# 01 · Requirements

## Goal
A personal context graph: it connects one person's work tools into a single linked graph that the person can explore visually and their AI agents can query.

## Functional requirements

| ID | Requirement |
|---|---|
| RQ1 | Build one graph per person, from their own work tools, on their own machine. |
| RQ2 | Pull data from Slack, Linear, Jira, Notion, Gmail and GitHub (issues, PRs, commits and code). |
| RQ3 | Link everything into one graph: the same person across tools, and items that reference each other across tools (issue keys, URLs, titles, file paths, function names). |
| RQ4 | Keep the graph in sync: pull only what changed, on a configurable interval, without manual steps. |
| RQ5 | Everything is free, open source and runs locally. No hosted service holds the data. |
| RQ6 | Visualise the graph: search, filter by tool and type, click a node to see its details and neighbours. |
| RQ7 | Query the graph: keyword search, node details, neighbours, paths between nodes, recent activity. Available to people (UI, CLI) and to agents (MCP). |
| RQ8 | Setup is guided: one screen shows each tool's status, the fields it needs, where to get them, and a connection test. |
| RQ9 | Install from a clone with one script. Afterwards `cg` works from any folder, and the person's data lives in one folder in their home directory, apart from the code. |
| RQ10 | `cg setup` always opens the Setup page of the web app. |
| RQ11 | Agents can query the graph from the command line: one command takes a question and returns the matching items with their links; others give an item's details, its connections, the path between two items, recent activity and sync status. |
| RQ12 | An agent skill teaches Claude Code and Codex to use those commands. It is added on request, works with whichever tools are connected, and warns (does not block) when nothing is synced yet. |

## Non-functional requirements

| ID | Requirement |
|---|---|
| NF1 | Modular: each tool, store, LLM and interface sits behind an interface and can be replaced without touching the rest. |
| NF2 | Deterministic first: links that can be derived from IDs and text patterns never depend on an LLM. The LLM only adds meaning (topics, decisions). |
| NF3 | Cheap updates: unchanged text is never sent to the LLM twice. |
| NF4 | Fault isolation: one failing tool does not stop the others from syncing. |
| NF5 | Secrets stay in `.env` on disk, are never logged or shown in full, and the local server only listens on 127.0.0.1. |
| NF6 | Tested: unit tests for every module, plus an end-to-end check on real data. |

## Out of scope (for now)
Company-wide shared graph, permissions per viewer, webhooks, hosted deployment.

## Acceptance check (mock "Acme Pay" story)
After one sync, the graph must contain these links:

1. Gmail escalation thread ↔ Jira DEMO-1 (title quoted in the ticket, key in the email).
2. Jira DEMO-1 ↔ Linear ENG-5 ↔ GitHub issue #1.
3. GitHub PR #2 → fixes Linear ENG-5 and closes GitHub issue #1.
4. Slack `#payments` thread → DEMO-1, ENG-5, PR #2, Notion "Payments retry design".
5. Notion "Payments retry design" → ENG-5…ENG-8, DEMO-1, DEMO-2, PR #2, Slack `#payments`.
6. Linear ENG-5 → code: `payments/retry.py` and `charge_with_retry`.
7. One person node for the demo user across GitHub, Linear, Jira, Notion, Slack and Gmail.
8. Unrelated items (Linear ENG-9 dark mode, Slack lunch message, Jira DEMO-3) are not linked to the payments story.
