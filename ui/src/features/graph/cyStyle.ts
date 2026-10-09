import type { StylesheetJson } from "cytoscape";
import { KIND_SHAPES, KIND_SIZE } from "./palette";

const LLM_EDGES = ["mentions", "decides", "about"];
const STRONG_EDGES = ["references", "fixes", "changes"];
/** Kinds that are numerous and small: their labels appear on hover or selection only. */
const QUIET_KINDS = ["message", "email", "comment", "symbol", "commit", "topic", "decision"];

export interface ThemeColors {
  text: string;
  edge: string;
  accent: string;
  surface: string;
}

type Element = { data: (key: string) => string };
const byKind = <T,>(table: Record<string, T>, fallback: T) => ((ele: Element) => table[ele.data("kind")] ?? fallback) as never;

/** Cytoscape stylesheet. Cytoscape only understands opaque colors, so transparency uses the *-opacity properties. */
export function buildStyle({ text, edge, accent, surface }: ThemeColors): StylesheetJson {
  return [
    {
      selector: "node",
      style: {
        "background-color": "data(color)",
        shape: byKind(KIND_SHAPES, "ellipse"),
        width: byKind(KIND_SIZE, 20),
        height: byKind(KIND_SIZE, 20),
        label: "data(label)",
        color: text,
        "font-size": 10,
        "text-valign": "bottom",
        "text-margin-y": 4,
        "text-wrap": "ellipsis",
        "text-max-width": "130px",
        "text-background-color": surface,
        "text-background-opacity": 0.7,
        "text-background-padding": "1px",
        "border-width": 1.5,
        "border-color": surface,
        "border-opacity": 0.6,
        "overlay-opacity": 0,
      },
    },
    { selector: QUIET_KINDS.map((k) => `node[kind = "${k}"]`).join(","), style: { "text-opacity": 0, "text-background-opacity": 0 } },
    {
      selector: "edge",
      style: {
        width: 1,
        "line-color": edge,
        "target-arrow-color": edge,
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.6,
        "curve-style": "bezier",
        opacity: 0.55,
      },
    },
    {
      selector: STRONG_EDGES.map((k) => `edge[kind = "${k}"]`).join(","),
      style: { width: 1.8, "line-color": accent, "target-arrow-color": accent, opacity: 0.85 },
    },
    { selector: LLM_EDGES.map((k) => `edge[kind = "${k}"]`).join(","), style: { "line-style": "dashed", opacity: 0.4 } },
    { selector: ".hidden", style: { display: "none" } },
    { selector: ".faded", style: { opacity: 0.12, "text-opacity": 0, "text-background-opacity": 0 } },
    { selector: ".show-label, .hover", style: { "text-opacity": 1, "text-background-opacity": 0.7, "z-index": 10 } },
    { selector: ".match", style: { "border-width": 4, "border-color": "#facc15", "border-opacity": 1, "text-opacity": 1 } },
    { selector: "node:selected", style: { "border-width": 4, "border-color": accent, "border-opacity": 1, "text-opacity": 1, "z-index": 20 } },
    { selector: "edge.focus", style: { opacity: 1, width: 2.2 } },
  ];
}
