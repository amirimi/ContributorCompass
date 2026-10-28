from compass.domain import Bucket, Evaluation, Recommendation, RecommendationGroup
from compass.views.attribution import EXPLORE_ATTRIBUTION

BUCKET_TITLES: dict[Bucket, str] = {
    Bucket.CAREER_SIGNAL: "Career Signal",
    Bucket.FRESH_BREEZE: "Fresh Breeze",
    Bucket.ALIGNED: "Aligned",
}

EMPTY_BUCKET = "nothing cleared the floor"


def format_axis(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.2f}"


def format_axes(evaluation: Evaluation) -> str:
    return (
        f"fit {format_axis(evaluation.fit)}"
        f"   absorption {format_axis(evaluation.absorption)}"
        f"   upside {format_axis(evaluation.upside)}"
    )


def render_recommendation(recommendation: Recommendation) -> str:
    project = recommendation.project

    return "\n".join(
        [
            f"  {project.owner}/{project.name}",
            f"  {project.url}",
            f"  {format_axes(recommendation.evaluation)}",
            f"  {recommendation.explanation}",
        ]
    )


def render_bucket(bucket: Bucket, recommendations: list[Recommendation]) -> str:
    if not recommendations:
        return f"{BUCKET_TITLES[bucket]}\n  {EMPTY_BUCKET}"

    bodies = "\n\n".join(
        render_recommendation(recommendation) for recommendation in recommendations
    )

    return f"{BUCKET_TITLES[bucket]}\n{bodies}"


def render_group(group: RecommendationGroup) -> str:
    sections = [
        render_bucket(
            bucket,
            [
                recommendation
                for recommendation in group.recommendations
                if recommendation.bucket is bucket
            ],
        )
        for bucket in Bucket
    ]

    return "\n\n".join([f"as of {group.as_of:%Y-%m-%d}", *sections, EXPLORE_ATTRIBUTION])
