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
    ./install.sh time-log

Registers the MCP server in `claude_desktop_config.json` (backing up the old
one) and packages the skill zip for Settings > Capabilities > Skills. Requires
[uv](https://docs.astral.sh/uv/getting-started/installation/). Updating is
`git pull`; data lives outside the repo, so a pull never touches it.

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
