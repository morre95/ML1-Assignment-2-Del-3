from react_agent_system.hub.assessment import format_hub_context, parse_assessment
from react_agent_system.hub.models import AssessmentAction, HubMessage


def test_parse_assessment_accepts_json_fence() -> None:
    decision = parse_assessment(
        """```json
        {"action": "respond", "reason": "relevant", "confidence": 0.9,
         "response_hint": "help with code", "target_agent": ""}
        ```"""
    )

    assert decision.action == AssessmentAction.RESPOND
    assert decision.response_hint == "help with code"


def test_parse_assessment_fails_closed_to_silence() -> None:
    decision = parse_assessment("not json")

    assert decision.action == AssessmentAction.STAY_SILENT


def test_format_hub_context_limits_recent_messages() -> None:
    messages = [
        HubMessage(seq=1, agent_name="a", content="old"),
        HubMessage(seq=2, agent_name="b", content="new"),
    ]

    context = format_hub_context(messages, max_messages=1)

    assert "old" not in context
    assert "[seq=2 agent=b] new" in context
