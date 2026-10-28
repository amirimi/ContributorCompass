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
    VOCABULARY_FILE,
    VOCABULARY_STALE_AFTER,
    ClusterCache,
    ExploreSource,
    GitHubClient,
    LinguistSource,
    TopicCache,
    VocabularyCache,
    load_lexicon,
    load_preferences,
    resolve_github_token,
)
from compass.application.identity import find_project, inspect_repository
from compass.application.topics import collect_profile, collect_topic_pages
from compass.application.vocabulary import (
    cached_projects,
    load_fresh_sources,
    refresh_sources,
    report_vocabulary,
)
from compass.domain import TagClusters, VocabularySources, build_vocabulary, describe_contributor
from compass.views.identity import render_inspection, render_vocabulary_report

app = typer.Typer()
cache = TopicCache(personal_file=PERSONAL_PROFILE_FILE, project_dir=PROJECT_TOPICS_DIR)
vocabulary_cache = VocabularyCache(file_path=VOCABULARY_FILE)
cluster_cache = ClusterCache(file_path=CLUSTERS_FILE)


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


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("compass").setLevel(logging.INFO)
    app()


if __name__ == "__main__":
    main()
