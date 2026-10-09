# Context Graph

A personal context graph. It pulls your work from Slack, Linear, Jira, Notion, Gmail and GitHub (issues, pull requests and code) and links it into one graph on your computer. You explore it in a local web app; your AI agents query it from the command line.

Everything runs locally and is free. Your keys and data stay in `~/.context-graph`, and the web app only listens on 127.0.0.1.

## Requirements

- macOS (background sync uses launchd; everything else also works on Linux)
- [uv](https://docs.astral.sh/uv/), which installs Python for you
- Node.js 18 or newer, only to build the web app during install
- [Claude Code](https://claude.com/claude-code), optional: it adds topics and decisions using your Claude plan, no API key

## Install

```bash
git clone https://github.com/Jyoti-Ranjan-Das845/context-graph.git && cd context-graph && ./install.sh
```

The script builds the web app and installs the `cg` command so it works from any folder. It asks before changing anything outside this folder: adding `cg` to your PATH, and adding the agent skill. At the end it opens Setup.

To update, pull and run `./install.sh` again. Your data is kept.

## Set up

```bash
cg setup
```

This opens the Setup page in your browser, every time you run it:

1. **Connect your tools.** Each tool's card has the steps, a link to where you get its key, a **Test connection** button and its options (which repos, projects or channels). Slack has a **Create the Slack app** button; Gmail has **Sign in with Google**. Skip any tool you don't use.
2. **Choose what to sync and how often.** How far back to pull (30 days by default), the interval, background sync, and whether Claude adds topics and decisions.
3. **Sync.** The first sync takes about a minute.
4. **Connect your AI agents.** Adds the skill to Claude Code and Codex.

The web app runs while that terminal window is open. Background sync and the agent commands work without it.

## Use

`cg ui` opens the web app on the graph:

| Tab | What |
|---|---|
| **Graph** | Everything, linked. Filter by tool or layer, find an item, click it to see its text and links. |
| **Search** | Full-text search. **Agent context** shows exactly what an agent gets for a question. |
| **Setup** | Keys, options, sync settings, agents. |

On the command line, for you and for agents (add `--json` to any of them):

| Command | What it gives |
|---|---|
| `cg ask "why are customers charged twice"` | The best matches for a question, each with its links. Start here. |
| `cg search "retries" --kind decision --source slack` | Matching items only. |
| `cg show <id>` | One item in full, with all its links and the evidence for each. |
| `cg neighbors <id> --depth 2` | The items around an item. |
| `cg path <id> <id>` | How two items are connected. |
| `cg recent --hours 24` | What changed lately. |
| `cg status` | Connected tools, last sync, graph size, background sync, agents. |
| `cg sync` | Pull what changed now. |
| `cg check` | Test each tool's connection. |

### AI agents

`cg agent install` (or step 4 of Setup) adds a skill that teaches agents these commands:

- Claude Code: `~/.claude/skills/context-graph/SKILL.md`
- Codex: a marked block in `~/.codex/AGENTS.md`; the rest of that file is left alone

`cg agent remove` takes it out again. Agents that prefer MCP can run `cg mcp` instead, for example `claude mcp add context-graph -- cg mcp`.

### Gmail sign-in

While your Google sign-in app is in Testing mode, a sign-in lasts 7 days. Click **Sign in again** on the Setup page when the sync bar says Gmail failed.

## How it works

Each sync pulls only what changed (PyAirbyte, into a local DuckDB file), reads the repos' code (Graphify), and rebuilds the graph from that local copy. Links come from rules first:

- the tools' own data: authors, assignees, threads, channels, which files a PR changed
- exact mentions in text: issue keys, URLs, quoted titles, file paths and function names
- one person per human across tools, by email, account id and name

Claude Code then adds topics and decisions, each backed by a verbatim quote, and merges the ones that mean the same thing. Text it has already read is never sent again.

Details: [requirements](docs/01-requirements.md) · [spec](docs/02-spec.md) · [plan](docs/03-plan.md).

## Uninstall

1. Turn off background sync on the Setup page.
2. `cg agent remove`
3. `uv tool uninstall context-graph`
4. Delete `~/.context-graph` if you no longer want your keys and graph.

## Develop

```bash
cd backend && uv venv --python 3.12 && uv pip install -e ".[dev]" && .venv/bin/pytest
```

```bash
cd ui && npm install && npm run dev
```

`npm run dev` serves the web app on http://127.0.0.1:5173 with live reload, and forwards `/api` to a running `cg ui`. `npm run build` writes the web app into `backend/src/context_graph/web`, which the package ships.

| Folder | Contents |
|---|---|
| `backend/src/context_graph` | `domain`, `config`, `sources` (one module per tool), `ingest`, `code`, `linking`, `graph`, `enrich`, `query`, `pipeline`, `agents`, `interfaces` |
| `ui/src` | `api` (typed client), `features` (graph, search, setup, sync), `components`, `hooks` |
| `docs` | Requirements, spec, plan |

Nothing personal belongs in this repo: keys, settings, pulled data, caches and logs all live in `~/.context-graph` (or `$CONTEXT_GRAPH_HOME`).

## License

MIT. See [LICENSE](LICENSE).
