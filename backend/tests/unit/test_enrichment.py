from typing import Any

from context_graph.domain import EdgeKind, Item, NodeKind, Source
from context_graph.enrich.cache import LLMCache
from context_graph.enrich.concepts import ConceptMerger, ConceptRegistry
from context_graph.enrich.enricher import SemanticEnricher
from context_graph.enrich.llm import LLMError

TEXT = "Decision: send an idempotency key with every charge and use exponential backoff for payment retries."


class FakeLLM:
    def __init__(self, answers: list[Any]) -> None:
        self.answers = answers
        self.calls = 0

    def complete_json(self, *, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def item(item_id: str = "slack:message:C1:1", text: str = TEXT) -> Item:
    return Item(id=item_id, source=Source.SLACK, kind=NodeKind.MESSAGE, title="Decision", body=text)


GOOD = {"items": [{"id": "i1", "topics": [
    {"name": "Idempotency keys", "quote": "idempotency key"},
    {"name": "Invented", "quote": "this text is not in the item"},
], "decisions": [{"statement": "Send an idempotency key with every charge.", "quote": "send an idempotency key with every charge", "topics": ["idempotency key"]}]}]}


def test_quotes_are_verified_and_topics_are_merged(tmp_path):
    enricher = SemanticEnricher(FakeLLM([GOOD]), LLMCache(tmp_path / "c.sqlite"))
    graph, report = enricher.enrich([item()])
    assert report.sent == 1 and report.dropped_quotes == 1
    topics = [n for n in graph.nodes if n.kind is NodeKind.TOPIC]
    assert [t.id for t in topics] == ["topic:idempotency-key"]  # "Idempotency keys" and "idempotency key" merge
    kinds = {e.kind for e in graph.edges}
    assert kinds == {EdgeKind.MENTIONS, EdgeKind.DECIDES, EdgeKind.ABOUT}
    assert all(e.confidence == 0.8 for e in graph.edges)


def test_cache_prevents_a_second_llm_call(tmp_path):
    cache = LLMCache(tmp_path / "c.sqlite")
    llm = FakeLLM([GOOD])
    SemanticEnricher(llm, cache).enrich([item()])
    graph, report = SemanticEnricher(llm, cache).enrich([item()])
    assert llm.calls == 1 and report.cached == 1 and report.sent == 0
    assert any(n.kind is NodeKind.DECISION for n in graph.nodes)


def test_failed_batches_are_reported_not_raised(tmp_path):
    enricher = SemanticEnricher(FakeLLM([LLMError("down")]), LLMCache(tmp_path / "c.sqlite"))
    graph, report = enricher.enrich([item()])
    assert report.failed_batches == 1 and report.errors == ["down"] and graph.nodes == []


def test_short_text_and_limits(tmp_path):
    llm = FakeLLM([GOOD])
    enricher = SemanticEnricher(llm, LLMCache(tmp_path / "c.sqlite"), batch_size=1, max_items_per_run=1)
    _, report = enricher.enrich([item("a", "too short"), item("b"), item("c", TEXT + " again")])
    assert report.considered == 2 and report.sent == 1 and report.deferred == 1


def test_same_decision_from_two_tools_becomes_one_node(tmp_path):
    slack = item("slack:message:C1:1", "Decision: send an idempotency key with every charge, starting today.")
    notion = Item(
        id="notion:page:abc", source=Source.NOTION, kind=NodeKind.PAGE, title="Retry design",
        body="We will attach an idempotency key to each charge request so retries are safe.",
    )
    extraction = {"items": [
        {"id": "i1", "topics": [], "decisions": [{"statement": "Send an idempotency key with every charge.", "quote": "send an idempotency key with every charge", "topics": ["idempotency key"]}]},
        {"id": "i2", "topics": [], "decisions": [{"statement": "Attach an idempotency key to each charge request.", "quote": "attach an idempotency key to each charge request", "topics": ["Idempotency keys"]}]},
    ]}
    merge = {"groups": [{"label": "Send an idempotency key with every charge.", "members": ["n1", "n2"]}]}
    llm = FakeLLM([extraction, merge])  # one topic wording only, so topics need no LLM call
    cache = tmp_path / "c.sqlite"
    enricher = SemanticEnricher(llm, LLMCache(cache), merger=ConceptMerger(llm, ConceptRegistry(cache)))

    graph, report = enricher.enrich([slack, notion])

    decisions = [n for n in graph.nodes if n.kind is NodeKind.DECISION]
    assert len(decisions) == 1 and decisions[0].title == "Send an idempotency key with every charge."
    assert decisions[0].props["also_stated_as"] == ["Attach an idempotency key to each charge request."]
    decided_in = {e.src for e in graph.edges if e.kind is EdgeKind.DECIDES}
    assert decided_in == {"slack:message:C1:1", "notion:page:abc"}
    assert [n.id for n in graph.nodes if n.kind is NodeKind.TOPIC] == ["topic:idempotency-key"]
    assert report.merged_decisions == 1 and llm.calls == 2
