import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../../api/client";
import type { NodeCard } from "../../api/types";
import { Empty, ErrorNote, SourceBadge, timeAgo } from "../../components/ui";
import { NodePanel } from "../graph/NodePanel";

type Mode = "search" | "agent";

/** A search hit; in agent mode it also carries the one-line links `retrieve_context` returns. */
type ResultCard = NodeCard & { links?: string[] };

interface Results {
  query: string;
  mode: Mode;
  cards: ResultCard[];
  /** Rough size of the agent bundle (characters / 4). */
  tokens: number;
}

async function fetchResults(query: string, mode: Mode): Promise<Results> {
  if (mode === "search") return { query, mode, cards: await api.search(query), tokens: 0 };
  const bundle = await api.context(query);
  return { query, mode, cards: bundle.results, tokens: Math.round(JSON.stringify(bundle).length / 4) };
}

export function SearchView({ onShowInGraph }: { onShowInGraph: (id: string) => void }) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<Mode>("search");
  const [results, setResults] = useState<Results | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(text: string, nextMode: Mode) {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResults(await fetchResults(text.trim(), nextMode));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run(query, mode);
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    if (results) void run(results.query, next);
  };

  return (
    <div className="split">
      <div className="search-main">
        <form className="search-bar" onSubmit={submit}>
          <input
            autoFocus
            className="search-input big"
            placeholder="Search everything: an issue key, a person, a topic, a file…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="segmented" role="tablist">
            <button type="button" className={mode === "search" ? "on" : ""} onClick={() => switchMode("search")}>
              Items
            </button>
            <button type="button" className={mode === "agent" ? "on" : ""} onClick={() => switchMode("agent")}>
              Agent context
            </button>
          </div>
          <button className="primary" disabled={busy}>
            {busy ? "Searching…" : "Search"}
          </button>
        </form>
        <ErrorNote message={error} />

        {results?.mode === "agent" && (
          <p className="muted small">
            This is the bundle the MCP tool <code>retrieve_context</code> gives Claude Code or Codex for this question (about{" "}
            {results.tokens.toLocaleString()} tokens). The agent can then open any item with <code>get_node</code>.
          </p>
        )}
        {results && results.cards.length === 0 && <Empty>No matches for “{results.query}”.</Empty>}

        <ul className="results">
          {results?.cards.map((card) => (
            <li key={card.id} className={`result ${selected === card.id ? "active" : ""}`}>
              <button className="result-main" onClick={() => setSelected(card.id)}>
                <SourceBadge source={card.source} kind={card.kind} />
                <div className="result-title">
                  {card.ref && <span className="ref">{card.ref}</span>} {card.title}
                </div>
                {card.snippet && <div className="result-snippet">{card.snippet}</div>}
                <div className="muted small">{card.updated_at ? `Updated ${timeAgo(card.updated_at)}` : card.id}</div>
              </button>
              {card.links && card.links.length > 0 && (
                <ul className="agent-links">
                  {card.links.map((link) => (
                    <li key={link}>
                      <code>{link}</code>
                    </li>
                  ))}
                </ul>
              )}
              <button className="link-button" onClick={() => onShowInGraph(card.id)}>
                Show in graph →
              </button>
            </li>
          ))}
        </ul>
      </div>
      {selected && <NodePanel key={selected} nodeId={selected} onSelect={setSelected} onClose={() => setSelected(null)} />}
    </div>
  );
}
