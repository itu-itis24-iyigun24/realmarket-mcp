"""Build the sales demo page from recorded, unedited model answers."""

import html
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
firm = json.loads((HERE / "recordings" / "answers.json").read_text())
bare = json.loads((HERE / "recordings" / "no-tools.json").read_text())

LABELS = {
    "getiri": "Getiri",
    "enflasyon": "Enflasyon",
    "altin": "Altınla kıyas",
    "portfoy": "Portföyüm",
    "birikim": "Düzenli birikim",
    "ucuz": "Ucuz mu?",
    "bilanco": "Bilanço",
    "neden": "Neden düştü?",
    "tavsiye": "Almalı mıyım?",
    "kapsam": "Kapsam dışı",
}
TOOL_TR = {
    "get_price_summary": "Fiyat özeti",
    "compare_real_return": "Reel getiri",
    "compare_assets": "Varlık karşılaştırma",
    "analyze_portfolio": "Portföy analizi",
    "portfolio_real_return": "Birikim ve alternatifler",
    "get_valuation": "Değerleme ve sektör kıyası",
    "get_financials": "Finansal tablolar",
    "explain_price_move": "Seans hareketi",
}
NOTES = {
    "tavsiye": "Model hiçbir araç çağırmadan tavsiyeyi reddetti. Hüküm yok, yönlendirme yok.",
    "kapsam": (
        "Veri bu hizmette yok. Model hafızasından faiz oranı uydurmadı, ayar adı da söylemedi."
    ),
    "neden": "Seansın rakamları var, bir neden yok. Hareket piyasaya ya da habere bağlanmadı.",
    "ucuz": 'Oran ve sektördeki yeri verildi; "ucuz" ya da "pahalı" denmedi.',
}


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    return text


def markdown(text: str) -> str:
    """The small subset the model writes: paragraphs, bold, italics, one or two list levels."""
    out, stack = [], []

    def close_to(depth: int) -> None:
        while len(stack) > depth:
            out.append(f"</{stack.pop()}>")

    for raw in text.strip().splitlines():
        line = raw.rstrip()
        if not line.strip():
            close_to(0)
            continue
        m = re.match(r"^(\s*)([*-]|\d+\.)\s+(.*)$", line)
        if m:
            depth = 1 if len(m.group(1)) < 2 else 2
            tag = "ol" if m.group(2)[0].isdigit() else "ul"
            if len(stack) < depth:
                while len(stack) < depth:
                    out.append(f"<{tag}>")
                    stack.append(tag)
            else:
                close_to(depth)
            out.append(f"<li>{inline(m.group(3))}</li>")
        elif stack and raw[:1].isspace() and out[-1].endswith("</li>"):
            out[-1] = out[-1][: -len("</li>")] + "<br>" + inline(line.strip()) + "</li>"
        else:
            close_to(0)
            out.append(f"<p>{inline(line.strip())}</p>")
    close_to(0)
    return "\n".join(out)


def excerpt(text: str, keep: list[int]) -> str:
    """Selected paragraphs of an answer, in order, with the cut marked."""
    parts = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    chosen = [markdown(parts[i]) for i in keep]
    return '\n<p class="cut">[…]</p>\n'.join(chosen)


cases = []
for c in firm["cases"]:
    calls = [x for x in c["calls"] if x["tool"] != "search_assets"]
    facts = [f for x in calls for f in x["response"].get("facts", [])]
    cases.append(
        {
            "id": c["id"],
            "label": LABELS[c["id"]],
            "question": c["question"],
            "answer": markdown(c["answer"]),
            "tools": [TOOL_TR.get(x["tool"], x["tool"]) for x in calls],
            "facts": len(facts),
            "fact": html.escape(facts[0]) if facts else "",
            "note": NOTES.get(c["id"], ""),
        }
    )

contrast_q = bare["neden"]["question"]
contrast_a = excerpt(bare["neden"]["answer"], [0, 2, 3])
advice_a = excerpt(bare["yatirim"]["answer"], [1, 2, 3, 6])
with_tools = next(c for c in cases if c["id"] == "neden")["answer"]

page = (HERE / "template.html").read_text()
page = page.replace("/*CASES*/[]", json.dumps(cases, ensure_ascii=False))
page = page.replace("<!--CONTRAST_Q-->", html.escape(contrast_q))
page = page.replace("<!--CONTRAST_A-->", contrast_a)
page = page.replace("<!--ADVICE_Q-->", html.escape(bare["yatirim"]["question"]))
page = page.replace("<!--ADVICE_A-->", advice_a)
page = page.replace("<!--WITH_TOOLS-->", with_tools)
(HERE / "realmarket-demo.html").write_text(page)
print("written", len(page))
