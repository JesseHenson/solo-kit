#!/usr/bin/env bash
# Install one tool from this repo into Claude Desktop.
#
#   ./install.sh time-log
#
# Registers the MCP server in claude_desktop_config.json and packages the skill
# as a zip for Settings > Capabilities > Skills > Upload.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="${1:-}"
CLIENT="${2:---claude}"
CONFIG="${CLAUDE_DESKTOP_CONFIG:-$HOME/Library/Application Support/Claude/claude_desktop_config.json}"

available() { ls -1 "$ROOT/tools"; }

if [ -z "$TOOL" ] || [ ! -d "$ROOT/tools/$TOOL" ]; then
  echo "usage: ./install.sh <tool> [--claude|--codex]"
  echo "  --claude  Claude Desktop (default)"
  echo "  --codex   Codex CLI and the ChatGPT desktop app, which share one config"
  echo "available:"; available | sed 's/^/  /'
  exit 1
fi

command -v uv >/dev/null || {
  echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
}

SERVER_PATH="$ROOT/tools/$TOOL/server.py"

# Codex CLI and the ChatGPT app read the same ~/.codex/config.toml
if [ "$CLIENT" = "--codex" ]; then
  CODEX="${CODEX_CONFIG:-$HOME/.codex/config.toml}"
  mkdir -p "$(dirname "$CODEX")"
  touch "$CODEX"
  if grep -q "^\[mcp_servers\.$TOOL\]" "$CODEX"; then
    echo "'$TOOL' is already in $CODEX — leaving it alone."
  else
    cp "$CODEX" "$CODEX.bak" 2>/dev/null || true
    printf '\n[mcp_servers.%s]\ncommand = "uv"\nargs = ["run", "--script", "%s"]\n' \
      "$TOOL" "$SERVER_PATH" >> "$CODEX"
    echo "Added '$TOOL' to $CODEX"
  fi
  cat <<EOF

Restart Codex (or the ChatGPT app) and it'll pick the server up. Equivalent
one-liner if you'd rather let Codex write its own config:

  codex mcp add $TOOL -- uv run --script $SERVER_PATH

Note: Codex doesn't support MCP prompts, so the "Draft an invoice" style
shortcuts won't appear. Everything else — tools, guides, instructions — works.
EOF
  exit 0
fi

if [ ! -e "$CONFIG" ]; then
  case "$(uname -s)" in
    Darwin) mkdir -p "$(dirname "$CONFIG")"; echo '{}' > "$CONFIG" ;;
    *) echo "Can't find $CONFIG. On Windows it's %APPDATA%\\Claude\\claude_desktop_config.json;" >&2
       echo "set CLAUDE_DESKTOP_CONFIG to its path and re-run." >&2; exit 1 ;;
  esac
fi

SERVER="$ROOT/tools/$TOOL/server.py"

# --- 1. register the MCP server, leaving every other key alone -------------
cp "$CONFIG" "$CONFIG.bak"
TOOL="$TOOL" SERVER="$SERVER" CONFIG="$CONFIG" uv run --quiet python - <<'PY'
import json, os, pathlib
config = pathlib.Path(os.environ["CONFIG"])
data = json.loads(config.read_text() or "{}")
servers = data.setdefault("mcpServers", {})
servers[os.environ["TOOL"]] = {
    "command": "uv",
    "args": ["run", "--script", os.environ["SERVER"]],
}
config.write_text(json.dumps(data, indent=2) + "\n")
PY
echo "Registered '$TOOL' in $(basename "$CONFIG") (previous copy at $CONFIG.bak)"

# --- 2. package the skill, folder at the zip root -------------------------
if [ -d "$ROOT/tools/$TOOL/skill" ]; then
  rm -rf "$ROOT/dist/stage" && mkdir -p "$ROOT/dist/stage"
  cp -R "$ROOT/tools/$TOOL/skill" "$ROOT/dist/stage/$TOOL"
  (cd "$ROOT/dist/stage" && zip -qr "../$TOOL-skill.zip" "$TOOL")
  rm -rf "$ROOT/dist/stage"
  echo "Packaged dist/$TOOL-skill.zip"
fi

cat <<EOF

Two steps left, both in Claude Desktop:

  1. Quit and reopen it, so it picks up the new MCP server.
  2. Settings > Capabilities > Skills > Upload, and pick:
     $ROOT/dist/$TOOL-skill.zip

Then ask it something like "start a timer for Acme".
EOF
