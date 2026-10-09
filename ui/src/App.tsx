import { useCallback, useState } from "react";
import { GraphView, type FocusRequest } from "./features/graph/GraphView";
import { SearchView } from "./features/search/SearchView";
import { SetupView } from "./features/setup/SetupView";
import { SyncBar } from "./features/sync/SyncBar";
import { SyncProvider } from "./features/sync/SyncContext";
import { useHashRoute } from "./hooks/useHashRoute";

const VIEWS = ["graph", "search", "setup"] as const;
type View = (typeof VIEWS)[number];

const VIEW_LABELS: Record<View, string> = { graph: "Graph", search: "Search", setup: "Setup" };

export function App() {
  const [view, navigate] = useHashRoute(VIEWS, "graph");
  // Bumped after every finished sync so views reload their data.
  const [dataVersion, setDataVersion] = useState(0);
  const [focus, setFocus] = useState<FocusRequest | null>(null);

  const onSynced = useCallback(() => setDataVersion((v) => v + 1), []);
  const showInGraph = useCallback(
    (id: string) => {
      setFocus({ id, nonce: Date.now() });
      navigate("graph");
    },
    [navigate],
  );

  return (
    <SyncProvider onSynced={onSynced}>
      <div className="app">
        <header className="topbar">
          <div className="brand">
            <span className="logo" aria-hidden>◎</span> Context Graph
          </div>
          <nav className="tabs">
            {VIEWS.map((id) => (
              <a key={id} href={`#/${id}`} className={view === id ? "active" : ""} aria-current={view === id ? "page" : undefined}>
                {VIEW_LABELS[id]}
              </a>
            ))}
          </nav>
          <SyncBar />
        </header>
        {/* Views stay mounted so each keeps its state (graph layout, search results) across tabs. */}
        <main className="views">
          <section className="view" hidden={view !== "graph"}>
            <GraphView version={dataVersion} focus={focus} />
          </section>
          <section className="view" hidden={view !== "search"}>
            <SearchView onShowInGraph={showInGraph} />
          </section>
          <section className="view scroll" hidden={view !== "setup"}>
            <SetupView version={dataVersion} />
          </section>
        </main>
      </div>
    </SyncProvider>
  );
}
