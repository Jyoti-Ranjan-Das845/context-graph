from context_graph.domain import EdgeKind, Item, Node, NodeKind, PersonRecord, PersonRef, Source
from context_graph.domain import keys
from context_graph.linking.identity import IdentityResolver
from context_graph.linking.matchers import (
    ChannelMatcher,
    GitHubNumberMatcher,
    IssueKeyMatcher,
    MatchContext,
    PathMatcher,
    QuotedTitleMatcher,
    SymbolMatcher,
)
from context_graph.linking.references import ReferenceIndex, ReferenceLinker

CTX = MatchContext(source="slack")


def found(matcher, text, context=CTX):
    return {k for hit in matcher.find(text, context) for k in hit.keys}


class TestMatchers:
    def test_issue_keys(self):
        assert found(IssueKeyMatcher(), "See ENG-5 and DEMO-12.") == {"issue:ENG-5", "issue:DEMO-12"}
        assert found(IssueKeyMatcher(), "utf-8 and a-1 are not keys") == set()

    def test_channel_ignores_order_numbers_and_url_fragments(self):
        assert found(ChannelMatcher(), "talk in #payments, orders #4821, see /x#frag") == {"channel:payments"}

    def test_github_numbers(self):
        m = GitHubNumberMatcher()
        assert keys.github_number("acme", "pay", 3) in found(m, "acme/pay#3")
        assert keys.github_repo_number("pay", 1) in found(m, "issue #1 of pay")
        assert found(m, "orders #4821") == set()
        inside = MatchContext(source="github", repo="acme/pay")
        assert keys.github_number("acme", "pay", 7) in found(m, "closes #7", inside)
        single = MatchContext(source="notion", only_repo="acme/pay")
        assert keys.github_number("acme", "pay", 1) in found(m, "tracked in GitHub issue #1", single)

    def test_quoted_title_needs_three_words(self):
        m = QuotedTitleMatcher()
        assert found(m, 'the doc "Payments retry design" says') == {keys.title("Payments retry design")}
        assert found(m, 'just "a note"') == set()

    def test_paths_outside_urls_only(self):
        m = PathMatcher()
        assert found(m, "bug in payments/retry.py today") == {keys.path("payments/retry.py")}
        assert found(m, "https://github.com/a/b/blob/main/payments/retry.py") == set()

    def test_symbols_must_look_like_code(self):
        m = SymbolMatcher()
        assert found(m, "charge_with_retry() and chargeWithRetry fail") == {
            keys.symbol("charge_with_retry"),
            keys.symbol("chargeWithRetry"),
        }
        assert found(m, "payment retries fail") == set()


def _node(node_id, kind, node_keys, **props):
    return Node(id=node_id, kind=kind, source=Source.LINEAR, title=node_id, keys=frozenset(node_keys), props=props)


class TestReferenceLinker:
    def test_links_and_detects_fixes(self):
        target = _node("linear:issue:ENG-5", NodeKind.ISSUE, {keys.issue("ENG-5")})
        pr = Item(id="github:pull_request:a/b#2", source=Source.GITHUB, kind=NodeKind.PULL_REQUEST, title="Fix", body="Fixes ENG-5.", props={"repo": "a/b"})
        note = Item(id="slack:message:C1:1", source=Source.SLACK, kind=NodeKind.MESSAGE, title="", body="about ENG-5")
        edges = ReferenceLinker().link([pr, note], ReferenceIndex([target]))
        kinds = {(e.src, e.kind) for e in edges}
        assert (pr.id, EdgeKind.FIXES) in kinds
        assert (note.id, EdgeKind.REFERENCES) in kinds
        assert all(e.props["evidence"] for e in edges)

    def test_no_self_links_and_ambiguity_lowers_confidence(self):
        a = _node("a", NodeKind.PAGE, {keys.title("Shared title words")})
        b = _node("b", NodeKind.PAGE, {keys.title("Shared title words")})
        item = Item(id="a", source=Source.NOTION, kind=NodeKind.PAGE, title="x", body='see "Shared title words"')
        edges = ReferenceLinker().link([item], ReferenceIndex([a, b]))
        assert [e.dst for e in edges] == ["b"]
        other = Item(id="c", source=Source.NOTION, kind=NodeKind.PAGE, title="x", body='see "Shared title words"')
        confidences = {e.confidence for e in ReferenceLinker().link([other], ReferenceIndex([a, b]))}
        assert confidences == {round(0.9 * 0.6, 3)}

    def test_short_titles_are_not_indexed(self):
        index = ReferenceIndex([_node("p", NodeKind.PAGE, {keys.title("Problem")})])
        assert index.lookup(keys.title("Problem")) == set()


class TestIdentity:
    def test_merges_across_tools_by_email_handle_and_name(self):
        records = [
            PersonRecord(Source.JIRA, "acc-1", names={"Priya Shah"}, emails={"priya@acme.io"}),
            PersonRecord(Source.GITHUB, "99", handles={"priya-gh"}, emails={"Priya@acme.io"}, names={"priya-gh"}),
            PersonRecord(Source.SLACK, "U1", names={"Priya Shah"}),
            PersonRecord(Source.SLACK, "U2", names={"Sam"}),
        ]
        refs = [PersonRef(Source.GITHUB, native_id="99", handle="priya-gh"), PersonRef(Source.SLACK, native_id="U2")]
        result = IdentityResolver(merge_by_name=True).resolve(records, refs)
        assert len(result.people) == 2
        priya = result.node_for(PersonRef(Source.SLACK, native_id="U1"))
        assert priya == result.node_for(PersonRef(Source.GITHUB, native_id="99")) == "person:priya@acme.io"
        node = next(p for p in result.people if p.id == priya)
        assert node.title == "Priya Shah" and set(node.props["sources"]) == {"jira", "github", "slack"}

    def test_single_word_names_never_merge(self):
        records = [PersonRecord(Source.SLACK, "U1", names={"Sam"}), PersonRecord(Source.JIRA, "a", names={"Sam"})]
        assert len(IdentityResolver().resolve(records, []).people) == 2

    def test_name_merge_can_be_disabled(self):
        records = [PersonRecord(Source.SLACK, "U1", names={"Priya Shah"}), PersonRecord(Source.JIRA, "a", names={"Priya Shah"})]
        assert len(IdentityResolver(merge_by_name=False).resolve(records, []).people) == 2
