# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## What this is

realmarket-mcp is an open-source MCP server that lets LLMs research markets from verified,
sourced numbers: returns, drawdowns, inflation-adjusted returns and data-quality checks.
It ships code, never data, and produces research, never investment advice.

Read before changing anything: `docs/design.md` (scope, architecture, milestones) and
`docs/tool-contract.md` (the response shape every tool must follow).

## Commands

```bash
python -m pip install -e ".[dev]"   # install package + dev tools
python -m pytest -q                 # full suite, offline
python -m ruff check .              # lint
python -m ruff format --check .     # formatting
python -m mypy                      # strict type check of src/
```

All four must pass before a commit. A PostToolUse hook (`.claude/hooks/format_python.sh`)
runs `ruff format` and `ruff check --fix` on every Python file Claude writes.

## Rules

- **Contract first.** Tools return `contract.ToolResult` or raise `contract.ToolError`. Never
  return a bare dict, never put NaN in output, never omit provenance.
- **Compute in code.** Tools return finished figures; the model interprets them.
- **Flag, don't repair.** Data problems become `QualityFlag`s; never fill, interpolate or
  clip silently.
- **Network only in `providers/`.** Tests are offline (`tests/conftest.py` blocks sockets);
  providers are tested against fixtures in `tests/fixtures/<provider>/`.
- **No advice language** anywhere a user or model can read it: tool descriptions, prompts,
  README, result text.
- **Secrets only from environment variables** (`REALMARKET_<PROVIDER>_API_KEY`).
- **English** for identifiers, comments and docs.
- Keep dependencies minimal; each new runtime dependency needs an Apache-2.0-compatible license.

## Development agents and skills

Project subagents live in `.claude/agents/`; delegate to them rather than doing their job inline.

| Agent | Use it for |
|---|---|
| `tool-designer` | designing or reviewing a tool's name, description, arguments, output and errors |
| `data-integrity-reviewer` | reviewing provider, normalization and calculation code for wrong numbers |
| `test-engineer` | writing offline, hand-computable tests |
| `compliance-reviewer` | provider terms, bundled data, secrets, licenses, advice language |

Workflows in `.claude/skills/` chain them together:

- `add-mcp-tool` — design → implement → test → review → verify, for any tool change.
- `add-data-provider` — terms check → implement → fixtures → test → integrity review.

## Layout

```
src/realmarket_mcp/
  contract.py      response envelope, errors, quality flags (implemented)
  providers/       network access, one module per provider        (M1+)
  store/           normalization, data_version, cache            (M2)
  quality/         gap / seam / placeholder-bar detection        (M2)
  analytics/       pure metric functions                         (M1+)
  tools/           MCP tool implementations                      (M1+)
  server.py        MCP server entry point                        (M1)
docs/              design, tool contract, providers
tests/             offline pytest suite
```
