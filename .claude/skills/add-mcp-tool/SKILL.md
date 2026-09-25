---
name: add-mcp-tool
description: Step-by-step workflow for adding a new MCP tool to realmarket-mcp or changing an existing tool's public surface - design against the tool contract, implement, test offline, review. Use whenever a tool is added, renamed, or its arguments or output change.
---

# Adding or changing an MCP tool

Follow these steps in order. Do not skip the design step: the tool's surface is what every
LLM client sees, and changing it after release breaks users' prompts.

1. **Design first.** Delegate to the `tool-designer` agent with the tool's purpose. Get back
   the name, description, arguments, result `data` keys, errors with hints, quality flags and
   an example envelope. Resolve every open question before writing code.

2. **Record the design.** Add the tool to the tool table in `docs/design.md` (name, one-line
   purpose, milestone) and paste the example envelope into the tool's docstring.

3. **Implement.**
   - Put the computation in a pure function (inputs: normalized data; output: plain values),
     separate from the MCP registration code. The pure function is what tests target.
   - Return `contract.ToolResult`; raise `contract.ToolError` with a concrete `hint`.
   - Cite `Provenance` for every data source used. Surface data problems as `QualityFlag`s
     instead of silently cleaning them.
   - Never call the network outside a provider module.

4. **Test.** Delegate to the `test-engineer` agent: hand-computable calculation tests, the full
   envelope, each documented error, and the edge cases listed in its instructions.

5. **Review.** Run the reviewers that apply, in parallel:
   - `data-integrity-reviewer` if the tool computes returns, inflation, risk or reads a provider.
   - `compliance-reviewer` for the description and any user-facing text.
   - `tool-designer` again in review mode on the final code.

6. **Verify.** `python -m pytest -q`, `python -m ruff check .`, `python -m ruff format --check .`,
   `python -m mypy`. All must pass. Report the results, including anything skipped.
