import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape, { type Core } from "cytoscape";
import fcose from "cytoscape-fcose";
import { api } from "../../api/client";
import type { Subgraph } from "../../api/types";
import { useAsync } from "../../hooks/useAsync";
import { Empty, ErrorNote } from "../../components/ui";
import { buildStyle } from "./cyStyle";
import { LAYERS, LAYER_LABELS, SOURCE_COLORS, SOURCE_LABELS, nodeColor, type Layer } from "./palette";
import { NodePanel } from "./NodePanel";

cytoscape.use(fcose);

/** Ask the graph to select and center a node; `nonce` lets the same node be focused again. */
export interface FocusRequest {
  id: string;
  nonce: number;
}

const DARK = window.matchMedia("(prefers-color-scheme: dark)");
/** Zoom range used when centering a selected node: close enough to read, far enough to see its links. */
const SELECT_ZOOM = { min: 1, max: 1.6 };

function themeStyle() {
  const css = getComputedStyle(document.documentElement);
  const color = (name: string) => css.getPropertyValue(name).trim();
  return buildStyle({ text: color("--text"), edge: color("--edge"), accent: color("--accent"), surface: color("--surface") });
}

function toElements(graph: Subgraph) {
  return [
    ...graph.nodes.map((n) => ({
      group: "nodes" as const,
      data: { id: n.id, label: n.ref ? `${n.ref} ${n.title}` : n.title, kind: n.kind, source: n.source, color: nodeColor(n.kind, n.source) },
    })),
    ...graph.edges.map((e, i) => ({
      group: "edges" as const,
      data: { id: `e${i}`, source: e.src, target: e.dst, kind: e.kind, confidence: e.confidence },
    })),
  ];
}

/** Keeps the canvas sized to its container (side panel, tab switches) and fits once it first becomes visible. */
function followContainerSize(cy: Core, element: HTMLElement): () => void {
  let wasVisible = element.clientWidth > 0;
  const observer = new ResizeObserver(() => {
    cy.resize();
    const visible = element.clientWidth > 0;
    if (visible && !wasVisible) cy.fit(undefined, 40);
    wasVisible = visible;
  });
  observer.observe(element);
  return () => observer.disconnect();
}

export function GraphView({ version, focus }: { version: number; focus: FocusRequest | null }) {
  const { data, error, loading } = useAsync(() => api.graph(), [version]);
  const container = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [hiddenSources, setHiddenSources] = useState<Set<string>>(new Set());
  const [layers, setLayers] = useState<Record<Layer, boolean>>({ meaning: true, code: true, people: true });
  const [query, setQuery] = useState("");

  const sources = useMemo(() => [...new Set((data?.nodes ?? []).map((n) => n.source))].sort(), [data]);

  // Build the canvas whenever new graph data arrives.
  useEffect(() => {
    const element = container.current;
    if (!element || !data) return;
    const cy = cytoscape({
      container: element,
      elements: toElements(data),
      style: themeStyle(),
      layout: { name: "fcose", animate: false, nodeRepulsion: 9000, idealEdgeLength: 90, randomize: true } as never,
      minZoom: 0.15,
      maxZoom: 3,
    });
    cy.on("tap", "node", (event) => setSelected(event.target.id()));
    cy.on("tap", (event) => {
      if (event.target === cy) setSelected(null);
    });
    cy.on("mouseover", "node", (event) => event.target.addClass("hover"));
    cy.on("mouseout", "node", (event) => event.target.removeClass("hover"));

    const restyle = () => cy.style(themeStyle());
    DARK.addEventListener("change", restyle);
    const stopFollowing = followContainerSize(cy, element);
    cyRef.current = cy;
    return () => {
      DARK.removeEventListener("change", restyle);
      stopFollowing();
      cy.destroy();
      cyRef.current = null;
    };
  }, [data]);

  // Filters: tools and layers.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.nodes().forEach((node) => {
        const kind = node.data("kind") as string;
        const hiddenByLayer = (Object.keys(LAYERS) as Layer[]).some((layer) => !layers[layer] && LAYERS[layer].has(kind));
        node.toggleClass("hidden", hiddenSources.has(node.data("source")) || hiddenByLayer);
      });
    });
  }, [hiddenSources, layers, data]);

  // Selection: highlight a node and its neighborhood.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const node = selected ? cy.getElementById(selected) : cy.collection();
    cy.batch(() => {
      cy.elements().removeClass("faded focus show-label").unselect();
      if (node.empty()) return;
      const hood = node.closedNeighborhood();
      cy.elements().not(hood).addClass("faded");
      hood.nodes().addClass("show-label");
      node.connectedEdges().addClass("focus");
      node.select();
    });
    if (node.nonempty()) {
      cy.resize();
      cy.animate({ center: { eles: node }, zoom: Math.min(Math.max(cy.zoom(), SELECT_ZOOM.min), SELECT_ZOOM.max) }, { duration: 300 });
    }
  }, [selected, data]);

  // Find-in-graph: highlight matches and fit them in view.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const term = query.trim().toLowerCase();
    cy.nodes().removeClass("match");
    if (term.length < 2) return;
    const matches = cy.nodes().filter((n) => !n.hasClass("hidden") && String(n.data("label")).toLowerCase().includes(term));
    matches.addClass("match");
    if (matches.nonempty()) cy.animate({ fit: { eles: matches, padding: 80 } }, { duration: 300 });
  }, [query, data]);

  useEffect(() => {
    if (focus) setSelected(focus.id);
  }, [focus]);

  const toggleSource = (source: string) =>
    setHiddenSources((current) => {
      const next = new Set(current);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });

  return (
    <div className="split">
      <div className="graph-main">
        <div className="toolbar">
          <input
            className="search-input"
            placeholder="Find in graph… (e.g. ENG-5, retry, payments)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="chips">
            {sources.map((source) => (
              <button key={source} className={`chip ${hiddenSources.has(source) ? "off" : ""}`} onClick={() => toggleSource(source)}>
                <span className="dot" style={{ background: SOURCE_COLORS[source] }} />
                {SOURCE_LABELS[source] ?? source}
              </button>
            ))}
          </div>
          <div className="chips">
            {(Object.keys(LAYERS) as Layer[]).map((layer) => (
              <label key={layer} className="toggle">
                <input type="checkbox" checked={layers[layer]} onChange={() => setLayers({ ...layers, [layer]: !layers[layer] })} />
                {LAYER_LABELS[layer]}
              </label>
            ))}
            <button className="ghost" onClick={() => cyRef.current?.fit(undefined, 40)}>Fit</button>
          </div>
        </div>
        <ErrorNote message={error} />
        {loading && !data && <div className="muted pad">Loading graph…</div>}
        {data && data.nodes.length === 0 && (
          <Empty>
            The graph is empty. Connect your tools in <a href="#/setup">Setup</a>, then press Sync now.
          </Empty>
        )}
        <div ref={container} className="canvas" />
        {data && data.nodes.length > 0 && (
          <div className="graph-footer muted small">
            {data.nodes.length} nodes · {data.edges.length} links · solid accent lines are cross-tool references · dashed lines were found by
            the LLM
          </div>
        )}
      </div>
      {selected && <NodePanel key={selected} nodeId={selected} onSelect={setSelected} onClose={() => setSelected(null)} />}
    </div>
  );
}
