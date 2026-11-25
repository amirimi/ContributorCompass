import datetime
import logging
from typing import Annotated

import typer

from compass.adapters import (
    CLUSTERS_FILE,
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    MODEL_CACHE_DIR,
    MODEL_DOWNLOAD_TIMEOUT,
    PERSONAL_PROFILE_FILE,
    PERSONAL_PROFILE_REFRESH_AFTER,
    PERSONAL_PROFILE_STALE_AFTER,
    PREFERENCES_FILE,
    PROJECT_TOPICS_DIR,
    PROJECT_TOPICS_REFRESH_AFTER,
    PROJECT_TOPICS_STALE_AFTER,
    SHIFT_DIR,
    VOCABULARY_FILE,
    VOCABULARY_STALE_AFTER,
    ClusterCache,
    ContributionSource,
    ExploreSource,
    GitHubClient,
    LinguistSource,
    ShiftCache,
    TopicCache,
    VocabularyCache,
    load_lexicon,
    load_preferences,
    resolve_github_token,
)
from compass.application.identity import find_project, inspect_repository
from compass.application.shift_data import fetch_sample, sample_contributors
from compass.application.shift_report import ENTRY_CAP, ReportVariant, own_entries, run_report
from compass.application.topics import collect_profile, collect_topic_pages
from compass.application.vocabulary import (
    cached_projects,
    load_fresh_sources,
    refresh_sources,
    report_vocabulary,
)
from compass.domain import TagClusters, VocabularySources, build_vocabulary, describe_contributor
from compass.views.identity import render_inspection, render_vocabulary_report
from compass.views.shift import render_fetch_summary, render_own_entries, render_report

app = typer.Typer()
shift_app = typer.Typer(help="Test whether tooling and meaning shifts get unequal feedback.")
app.add_typer(shift_app, name="shift")
cache = TopicCache(personal_file=PERSONAL_PROFILE_FILE, project_dir=PROJECT_TOPICS_DIR)
vocabulary_cache = VocabularyCache(file_path=VOCABULARY_FILE)
cluster_cache = ClusterCache(file_path=CLUSTERS_FILE)
shift_cache = ShiftCache(directory=SHIFT_DIR)


def require_github_token() -> str:
    token = resolve_github_token()

    if token is None:
        typer.echo("GITHUB_TOKEN is not set", err=True)
        raise typer.Exit(code=1)

    return token


def require_fresh_sources() -> VocabularySources:
    sources = load_fresh_sources(vocabulary_cache, VOCABULARY_STALE_AFTER)

    if sources is None:
        typer.echo(f"{VOCABULARY_FILE} is missing or stale, run `compass vocabulary`", err=True)
        raise typer.Exit(code=1)

    return sources


def require_clusters() -> TagClusters:
    clusters = cluster_cache.load()

    if clusters is None:
        typer.echo(f"{CLUSTERS_FILE} is missing, run `compass clusters`", err=True)
        raise typer.Exit(code=1)

    return clusters


@app.command()
def get_topics(
    github_handle: Annotated[str, typer.Argument()],
) -> list[tuple[str, int]]:
    with GitHubClient(token=require_github_token()) as github:
        return collect_profile(
            github_handle=github_handle,
            github=github,
            cache=cache,
            stale_after=PERSONAL_PROFILE_STALE_AFTER,
        ).topics_frequency


@app.command()
def get_topics_pages(
    github_handle: Annotated[str, typer.Argument()],
    max_topics: Annotated[int | None, typer.Option()] = None,
) -> None:
    with GitHubClient(token=require_github_token()) as github:
        collect_topic_pages(
            github_handle=github_handle,
            github=github,
            cache=cache,
            personal_stale_after=PERSONAL_PROFILE_STALE_AFTER,
            project_stale_after=PROJECT_TOPICS_STALE_AFTER,
            max_topics=max_topics,
        )


@app.command()
def refresh(
    max_topics: Annotated[int | None, typer.Option()] = None,
) -> None:
    cached = cache.load_personal()

    if cached is None:
        typer.echo(f"No cached handle in {PERSONAL_PROFILE_FILE}", err=True)
        raise typer.Exit(code=1)

    with GitHubClient(token=require_github_token()) as github:
        collect_topic_pages(
            github_handle=cached.github_handle,
            github=github,
            cache=cache,
            personal_stale_after=PERSONAL_PROFILE_REFRESH_AFTER,
            project_stale_after=PROJECT_TOPICS_REFRESH_AFTER,
            max_topics=max_topics,
        )


@app.command()
def vocabulary() -> None:
    with GitHubClient(token=require_github_token()) as github:
        sources = refresh_sources(
            explore=ExploreSource(github),
            linguist=LinguistSource(),
            cache=vocabulary_cache,
        )

    built = build_vocabulary(sources, load_lexicon(), cluster_cache.load())
    profile = cache.load_personal()
    contributor = (
        describe_contributor(profile, load_preferences(PREFERENCES_FILE), built)
        if profile is not None
        else None
    )
    report = report_vocabulary(sources, built, cached_projects(cache), contributor)

    typer.echo(render_vocabulary_report(report))


