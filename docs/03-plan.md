# 03 · Plan

## Milestones

| # | Milestone | Done when | Status |
|---|---|---|---|
| M1 | Foundations: package, config, domain types | Settings load from `.env` + `settings.json`; unit tests pass | Done |
| M2 | Ingest: six source definitions, PyAirbyte runner, raw store | `cg check` passes for all six; first pull lands in DuckDB | Done |
| M3 | Normalize: one normalizer per tool | Every raw stream turns into `Item`s and `PersonRecord`s; fixture tests per tool | Done |
| M4 | Graph: identity, builder, linker, SQLite store | Structural and reference edges built; store round-trips; search works | Done |
| M5 | Code + enrichment: Graphify AST, PR file lists, Claude Code enricher with cache, concept merging | Files, functions and calls in the graph; topics/decisions with verified quotes; one node per decision | Done |
| M6 | Interfaces: query service, REST API, MCP server, CLI, scheduler | API tests pass; MCP tools answer; `cg sync` runs end to end | Done |
| M7 | UI: graph explorer, search, setup screen, sync status | Graph visible in the browser; all six tools show connected | Done |
| M8 | Verification | Unit suite green; acceptance check from `01-requirements.md` passes on real data | Done |
| M9 | Install and agent access: `install.sh`, data in `~/.context-graph`, `cg ask` and agent commands, skill for Claude Code and Codex, Setup page as landing | A fresh clone installs with one script; `cg` runs from any folder; the skill is added and removed cleanly | Done |

## Test strategy
- **Unit:** pure modules (normalizers, matchers, identity, builder, store, query) tested with small synthetic fixtures shaped like real records.
- **Contract:** each `SourceDefinition` builds a config that satisfies its connector's JSON schema.
- **API:** FastAPI `TestClient` against a temporary graph.
- **End to end:** a real `cg sync` on a demo workspace, then a private check (kept with that workspace's data, not in the repo) asserts the eight links listed in the requirements.
- **Install:** `install.sh --yes --no-setup` from a copy of the repo with a temporary `HOME`; then `cg` from another folder, the web app from the installed package, and adding and removing the skill.

## Risks

| Risk | Mitigation |
|---|---|
| A connector's stream schema differs from what a normalizer expects | Normalizers read fields defensively; contract and fixture tests; per-source failures are isolated |
| Gmail token expires after 7 days (Testing mode) | The sync bar names the failing tool; "Sign in again" on the Setup page refreshes it |
| LLM enrichment is slow or unavailable | Optional step; the cache avoids repeats; the graph is complete without it |
| Personal Gmail adds noise | Only Primary-inbox mail after `start_date` is kept (promotions, social, updates, spam and trash are skipped) |
