"""Build the sales demo page from recorded, unedited model answers.

The page only lays the recordings out: every answer, request and sentence on it is copied
from recordings/. Highlights mark phrases the notes beside them explain; each phrase must
exist in the recording, or the build stops.
"""

import html
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
firm = json.loads((HERE / "recordings" / "answers.json").read_text())
bare = json.loads((HERE / "recordings" / "no-tools.json").read_text())

# What each calculation is, in the words a brokerage's product team uses.
CALCULATION = {
    "get_price_summary": "Getiri hesabı",
    "compare_real_return": "Enflasyona göre getiri hesabı",
    "compare_assets": "Varlık karşılaştırması",
    "analyze_portfolio": "Portföy hesabı",
    "portfolio_real_return": "Birikim ve alternatifler hesabı",
    "get_valuation": "Değerleme oranları ve sektör kıyası",
    "get_financials": "Finansal tablo özeti",
    "explain_price_move": "Seans özeti",
}
NOTES = {
    "tavsiye": "Asistan realmarket'e hiç başvurmadan tavsiyeyi reddetti.",
    "kapsam": (
        "Bu veri hizmette yok. Asistan hafızasından bir faiz oranı söylemedi, "
        "teknik ayar adı da vermedi."
    ),
    "neden": "Seansın rakamları var, neden yok. Hareket piyasaya ya da habere bağlanmadı.",
    "ucuz": "Oran ve sektördeki yeri verildi; ucuz ya da pahalı denmedi.",
    "enflasyon": (
        "Müşteri 50.000 TL dedi, asistan tutarı hesaba katmadı; cevap yalnızca yüzde veriyor. "
        "Kayıttaki kusurlu cevabı olduğu gibi bırakıyoruz."
    ),
}


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    return text


def markdown(text: str) -> str:
    """The small subset the model writes: paragraphs, bold, italics, one or two list levels."""
    out: list[str] = []
    stack: list[str] = []

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
    """Selected paragraphs of an answer, in order, with each cut marked."""
    parts = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return '\n<p class="cut">[…]</p>\n'.join(markdown(parts[i]) for i in keep)


def mark(body: str, phrases: list[str]) -> str:
    """Wrap each phrase (first occurrence) in a numbered highlight; the notes use the same
    numbers."""
    for n, phrase in enumerate(phrases, 1):
        escaped = html.escape(phrase, quote=False)
        if escaped not in body:
            raise SystemExit(f"highlight not in the recording: {phrase!r}")
        body = body.replace(escaped, f'<mark data-n="{n}">{escaped}</mark>', 1)
    return body


def case(case_id: str) -> dict:
    return next(c for c in firm["cases"] if c["id"] == case_id)


def calculations(c: dict) -> list[dict]:
    return [x for x in c["calls"] if x["tool"] != "search_assets"]


examples = []
for c in firm["cases"]:
    calls = calculations(c)
    facts = [f for x in calls for f in x["response"].get("facts", [])]
    examples.append(
        {
            "id": c["id"],
            "question": c["question"],
            "answer": markdown(c["answer"]),
            "calculation": ", ".join(CALCULATION.get(x["tool"], x["tool"]) for x in calls),
            "sentences": [html.escape(f) for f in facts[:2]],
            "count": len(facts),
            "note": NOTES.get(c["id"], ""),
        }
    )

# The walkthrough: one question from the customer's words to the answer.
walk = case("portfoy")
(walk_call,) = calculations(walk)
trades = "".join(
    f"<li>{'Alış' if t['type'] == 'buy' else 'Satış'}: {t['quantity']:g} {t['symbol']}, "
    f"{t['date']}</li>"
    for t in walk_call["arguments"]["transactions"]
)
walk_facts = "".join(f"<li>{html.escape(f)}</li>" for f in walk_call["response"]["facts"])

without = mark(
    excerpt(bare["neden"]["answer"], [0, 2, 3]),
    [
        "hisselerindeki bugünkü hareketlerin arkasında",
        "Akaryakıt (Jet Yakıtı) Fiyatları",
        '"Piyasa Haberleri"',
    ],
)
with_data = mark(
    markdown(case("neden")["answer"]),
    [
        "göre +%0,23 değişti",
        "Aynı seansta IDX +%0,37 değişti",
        "Haber kaynağına ulaşılamadı; haberler kontrol edilemedi.",
    ],
)
advice = mark(
    excerpt(bare["yatirim"]["answer"], [1, 3, 4, 7]),
    [
        "vermem maalesef mümkün değildir",
        "Perakende ve Gıda",
        "analistlerimizin hazırladığı dönemsel hisse ve sektör önerilerine",
    ],
)

fills = {
    "/*EXAMPLES*/[]": json.dumps(examples, ensure_ascii=False),
    "<!--WITHOUT_Q-->": html.escape(bare["neden"]["question"]),
    "<!--WITHOUT_A-->": without,
    "<!--WITH_Q-->": html.escape(case("neden")["question"]),
    "<!--WITH_A-->": with_data,
    "<!--ADVICE_Q-->": html.escape(bare["yatirim"]["question"]),
    "<!--ADVICE_A-->": advice,
    "<!--WALK_Q-->": html.escape(walk["question"]),
    "<!--WALK_TRADES-->": trades,
    "<!--WALK_FACTS-->": walk_facts,
    "<!--WALK_COUNT-->": str(len(walk_call["response"]["facts"])),
    "<!--WALK_A-->": markdown(walk["answer"]),
}
page = (HERE / "template.html").read_text()
for key, value in fills.items():
    if key not in page:
        raise SystemExit(f"template has no {key}")
    page = page.replace(key, value)
(HERE / "realmarket-demo.html").write_text(page)
print("written", len(page))
