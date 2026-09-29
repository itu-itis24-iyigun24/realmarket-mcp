"""Write the demo's fictional dataset for the example adapter.

ORNEK, its index, USD/TRY, gold and a monthly CPI come from realmarket-qualify's synthetic
generator; this adds Turkish names, the adapter's /meta (declaring financials and peers) and
a peer list of fictional retailers, so the demo runs in the firm's mode exactly as a
brokerage's deployment would. Nothing here is market data.

    python examples/demo/make_data.py examples/demo/data
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from realmarket_mcp import qualify

TODAY = dt.date(2026, 9, 29)  # the date the recorded answers were made
NAMES = {
    "ORNEK": "Örnek Perakende A.Ş. (kurgusal)",
    "IDX": "Örnek Endeks (kurgusal)",
    "USDTRY": "Dolar/TL",
    "GOLD": "Altın (ons, USD)",
}
# Fictional retailers; ORNEK's price-to-book matches the ratio computed from its statements.
PEERS = [
    ("ORNEK", "Örnek Perakende A.Ş. (kurgusal)", 9.05, 4.0157e11),
    ("KMRKT", "Kuzey Market A.Ş. (kurgusal)", 4.8, 1.9e11),
    ("GNYPR", "Güney Perakende A.Ş. (kurgusal)", 6.3, 2.6e11),
    ("DOGUM", "Doğu Mağazaları A.Ş. (kurgusal)", 11.6, 5.2e11),
    ("BATIM", "Batı Market A.Ş. (kurgusal)", 3.4, 0.9e11),
    ("MRKZP", "Merkez Perakende A.Ş. (kurgusal)", 7.9, 3.3e11),
    ("KYPZR", "Köy Pazarı A.Ş. (kurgusal)", 13.2, 1.4e11),
]


def main(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    qualify.write_dataset(root, TODAY)
    assets = json.loads((root / "assets.json").read_text(encoding="utf-8"))
    for asset in assets:
        asset["name"], asset["exchange"] = NAMES[asset["symbol"]], "DEMO"
    (root / "assets.json").write_text(json.dumps(assets, ensure_ascii=False, indent=1))
    meta = {
        "api_version": 1,
        "name": "demo",
        "attribution": "Demo verisi: kurgusal ORNEK şirketi ve sentetik piyasa serileri.",
        "gold_usd_symbol": "GOLD",
        "fx_symbol": "{base}{quote}",
        "benchmarks": {"TRY": "IDX"},
        "endpoints": ["financials", "peers"],
    }
    (root / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
    body = {
        "industry": "Gıda perakendesi",
        "group": "Gıda perakendesi",
        "market": "Borsa İstanbul (demo)",
        "definition": "Piyasa değeri / son bilanço özsermayesi (demo verisi)",
        "peers": [
            {"symbol": s, "name": n, "price_to_book": pb, "market_cap": cap,
             "currency": "TRY", "financial_currency": "TRY"}
            for s, n, pb, cap in PEERS
        ],
    }  # fmt: skip
    sector = {**body, "industry": "Perakende", "group": "Perakende"}
    (root / "peers").mkdir(exist_ok=True)
    (root / "peers" / "ORNEK.json").write_text(
        json.dumps({"industry": body, "sector": sector}, ensure_ascii=False)
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
