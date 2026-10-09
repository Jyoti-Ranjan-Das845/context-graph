from typing import Any

from context_graph.enrich.concepts import ConceptKind, ConceptMerger, ConceptRegistry, concept_key
from context_graph.enrich.llm import LLMError

TOPIC, DECISION = ConceptKind.TOPIC, ConceptKind.DECISION


class ScriptedLLM:
    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def complete_json(self, *, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.prompts.append(prompt)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def merger(tmp_path, llm: ScriptedLLM) -> ConceptMerger:
    return ConceptMerger(llm, ConceptRegistry(tmp_path / "concepts.sqlite"))


def test_keys_ignore_case_punctuation_and_topic_plurals():
    assert concept_key(TOPIC, "Payment Retries") == concept_key(TOPIC, "payment retry") == "payment-retry"
    assert concept_key(TOPIC, "status") == "status"
    assert concept_key(DECISION, "Cap payment retries at 5.") == concept_key(DECISION, "cap payment retries at 5")
    assert concept_key(DECISION, "Cap payment retries at 5") != concept_key(DECISION, "Cap payment retry at 5")


def test_new_wordings_join_existing_concepts_and_are_remembered(tmp_path):
    llm = ScriptedLLM(
        {"groups": [{"label": "Cap payment retries at 5.", "members": ["n1", "n2"]}]},
        {"groups": [{"label": "something else", "members": ["e1", "n1"]}]},
    )
    m = merger(tmp_path, llm)
    first, _ = m.canonicalize(DECISION, ["Cap payment retries at 5.", "Allow at most 5 retries."])
    assert first == {"Cap payment retries at 5.": "Cap payment retries at 5.", "Allow at most 5 retries.": "Cap payment retries at 5."}

    second, report = m.canonicalize(DECISION, ["Allow at most 5 retries.", "Never retry more than five times."])
    assert second["Never retry more than five times."] == "Cap payment retries at 5."  # an existing label wins
    assert second["Allow at most 5 retries."] == "Cap payment retries at 5."  # answered from the registry
    assert report.new == 1 and report.calls == 1 and '"existing"' in llm.prompts[1]

    again, report = m.canonicalize(DECISION, ["Never retry more than five times."])
    assert report.calls == 0 and again["Never retry more than five times."] == "Cap payment retries at 5."


def test_unknown_members_and_single_member_groups_are_ignored(tmp_path):
    llm = ScriptedLLM({"groups": [{"label": "x", "members": ["n1", "n9"]}, {"label": "y", "members": ["n2"]}]})
    mapping, report = merger(tmp_path, llm).canonicalize(TOPIC, ["refunds", "alerting"])
    assert mapping == {"refunds": "refunds", "alerting": "alerting"} and report.merged == 0


def test_a_failed_call_keeps_wordings_and_asks_again_later(tmp_path):
    llm = ScriptedLLM(LLMError("down"), {"groups": [{"label": "refunds", "members": ["n1", "n2"]}]})
    m = merger(tmp_path, llm)
    mapping, report = m.canonicalize(TOPIC, ["refunds", "refunding customers"])
    assert mapping == {"refunds": "refunds", "refunding customers": "refunding customers"} and report.errors == ["down"]
    mapping, _ = m.canonicalize(TOPIC, ["refunds", "refunding customers"])
    assert mapping["refunding customers"] == "refunds"


def test_a_single_new_wording_with_nothing_to_compare_needs_no_call(tmp_path):
    llm = ScriptedLLM()
    mapping, report = merger(tmp_path, llm).canonicalize(TOPIC, ["Idempotency keys", "idempotency key"])
    assert report.calls == 0 and mapping == {"Idempotency keys": "Idempotency keys", "idempotency key": "Idempotency keys"}


def test_large_registries_only_send_overlapping_candidates(tmp_path):
    registry = ConceptRegistry(tmp_path / "concepts.sqlite")
    registry.record(TOPIC, {concept_key(TOPIC, f"area {n}"): f"area {n}" for n in range(5)})
    registry.record(TOPIC, {"payment-retry": "payment retries"})
    llm = ScriptedLLM({"groups": []})
    ConceptMerger(llm, registry, max_candidates=3).canonicalize(TOPIC, ["charge retries"])
    assert "payment retries" in llm.prompts[0] and "area 1" not in llm.prompts[0]
