#!/usr/bin/env bash
# Build the double-click installer for a tool.
#
#   ./pack.sh time-log      ->  dist/time-log.mcpb
#
# Attach the .mcpb to a GitHub Release. Anyone who downloads and opens it gets
# an install dialog in Claude Desktop — no terminal, no Python, no config file.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="${1:-}"

if [ -z "$TOOL" ] || [ ! -f "$ROOT/tools/$TOOL/manifest.json" ]; then
  echo "usage: ./pack.sh <tool>   (needs tools/<tool>/manifest.json)"
  echo "available:"; ls -1 "$ROOT/tools" | sed 's/^/  /'
  exit 1
fi

mkdir -p "$ROOT/dist"
npx -y @anthropic-ai/mcpb@2 validate "$ROOT/tools/$TOOL/manifest.json"
npx -y @anthropic-ai/mcpb@2 pack "$ROOT/tools/$TOOL" "$ROOT/dist/$TOOL.mcpb"
