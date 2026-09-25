"""Stage the Claude Desktop extension (.mcpb) from this repository.

    python scripts/build_mcpb.py            # writes build/mcpb/ (manifest + sources + uv.lock)
    npx -y @anthropic-ai/mcpb validate build/mcpb/manifest.json
    npx -y @anthropic-ai/mcpb pack build/mcpb dist/realmarket-<version>.mcpb

The manifest is generated from the code (version, tools, prompts) so the bundle cannot drift
from the server it ships. It uses the MCPB ``uv`` server type: the host installs the
dependencies from ``pyproject.toml`` (pinned by ``uv.lock``), so the bundle carries no
Python packages and needs no Python on the user's machine.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import anyio

from realmarket_mcp import __version__
from realmarket_mcp.config import USE_YAHOO_ENV
from realmarket_mcp.providers import cpi, sec
from realmarket_mcp.server import build_server

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/itu-itis24-iyigun24/realmarket-mcp"
# What the bundle needs to build and run the package; tests, docs and dev tooling stay out.
INCLUDE = ("pyproject.toml", "README.md", "LICENSE", "src/realmarket_mcp")

USER_CONFIG: dict[str, dict[str, Any]] = {
    "use_yahoo": {
        "type": "boolean",
        "title": "Use Yahoo Finance (unofficial)",
        "description": "Prices, FX, gold and non-US company statements from Yahoo Finance. "
        "Yahoo's terms prohibit automated access without its permission; you take "
        "responsibility for your use. Off by default. Restart the app after changing it.",
        "required": False,
        "default": False,
    },
    "sec_contact": {
        "type": "string",
        "title": "E-mail for SEC EDGAR (optional)",
        "description": "The SEC requires a contact e-mail in automated requests. With it, US "
        "companies' financial statements come from their official filings. No sign-up needed.",
        "required": False,
    },
    "evds_api_key": {
        "type": "string",
        "title": "TCMB EVDS API key (optional)",
        "description": "Most current Turkish CPI. Without it Turkish inflation comes from the "
        "OECD, which can lag.",
        "required": False,
        "sensitive": True,
    },
    "fred_api_key": {
        "type": "string",
        "title": "FRED API key (optional)",
        "description": "US CPI through the FRED API (agreeing to the FRED API Terms of Use). "
        "Not needed: the OECD gives the same BLS data without a key.",
        "required": False,
        "sensitive": True,
    },
}
# Services that receive user data: the SEC gets the user's e-mail (User-Agent), the rest get
# query text (symbols, dates, search terms) and keys where set. GDELT publishes no privacy
# policy; it receives only the news search text. Sources for each URL: docs/providers.md.
PRIVACY_POLICIES = [
    "https://www.sec.gov/about/privacy-information",
    "https://legal.yahoo.com/us/en/yahoo/privacy/index.html",
    "https://www.stlouisfed.org/about-us/privacy-policy",
    "https://evds3.tcmb.gov.tr/igmevdsms-dis/documents/showDocument?docId=22",
    "https://www.oecd.org/en/about/privacy.html",
]
ENV = {
    USE_YAHOO_ENV: "${user_config.use_yahoo}",
    sec.CONTACT_ENV: "${user_config.sec_contact}",
    cpi.EVDS_KEY_ENV: "${user_config.evds_api_key}",
    cpi.FRED_KEY_ENV: "${user_config.fred_api_key}",
}


def _first_sentence(text: str) -> str:
    flat = " ".join(text.split())
    end = flat.find(". ")
    return flat if end < 0 else flat[: end + 1]


def _prompt(server: Any, prompt: Any) -> dict[str, Any]:
    """The server's own prompt text, rendered with the manifest's ``${arguments.x}`` slots, so
    a host that reads the manifest says exactly what the server would."""
    names = [a.name for a in prompt.arguments or []]
    rendered = anyio.run(server.get_prompt, prompt.name, {n: f"${{arguments.{n}}}" for n in names})
    text = "\n\n".join(m.content.text for m in rendered.messages)
    return {
        "name": prompt.name,
        "description": prompt.description or "",
        "arguments": names,
        "text": text,
    }


def manifest() -> dict[str, Any]:
    server = build_server()
    tools = anyio.run(server.list_tools)
    prompts = anyio.run(server.list_prompts)
    return {
        "manifest_version": "0.4",
        "name": "realmarket",
        "display_name": "realmarket",
        "version": __version__,
        "description": "Market research from verified, sourced numbers: real returns vs "
        "inflation, in US dollars and gold; data-quality checks; company financials; news.",
        "long_description": (
            "realmarket gives Claude tools that compute market figures in code and return them "
            "with their sources: nominal and inflation-adjusted returns, the same holding "
            "measured in US dollars and in gold, data-quality flags, company financial "
            "statements (official SEC filings for US companies), event reactions and news "
            "listings. It ships no market data: it fetches from providers under your own "
            "access, and you agree to each provider's terms (listed in the README), including "
            "the FRED® API Terms of Use (https://fred.stlouisfed.org/docs/api/terms_of_use.html)"
            " when a FRED key is set. This product uses the FRED® API but is not endorsed or "
            "certified by the Federal Reserve Bank of St. Louis. Not investment advice."
        ),
        "privacy_policies": PRIVACY_POLICIES,
        "author": {"name": "realmarket-mcp contributors", "url": REPO_URL},
        "repository": {"type": "git", "url": REPO_URL},
        "homepage": REPO_URL,
        "support": f"{REPO_URL}/issues",
        "license": "Apache-2.0",
        "keywords": ["markets", "inflation", "real return", "financial statements", "stocks"],
        "server": {
            "type": "uv",
            "entry_point": "src/realmarket_mcp/server.py",
            "mcp_config": {
                "command": "uv",
                "args": [
                    "run",
                    "--directory",
                    "${__dirname}",
                    "--frozen",
                    "--no-dev",
                    "--extra",
                    "yahoo",
                    "realmarket-mcp",
                ],
                "env": ENV,
            },
        },
        "tools": [
            {"name": t.name, "description": _first_sentence(t.description or "")} for t in tools
        ],
        "prompts": [_prompt(server, p) for p in prompts],
        "compatibility": {
            "platforms": ["darwin", "win32", "linux"],
            "runtimes": {"python": ">=3.11"},
        },
        "user_config": USER_CONFIG,
    }


def stage(out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for item in INCLUDE:
        source = ROOT / item
        if source.is_dir():
            shutil.copytree(source, out / item, ignore=ignore)
        else:
            shutil.copy2(source, out / item)
    (out / "manifest.json").write_text(json.dumps(manifest(), indent=2) + "\n", encoding="utf-8")
    (out / ".mcpbignore").write_text(".venv/\n__pycache__/\n*.pyc\n", encoding="utf-8")
    # Pin every dependency version for the host's uv install.
    subprocess.run(["uv", "lock", "--directory", str(out), "--quiet"], check=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "mcpb")
    parser.add_argument("--manifest-only", action="store_true", help="print the manifest")
    args = parser.parse_args()
    if args.manifest_only:
        json.dump(manifest(), sys.stdout, indent=2)
        return 0
    print(stage(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
