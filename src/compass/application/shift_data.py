import dataclasses
import datetime
import logging
import random
import threading
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

from compass.adapters import ContributionSource, ShiftCache
from compass.adapters.contributions import EARLIEST_SEARCH_DATE, SAMPLING_BATCH_SIZE
from compass.adapters.github import GRAPHQL_FAILURES
from compass.domain import TopicProject
from compass.domain.contributions import (
    ContributionRepository,
    ContributorHistory,
    RepositoryStore,
    ShiftSample,
)

logger = logging.getLogger(__name__)

MAX_PULL_REQUESTS = 2000
SAVE_EVERY = 10
BOT_SUFFIX = "[bot]"


@dataclasses.dataclass(frozen=True)
class FetchSummary:
    fetched: int
    skipped: int
    failed: int
    remaining: int
    elapsed: datetime.timedelta


def project_slugs(projects: Sequence[TopicProject], seed: int) -> list[str]:
    slugs = sorted({f"{project.owner}/{project.name}" for project in projects})
    random.Random(seed).shuffle(slugs)

    return slugs


def pick_author(slug: str, authors: list[str], chosen: set[str], seed: int) -> str | None:
    owner = slug.split("/")[0].lower()
    candidates = sorted(
        {
            author
            for author in authors
            if author.lower() != owner
            and not author.lower().endswith(BOT_SUFFIX)
            and author.lower() not in chosen
        }
    )

    return random.Random(f"{seed}:{slug}").choice(candidates) if candidates else None


def sample_contributors(
    projects: Sequence[TopicProject],
    source: ContributionSource,
    cache: ShiftCache,
    size: int,
    seed: int,
    include: Sequence[str],
) -> ShiftSample:
    sample = cache.load_sample() or ShiftSample(seed=seed, logins=list(include))
    chosen = {login.lower() for login in sample.logins}
    visited = set(sample.visited_projects)
    pending = [slug for slug in project_slugs(projects, sample.seed) if slug not in visited]

    for start in range(0, len(pending), SAMPLING_BATCH_SIZE):
        if len(sample.logins) >= size:
            break

        batch = pending[start : start + SAMPLING_BATCH_SIZE]
        authors = source.recent_authors(
            [(slug.split("/")[0], slug.split("/")[1]) for slug in batch]
        )

        for slug in batch:
            if len(sample.logins) >= size:
                break

            sample.visited_projects.append(slug)
            author = pick_author(slug, authors.get(slug, []), chosen, sample.seed)

            if author is not None:
                sample.logins.append(author)
                chosen.add(author.lower())

        cache.save_sample(sample)

    logger.info(
        "Sample holds %s contributors from %s projects",
        len(sample.logins),
        len(sample.visited_projects),
    )

    return sample


class SharedStore:
    def __init__(self, store: RepositoryStore) -> None:
        self.store = store
        self.lock = threading.Lock()

    def unknown(self, node_ids: Iterable[str]) -> list[str]:
        with self.lock:
            return self.store.unknown(node_ids)

    def add(self, requested: list[str], hydrated: dict[str, ContributionRepository]) -> None:
        with self.lock:
            self.store.repositories.update(hydrated)
            self.store.missing.extend(node_id for node_id in requested if node_id not in hydrated)

    def save(self, cache: ShiftCache) -> None:
        with self.lock:
            cache.save_repositories(self.store)


def fetch_contributor(
    login: str,
    source: ContributionSource,
    shared: SharedStore,
    today: datetime.date,
) -> ContributorHistory:
    count = source.pull_request_count(login, today)

    if count > MAX_PULL_REQUESTS:
        return ContributorHistory(login=login, external_pull_requests=count, complete=False)

    pull_requests = source.pull_requests(login, EARLIEST_SEARCH_DATE, today)
    owned = source.owned_repositories(login)
    unknown = shared.unknown(pull_request.repository_id for pull_request in pull_requests)
    shared.add(unknown, source.hydrate(unknown))

    return ContributorHistory(
        login=login,
        external_pull_requests=count,
        complete=True,
        owned=owned,
        pull_requests=pull_requests,
    )


def fetch_before(
    login: str,
    source: ContributionSource,
    shared: SharedStore,
    today: datetime.date,
    deadline: datetime.datetime | None,
) -> ContributorHistory | None:
    if deadline is not None and datetime.datetime.now(datetime.UTC) >= deadline:
        return None

    return fetch_contributor(login, source, shared, today)


def flush(cache: ShiftCache, shared: SharedStore, pending: list[ContributorHistory]) -> None:
    shared.save(cache)

    for history in pending:
        cache.save_contributor(history)

    pending.clear()


def fetch_sample(
    source: ContributionSource,
    cache: ShiftCache,
    limit: int | None,
    deadline: datetime.datetime | None,
    workers: int,
) -> FetchSummary:
    started = datetime.datetime.now(datetime.UTC)
    sample = cache.load_sample()
    logins = (sample.logins if sample else [])[:limit]
    queue = [login for login in logins if not cache.has_contributor(login)]
    shared = SharedStore(cache.load_repositories())
    pending: list[ContributorHistory] = []
    fetched = skipped = failed = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_before, login, source, shared, started.date(), deadline): login
            for login in queue
        }

        for future in as_completed(futures):
            try:
                history = future.result()
            except GRAPHQL_FAILURES as exc:
                logger.warning("Skipping %s after a failed fetch: %r", futures[future], exc)
                failed += 1
                continue

            if history is None:
                continue

            pending.append(history)
            fetched += 1
            skipped += not history.complete

            if len(pending) >= SAVE_EVERY:
                flush(cache, shared, pending)
                logger.info("Fetched %s of %s contributors", fetched, len(queue))

    flush(cache, shared, pending)

    return FetchSummary(
        fetched=fetched,
        skipped=skipped,
        failed=failed,
        remaining=len(queue) - fetched - failed,
        elapsed=datetime.datetime.now(datetime.UTC) - started,
    )
