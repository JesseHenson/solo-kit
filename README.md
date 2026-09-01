# solo-kit

Small tools that replace a SaaS subscription with a skill, an MCP server, and a
plaintext file. One folder per tool. Clone the repo, run the installer, done.

## Install a tool

    git clone https://github.com/JesseHenson/solo-kit.git
    cd solo-kit
    ./install.sh time-log

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/); no other
runtime to set up. The installer registers the MCP server in Claude Desktop's
config (backing up the old one) and packages the skill as a zip. It then tells
you the two manual steps Claude Desktop still requires: restart the app, and
upload the zip under **Settings > Capabilities > Skills**.

Updating is `git pull`. Data lives outside the repo, so a pull can never touch it.

## Tools

| Tool | Does | Replaces |
|---|---|---|
| [time-log](tools/time-log) | Timer + timesheet over a JSONL file | QuickBooks Time ($20/mo + $8/user, atop a $75/mo QBO plan) |

## Adding a tool

A tool is a folder under `tools/` with two things in it:

    tools/<name>/
      server.py           MCP server, a single uv script with PEP 723 deps
      skill/SKILL.md      the skill, folder name = skill name

`install.sh` is generic — it reads the folder, so nothing here needs editing
when a tool is added. Keep each tool to one file of server code and one skill;
anything that needs a build step or a deploy target belongs in its own repo
instead.

Run a tool's tests with:

    cd tools/<name> && uv run --with mcp --with pytest pytest -q