@app.command()
def clusters() -> None:
    try:
        from compass.adapters.embedding import TagEmbedder, download_model
        from compass.application.clusters import EmbeddingModel, refresh_clusters
        from compass.views.clusters import render_cluster_report
    except ImportError:
        typer.echo("Clustering needs the clusters extra, run `uv sync --extra clusters`", err=True)
        raise typer.Exit(code=1) from None

    sources = require_fresh_sources()
    model_dir = download_model(
        EMBEDDING_MODEL, EMBEDDING_REVISION, MODEL_CACHE_DIR, MODEL_DOWNLOAD_TIMEOUT
    )
    report = refresh_clusters(
        projects=cached_projects(cache),
        sources=sources,
        lexicon=load_lexicon(),
        profile=cache.load_personal(),
        preferences=load_preferences(PREFERENCES_FILE),
        model=EmbeddingModel(
            name=EMBEDDING_MODEL,
            revision=EMBEDDING_REVISION,
            embedder=TagEmbedder(model_dir),
        ),
        cache=cluster_cache,
    )

    typer.echo(render_cluster_report(report))


@app.command()
def identify(
    repository: Annotated[str, typer.Argument(help="owner/name of a cached project")],
) -> None:
    sources = require_fresh_sources()
    projects = cached_projects(cache)
    project = find_project(repository, projects)

    if project is None:
        typer.echo(f"{repository} is not in {PROJECT_TOPICS_DIR}", err=True)
        raise typer.Exit(code=1)

    inspection = inspect_repository(
        project=project,
        vocabulary=build_vocabulary(sources, load_lexicon(), require_clusters()),
        profile=cache.load_personal(),
        preferences=load_preferences(PREFERENCES_FILE),
    )

    typer.echo(render_inspection(inspection))


@shift_app.command("sample")
def shift_sample(
    size: Annotated[int, typer.Option()] = 50,
    seed: Annotated[int, typer.Option()] = 20261029,
    include: Annotated[list[str] | None, typer.Option()] = None,
) -> None:
    with GitHubClient(token=require_github_token()) as github:
        sample = sample_contributors(
            projects=cached_projects(cache),
            source=ContributionSource(github),
            cache=shift_cache,
            size=size,
            seed=seed,
            include=include or [],
        )

    typer.echo(f"Sample holds {len(sample.logins)} contributors")


@shift_app.command("fetch")
def shift_fetch(
    limit: Annotated[int | None, typer.Option()] = None,
    hours: Annotated[float | None, typer.Option()] = None,
    workers: Annotated[int, typer.Option()] = 6,
) -> None:
    deadline = (
        datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=hours)
        if hours is not None
        else None
    )

    with GitHubClient(token=require_github_token()) as github:
        source = ContributionSource(github)
        before, _ = source.rate_limit()
        summary = fetch_sample(source, shift_cache, limit, deadline, workers)
        after, _ = source.rate_limit()

    points = before - after if after <= before else None
    typer.echo(render_fetch_summary(summary, points))


@shift_app.command("clusters")
def shift_clusters() -> None:
    try:
        from compass.adapters.embedding import TagEmbedder, download_model
        from compass.application.clusters import EmbeddingModel, build_clusters_within_budget
    except ImportError:
        typer.echo("Clustering needs the clusters extra, run `uv sync --extra clusters`", err=True)
        raise typer.Exit(code=1) from None

    model_dir = download_model(
        EMBEDDING_MODEL, EMBEDDING_REVISION, MODEL_CACHE_DIR, MODEL_DOWNLOAD_TIMEOUT
    )
    histories = shift_cache.load_contributors()
    store = shift_cache.load_repositories()
    repositories = {
        repository.url: repository.as_topic_project()
        for repository in [
            *store.repositories.values(),
            *(owned for history in histories for owned in history.owned),
        ]
    }
    projects = {project.url: project for project in cached_projects(cache)} | repositories
    clusters, min_occurrences = build_clusters_within_budget(
        projects=list(projects.values()),
        sources=require_fresh_sources(),
        lexicon=load_lexicon(),
        model=EmbeddingModel(
            name=EMBEDDING_MODEL,
            revision=EMBEDDING_REVISION,
            embedder=TagEmbedder(model_dir),
        ),
    )
    shift_cache.clusters.save(clusters)
    typer.echo(
        f"Saved {len(clusters.synonyms):,} tags from {len(projects):,} projects "
        f"with min_occurrences {min_occurrences}"
    )


@shift_app.command("report")
def shift_report(
    own: Annotated[str | None, typer.Option()] = None,
    reps: Annotated[int, typer.Option()] = 2000,
) -> None:
    population = shift_cache.clusters.load()

    if population is None:
        typer.echo("Population clusters are missing, run `compass shift clusters`", err=True)
        raise typer.Exit(code=1)

    sources = require_fresh_sources()
    lexicon = load_lexicon()
    histories = shift_cache.load_contributors()
    store = shift_cache.load_repositories()
    primary = build_vocabulary(sources, lexicon, population)
    committed = build_vocabulary(sources, lexicon, require_clusters())
    variants = [
        ReportVariant("Primary: population clusters, 100 stars", primary, 100),
        ReportVariant("Sensitivity: committed clusters, 100 stars", committed, 100),
        ReportVariant("Sensitivity: population clusters, 500 stars", primary, 500),
        ReportVariant(
            f"Post hoc: population clusters, 100 stars, {ENTRY_CAP} entries per contributor",
            primary,
            100,
            ENTRY_CAP,
        ),
    ]

    for variant in variants:
        typer.echo(render_report(run_report(variant, histories, store, reps)) + "\n")

    if own is not None:
        entries = own_entries(own, histories, store, primary, load_preferences(PREFERENCES_FILE))
        typer.echo(render_own_entries(own, entries))


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("compass").setLevel(logging.INFO)
    app()


if __name__ == "__main__":
    main()
