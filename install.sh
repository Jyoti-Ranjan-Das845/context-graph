#!/usr/bin/env bash
# Installs Context Graph: builds the web app, installs the `cg` command, and walks you to Setup.
# Safe to run again to update. Options: --yes (accept every default), --no-setup (don't open Setup).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${CONTEXT_GRAPH_HOME:-$HOME/.context-graph}"
PORT=8765
ASSUME_YES=0
OPEN_SETUP=1
for arg in "$@"; do
  case "$arg" in
    --yes|-y) ASSUME_YES=1 ;;
    --no-setup) OPEN_SETUP=0 ;;
    *) echo "Unknown option: $arg (use --yes or --no-setup)"; exit 2 ;;
  esac
done

step() { printf '\n\033[1m%s\033[0m\n' "$1"; }
fail() { printf '\n✗ %s\n' "$1" >&2; exit 1; }
confirm() {  # confirm "Question?" -> yes by default
  [[ $ASSUME_YES == 1 ]] && return 0
  local reply=""
  read -r -p "$1 [Y/n] " reply </dev/tty || true
  [[ -z "$reply" || "$reply" =~ ^[Yy] ]]
}

step "1/5 Checking what's needed"
command -v uv >/dev/null || fail "uv is not installed. Install it (https://docs.astral.sh/uv/) with:
  curl -LsSf https://astral.sh/uv/install.sh | sh
then run ./install.sh again."
command -v npm >/dev/null || fail "Node.js is not installed. Install Node.js 18 or newer (https://nodejs.org); it's only used to build the web app."
node_major="$(node -p 'process.versions.node.split(".")[0]')"
(( node_major >= 18 )) || fail "Node.js $node_major is too old; the web app needs 18 or newer."
[[ "$(uname)" == "Darwin" ]] || echo "Note: background sync uses macOS launchd; on this system run \`cg sync\` yourself or from cron."
echo "✓ uv, Node.js $node_major"

step "2/5 Building the web app"
npm --prefix "$ROOT/ui" install --no-audit --no-fund --loglevel=error
npm --prefix "$ROOT/ui" run build --silent >/dev/null
echo "✓ Built into the package"

step "3/5 Installing the cg command"
uv tool install --reinstall --quiet --python 3.12 "$ROOT/backend"
BIN_DIR="$(uv tool dir --bin)"
CG="$BIN_DIR/cg"
[[ -x "$CG" ]] || fail "cg was not installed into $BIN_DIR."
echo "✓ cg installed in $BIN_DIR"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    if confirm "Add $BIN_DIR to your PATH (in your shell profile) so \`cg\` works in new terminals?"; then
      uv tool update-shell --quiet && echo "✓ Open a new terminal to use \`cg\` by name."
    else
      echo "  Skipped. Run cg as $CG, or add $BIN_DIR to your PATH."
    fi
    ;;
esac

step "4/5 Your data folder: $HOME_DIR"
mkdir -p "$HOME_DIR" && chmod 700 "$HOME_DIR"
old=()
for item in .env settings.json data; do
  [[ -e "$ROOT/$item" && ! -e "$HOME_DIR/$item" ]] && old+=("$item")
done
if (( ${#old[@]} )); then
  if confirm "Found data from an earlier version in this folder (${old[*]}). Move it to $HOME_DIR?"; then
    for item in "${old[@]}"; do mv "$ROOT/$item" "$HOME_DIR/"; done
    echo "✓ Moved ${old[*]}"
  fi
fi
echo "✓ Keys, settings and the graph live here, apart from the code"

step "5/5 AI agents"
if confirm "Add the context-graph skill to Claude Code and Codex, so they can look up your work with \`cg\`?"; then
  "$CG" agent install || echo "  You can add it later from the Setup page or with \`cg agent install\`."
else
  echo "  Skipped. Add it later from the Setup page or with \`cg agent install\`."
fi

echo
if curl -fs "http://127.0.0.1:$PORT/api/stats" >/dev/null 2>&1; then
  echo "Context Graph is already running from an earlier start. Stop it (Ctrl+C in its window), then run: cg setup"
elif [[ $OPEN_SETUP == 1 ]] && confirm "Open Setup now to connect your tools?"; then
  exec "$CG" setup
else
  echo "Done. Next: cg setup"
fi
