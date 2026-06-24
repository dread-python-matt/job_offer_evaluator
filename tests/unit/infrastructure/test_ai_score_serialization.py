import json

from app.domain.scoring import AiInsight, MatchScore, ScoreComponent
from app.infrastructure.postgres_ai_score_repository import deserialize_score, serialize_score


def _score() -> MatchScore:
    insight = AiInsight(rate=4, pros=["Strong Python"], cons=["No K8s"], rate_reason="Solid fit")
    return (
        MatchScore()
        .with_component(ScoreComponent(name="skills", value=2.0, weight=4.0))
        .with_component(
            ScoreComponent(name="description", value=0.8, weight=1.0, metadata={"ai_insight": insight})
        )
    )


def test_score_survives_serialize_round_trip():
    score = _score()

    restored = deserialize_score(serialize_score(score))

    assert restored.get("skills") == 2.0
    assert restored.overall_score == score.overall_score
    insight = restored.metadata("ai_insight")
    assert insight.rate == 4
    assert insight.pros == ["Strong Python"]
    assert insight.cons == ["No K8s"]
    assert insight.rate_reason == "Solid fit"


def test_serialized_form_is_json_safe():
    json.dumps(serialize_score(_score()))
