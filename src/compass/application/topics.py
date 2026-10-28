import datetime
import logging

from compass.adapters import GitHubClient, TopicCache, format_github_handle
from compass.application.personal_info import (
    get_topic_projects,
    languages_frequency,
    recent_user_repos,
    topics_frequency,
)
from compass.domain import PersonalProfileFile, ProjectTopicsFile

logger = logging.getLogger(__name__)


def load_fresh_profile(
    github_handle: str,
    cache: TopicCache,
    stale_after: datetime.timedelta,
) -> PersonalProfileFile | None:
    cached = cache.load_personal()

    if cached is None:
        return None

    if cached.github_handle != github_handle:
        return None

    if cached.is_stale(stale_after):
        return None

    return cached


def collect_profile(
    github_handle: str,
    github: GitHubClient,
    cache: TopicCache,
    stale_after: datetime.timedelta,
) -> PersonalProfileFile:
    formatted_github_handle = format_github_handle(github_handle)
    cached = load_fresh_profile(
        github_handle=formatted_github_handle,
        cache=cache,
        stale_after=stale_after,
    )

    if cached is not None:
        return cached

    logger.info("Fetching the profile for %s", formatted_github_handle)

    repos = recent_user_repos(github_handle=formatted_github_handle, github=github)
    profile = PersonalProfileFile(
        github_handle=formatted_github_handle,
        topics_frequency=topics_frequency(repos),
        languages_frequency=languages_frequency(repos),
    )
    cache.save_personal(profile)

    return profile


def collect_project_topics(
    topic: str,
    github: GitHubClient,
    cache: TopicCache,
    stale_after: datetime.timedelta,
) -> ProjectTopicsFile:
    cached = cache.load_projects(topic)

    if cached is not None and not cached.is_stale(stale_after):
        return cached

    logger.info("Fetching projects for %s", topic)

    collection = get_topic_projects(topic=topic, github=github)
    project_topics = ProjectTopicsFile(
        projects=collection.projects,
        stop_reason=collection.stop_reason,
        pages_fetched=collection.pages_fetched,
    )
    cache.save_projects(topic, project_topics)

    logger.info(
        "%s: %s projects, %s pages, stopped on %s",
        topic,
        len(collection.projects),
        collection.pages_fetched,
        collection.stop_reason,
    )

    return project_topics


def stale_topics_oldest_first(
    topics_frequency: list[tuple[str, int]],
    cache: TopicCache,
    stale_after: datetime.timedelta,
) -> list[str]:
    never_fetched = datetime.datetime.min.replace(tzinfo=datetime.UTC)
    stale: list[tuple[datetime.datetime, int, str]] = []

    for topic, frequency in topics_frequency:
        cached = cache.load_projects(topic)

        if cached is not None and not cached.is_stale(stale_after):
            continue

        update_date = never_fetched if cached is None else cached.update_date
        stale.append((update_date, -frequency, topic))

    return [topic for _, _, topic in sorted(stale)]


def collect_topic_pages(
    github_handle: str,
    github: GitHubClient,
    cache: TopicCache,
    personal_stale_after: datetime.timedelta,
    project_stale_after: datetime.timedelta,
    max_topics: int | None,
) -> None:
    profile = collect_profile(
        github_handle=github_handle,
        github=github,
        cache=cache,
        stale_after=personal_stale_after,
    )
    topics = stale_topics_oldest_first(
        topics_frequency=profile.topics_frequency,
        cache=cache,
        stale_after=project_stale_after,
    )

    for topic in topics[:max_topics]:
        collect_project_topics(
            topic=topic,
            github=github,
            cache=cache,
            stale_after=project_stale_after,
        )
