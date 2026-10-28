from uuid import UUID

from compass.domain import (
    Bucket,
    Evaluation,
    Recommendation,
    RecommendationGroup,
    TopicProject,
)
from compass.views.attribution import EXPLORE_ATTRIBUTION
from compass.views.recommendations import EMPTY_BUCKET, render_group
from tests.fixtures import AS_OF, POLICY_VERSION, SAMPLE_GROUP


def build_recommendation(bucket: Bucket, evaluation: Evaluation) -> Recommendation:
    return Recommendation(
        id=UUID("55555555-5555-5555-5555-555555555555"),
        project=TopicProject(
            owner="acme",
            name="widget",
            url="https://github.com/acme/widget",
        ),
        bucket=bucket,
        evaluation=evaluation,
        explanation="Placeholder.",
        policy_version=POLICY_VERSION,
        as_of=AS_OF,
    )


def build_group(*recommendations: Recommendation) -> RecommendationGroup:
    return RecommendationGroup(
        id=UUID("66666666-6666-6666-6666-666666666666"),
        as_of=AS_OF,
        recommendations=list(recommendations),
    )


def test_every_bucket_gets_a_section() -> None:
    output = render_group(SAMPLE_GROUP)

    assert "Career Signal" in output
    assert "Fresh Breeze" in output
    assert "Aligned" in output


def test_project_appears_under_its_own_bucket() -> None:
    output = render_group(SAMPLE_GROUP)

    career_signal = output.index("Career Signal")
    fresh_breeze = output.index("Fresh Breeze")

    assert career_signal < output.index("django/django") < fresh_breeze


def test_empty_bucket_says_so_instead_of_vanishing() -> None:
    group = build_group(
        build_recommendation(Bucket.ALIGNED, Evaluation(fit=0.5)),
    )

    output = render_group(group)

    assert output.count(EMPTY_BUCKET) == 2


def test_unknown_axis_is_not_rendered_as_zero() -> None:
    group = build_group(
        build_recommendation(Bucket.ALIGNED, Evaluation(fit=0.5)),
    )

    output = render_group(group)

    assert "fit 0.50" in output
    assert "absorption unknown" in output
    assert "0.00" not in output


def test_as_of_is_dated() -> None:
    assert "as of 2026-09-05" in render_group(SAMPLE_GROUP)


def test_explore_vocabulary_is_credited() -> None:
    assert render_group(SAMPLE_GROUP).endswith(EXPLORE_ATTRIBUTION)
