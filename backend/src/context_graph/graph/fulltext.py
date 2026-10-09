"""What the full-text index holds and how a search becomes FTS5 match expressions.

Ranking uses progressive relaxation: items that contain every content word of the query come
first, then items missing one word, then items with any word. BM25 orders items within a level.
Questions like "which decisions were made about payment retries" therefore find the decisions
about payment retries, instead of whatever happens to contain a rare filler word.
"""

from __future__ import annotations

import re

from context_graph.domain import Node, NodeKind, Source

MAX_TERMS = 8
"""Long questions keep their first eight content words, which bounds the number of queries per search."""

_TOKEN = re.compile(r"[\w][\w.\-/#]*", re.UNICODE)

STOPWORDS = frozenset(
    """
    a about above after again all also am an and any are as at be because been before being between both but by
    can could did do does doing done during each few for from had has have having he her here hers him his how i
    if in into is it its itself just me more most my no nor not now of off on once only or other our ours out over
    own same she should so some such than that the their theirs them then there these they this those through to
    too under until up very was we were what when where which while who whom why will with would you your yours
    made make makes tell show find give get got know happen happened say said
    """.split()
)
"""Words that carry no meaning in a search. A query made only of them is searched as typed."""

KIND_WORDS = {
    NodeKind.PULL_REQUEST: "pull request pr",
    NodeKind.EMAIL_THREAD: "email thread",
    NodeKind.SYMBOL: "function symbol",
}

_KEY_KINDS = {"issue", "channel", "path", "symbol", "email", "commit", "ghreponum"}


def search_terms(query: str) -> list[str]:
    tokens = list(dict.fromkeys(t.lower() for t in _TOKEN.findall(query)))
    content = [t for t in tokens if t not in STOPWORDS]
    return (content or tokens)[:MAX_TERMS]


def match_levels(terms: list[str]) -> list[list[str]]:
    """FTS5 expressions grouped by strictness, strictest first: all words, all but one, any word."""
    if not terms:
        return []
    quoted = ['"' + t.replace('"', "") + '"' for t in terms]
    if len(terms[-1]) >= 3 and terms[-1].isalpha():
        quoted[-1] += "*"  # the last word may still be being typed
    levels = [[" AND ".join(quoted)]]
    if len(quoted) > 2:
        levels.append([" AND ".join(quoted[:i] + quoted[i + 1 :]) for i in range(len(quoted))])
    if len(quoted) > 1:
        levels.append([" OR ".join(quoted)])
    return levels


def aliases(node: Node) -> str:
    """Searchable text beyond title and body: key forms (`ENG-5`, `#payments`, `payments/retry.py`),
    the node's kind ("decision", "pull request") and its tool ("slack")."""
    out = [str(node.props.get("ref", "")), KIND_WORDS.get(node.kind, node.kind.value.replace("_", " "))]
    if node.source is not Source.DERIVED:
        out.append(node.source.value)
    for key in node.keys:
        kind, _, value = key.partition(":")
        if kind in _KEY_KINDS:
            out.append(("#" + value) if kind == "channel" else value)
    return " ".join(filter(None, out))
