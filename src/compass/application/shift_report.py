import dataclasses
import datetime
import random
from collections import Counter, defaultdict
from collections.abc import Sequence

from compass.domain import Crossing, Preferences, Vocabulary, cross, describe_contributor
from compass.domain.choice import ChoiceResult, build_cases, evaluate_choice
from compass.domain.contributions import ContributorHistory, Entry, RepositoryStore, extract_entries
from compass.domain.feedback import FeedbackResult, Outcome, evaluate_feedback
from compass.domain.shift import ClassifiedRepository, Observation, classify_repository, observe
from compass.domain.statistics import phi
from compass.domain.verdict import Decision, decide

DECOY_SEED = 20261029
BOOTSTRAP_SEED = 1029
CAP_SEED = 50
ENTRY_CAP = 50


@dataclasses.dataclass(frozen=True)
class ShiftReport:
    label: str
    contributors: int
    skipped: int
    entries: int
    with_language: int
    with_meaning: int
    assessable: int
    eligible: int
    phi: float
    cells: dict[str, int]
    choice: ChoiceResult
    feedback: list[FeedbackResult]
    decision: Decision

    @property
    def coverage(self) -> float:
        return self.assessable / self.entries if self.entries else 0.0


@dataclasses.dataclass(frozen=True)
class ReportVariant:
    label: str
    vocabulary: Vocabulary
    min_stars: int
    entry_cap: int | None = None


@dataclasses.dataclass(frozen=True)
class OwnEntry:
    slug: str
    stars: int
    created_at: datetime.datetime
    cell: str
    with_preferences: Crossing
    merged: bool | None
    returned: bool | None


def observe_entries(
    histories: Sequence[ContributorHistory],
    store: RepositoryStore,
    vocabulary: Vocabulary,
    min_stars: int,
) -> list[Observation]:
    classified: dict[str, ClassifiedRepository] = {}
    observations: list[Observation] = []

    for history in histories:
        for entry in extract_entries(history, store.repositories, min_stars):
            node_id = entry.repository.node_id

            if node_id not in classified:
                classified[node_id] = classify_repository(
                    entry.repository.as_topic_project(), vocabulary
                )

            observations.append(observe(entry, classified[node_id], vocabulary))

    return observations


def touched_repositories(
    histories: Sequence[ContributorHistory],
    store: RepositoryStore,
) -> dict[str, frozenset[str]]:
    touched: dict[str, frozenset[str]] = {}

    for history in histories:
        slugs = {repository.slug for repository in history.owned}
        slugs.update(
            store.repositories[pull_request.repository_id].slug
            for pull_request in history.pull_requests
            if pull_request.repository_id in store.repositories
        )
        touched[history.login] = frozenset(slugs)

    return touched


def cap_per_contributor(
    observations: Sequence[Observation],
    cap: int | None,
) -> list[Observation]:
    if cap is None:
        return list(observations)

    grouped: defaultdict[str, list[Observation]] = defaultdict(list)

    for observation in observations:
        grouped[observation.entry.login].append(observation)

    rng = random.Random(CAP_SEED)
    kept: list[Observation] = []

    for members in grouped.values():
        kept.extend(members if len(members) <= cap else rng.sample(members, cap))

    return kept


def run_report(
    variant: ReportVariant,
    histories: Sequence[ContributorHistory],
    store: RepositoryStore,
    reps: int,
) -> ShiftReport:
    label = variant.label
    vocabulary = variant.vocabulary
    complete = [history for history in histories if history.complete]
    observations = cap_per_contributor(
        observe_entries(complete, store, vocabulary, variant.min_stars), variant.entry_cap
    )
    eligible = [observation for observation in observations if observation.contributor.ready]
    assessable = [observation for observation in eligible if observation.repository.assessable]
    rng = random.Random(BOOTSTRAP_SEED)
    cases = build_cases(
        eligible, touched_repositories(complete, store), vocabulary, random.Random(DECOY_SEED)
    )
    choice = evaluate_choice(cases, reps, rng)
    feedback = [
        result
        for outcome in Outcome
        if (result := evaluate_feedback(assessable, outcome, reps, rng)) is not None
    ]
    correlation = phi([(item.tooling_shift, item.meaning_shift) for item in assessable])
    assessable_entries = sum(item.repository.assessable for item in observations)

    return ShiftReport(
        label=label,
        contributors=len(complete),
        skipped=len(histories) - len(complete),
        entries=len(observations),
        with_language=sum(item.repository.has_language for item in observations),
        with_meaning=sum(item.repository.has_meaning for item in observations),
        assessable=assessable_entries,
        eligible=len(eligible),
        phi=correlation,
        cells=dict(Counter(item.cell for item in eligible).most_common()),
        choice=choice,
        feedback=feedback,
        decision=decide(
            coverage=assessable_entries / len(observations) if observations else 0.0,
            phi=correlation,
            choice=choice,
            feedback=feedback,
        ),
    )


def own_entries(
    login: str,
    histories: Sequence[ContributorHistory],
    store: RepositoryStore,
    vocabulary: Vocabulary,
    preferences: Preferences,
) -> list[OwnEntry]:
    own = [history for history in histories if history.login.lower() == login.lower()]
    listed: list[OwnEntry] = []

    for observation in observe_entries(own, store, vocabulary, min_stars=0):
        entry: Entry = observation.entry
        contributor = describe_contributor(entry.history.as_profile(login), preferences, vocabulary)
        listed.append(
            OwnEntry(
                slug=entry.repository.slug,
                stars=entry.repository.stars,
                created_at=entry.created_at,
                cell=observation.cell,
                with_preferences=cross(observation.repository.identity, contributor, vocabulary),
                merged=entry.merged,
                returned=entry.returned,
            )
        )

    return listed
