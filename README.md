# solo-kit

Small tools that replace a SaaS subscription with an MCP server, a skill, and a
plaintext file you own. One folder per tool.

## For the person you're giving it to

Send them one link — the `.mcpb` file from a release:

1. Download `time-log.mcpb`
2. Double-click it. Claude Desktop shows an install dialog; they pick where the
   data lives and hit Install.

That's it. No terminal, no Python, no config file, no separate skill upload —
Claude Desktop's bundle runtime supplies uv and the dependencies, and the
server hands Claude its own usage instructions on connect.

## For yourself, or a technical client

    git clone https://github.com/JesseHenson/solo-kit.git
    cd solo-kit
    ./install.sh time-log            # Claude Desktop
    ./install.sh time-log --codex    # Codex CLI and the ChatGPT app

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and
nothing else. Updating is `git pull` — the config points at the repo, so there
is no reinstall. Data lives outside the repo, so a pull never touches it.

This is the better path if you have it. The bundle exists because Claude Desktop
has no other install route; a clone updates in place and works everywhere.

## Where these run

| Client | How | Caveat |
|---|---|---|
| Claude Code | `./install.sh` or a clone | — |
| Claude Desktop | `.mcpb` bundle, or `./install.sh` | Reinstall to update |
| Codex CLI | `./install.sh --codex` | No MCP prompts |
| ChatGPT desktop app | Same config as Codex | No MCP prompts |

An MCP server is an MCP server. The tools, the guides, and the server's own
instructions travel to all of them; only the packaging differs.

## Tools

| Tool | Does | Replaces |
|---|---|---|
| [time-log](tools/time-log) | Timer + timesheet over a JSONL file | QuickBooks Time ($20/mo + $8/user, atop a $75/mo QBO plan) |

## Adding a tool

Three files under `tools/<name>/`:

    server.py           MCP server, a single uv script with PEP 723 deps
    skill/SKILL.md      the usage guidance, folder name = skill name
    manifest.json       bundle metadata; copy time-log's and edit the strings

`install.sh` and `pack.sh` are both generic over `tools/`, so nothing here needs
editing when a tool is added.

**SKILL.md is the only copy of the usage guidance.** `server.py` reads it at
startup and sends it as the MCP server's `instructions`, so a bundle install
gets the same text without a skill upload. Don't restate it in the manifest.

Keep each tool to one file of server code and one skill. Anything needing a
build step or a deploy target belongs in its own repo instead.

    ./pack.sh time-log       # -> dist/time-log.mcpb, attach to a release
    cd tools/time-log && uv run --with mcp --with pytest pytest -q
