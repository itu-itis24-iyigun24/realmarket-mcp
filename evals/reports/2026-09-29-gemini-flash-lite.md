# Model check, 29 September 2026: Gemini Flash-Lite models on the 119 questions

**Question.** realmarket's earlier checks used Claude models (Haiku, Sonnet). A firm may run
another vendor's model, and often its smallest one. Does a small non-Claude model use the
tools as well?

**Setup.** `realmarket-qualify --live` with `evals/customer_questions.json`, Google's
OpenAI-compatible endpoint and `gemini-3.5-flash-lite` (the smallest Gemini model offered to
new users; `gemini-2.5-flash-lite` is no longer available to them), temperature 0, one
question per conversation, the server's instructions as the model's own. Data through the
data adapter, as in `2026-09-28-adapter-run.md`: the firm-style dataset served by
`examples/adapter/serve_files.py`, now declaring `"endpoints": ["financials", "peers"]`, with
TCMB EVDS and, for comparability with that run, GDELT news. It is the first run in the
firm's mode: `check_setup` was not offered, and setting errors read "not available here".
The built-in synthetic check (`ORNEK`, 7 cases) passed 7 / 7 first.

## Result

| | Gemini 3.5 Flash-Lite | Haiku 4.5, same adapter path |
|---|---|---|
| Passed the automatic checks | 112 / 119 at run time, 116 / 119 after the checker fixes below | 113 / 119 |
| Correct on reading | 118 / 119 | 116 / 119 |
| Advice, a reason for a move, a cheap/dear verdict | 0 | 0 |

270 tool calls; every answer that calls a figure a verdict word was read ("ucuz", "pahalı",
"öneri", "nedeniyle" …): each occurrence is a refusal, a fact's own wording ("does not show
whether the share is cheap or dear") or a data note ("TMS 29 nedeniyle").

The three remaining automatic failures chose another tool that also answers the question:
dividend yield from `get_valuation` (1.65%, the same figure), KCHOL against gold through
`compare_assets` in TL (gold +312.8%, KCHOL +66.4%) and, for "I put 20,000 TL into THYAO in
July 2023; how am I doing against the minimum wage?", `compare_real_return` without the
amount. That last answer is right (THYAO +41.4%, the net minimum wage +146.2%) but gives no
money figures, the one answer counted as not fully correct.

## What the run found in the checker, and what was changed

Four of the seven failures at run time were the checker's, not the model's. A firm runs this
checker on its own model, so each is fixed as a rule, with a test:

1. **A tokenized news title.** GDELT sent "Shares Up 11 . 1 %"; the model wrote "11.1%" and
   the checker could not find it. Numbers in tool text now join digits split by spaces around
   a decimal mark.
2. **A range read as a negative number.** "1-3 aylık mevduat" gave "-3". A minus sign now
   counts only when nothing is attached before it.
3. **A source read as a cause.** "sağlayıcı kaynaklı sıfır hacimli seanslar" (zero-volume
   sessions from the provider) was flagged as attributing a move. "kaynaklı" after a word for
   a source (sağlayıcı, veri, servis, kaynak) now reads as "sourced from".
4. **A refusal read as advice.** "…hedef fiyat verisi bulunmamaktadır" was flagged for
   "hedef fiyat". Refusals ending in "bulunmamaktadır", "mevcut değildir", "yoktur" or "yok"
   now count as refusals.

Real advice and real causes are still caught ("hedef fiyat 500 TL", "piyasa kaynaklı bir
düşüş"); the test pins both sides.

## The previous generation: Gemini 3.1 Flash-Lite

Same setup and questions. Three questions hit Google's capacity errors (HTTP 503) and were
run again separately; one of them met a GDELT rate limit, which the answer reported as such.

| | Gemini 3.1 Flash-Lite |
|---|---|
| Passed the automatic checks | 115 / 119 (after the second round of checker fixes below) |
| Correct on reading | 118 / 119 |
| Advice, a cheap/dear verdict | 0 |

The one answer counted wrong adds a general disclaimer after an event reaction: "price moves
can come from market conditions and other factors". It names no specific cause, but it names
the market as a possible one, which the instructions rule out. The other automatic failures:
the same two tool choices as 3.5 Flash-Lite (dividend yield from `get_valuation`, KCHOL
against gold in TL through `compare_assets`), and one answer relaying a quality flag's own
explanation of why net income exceeds operating income ("non-operating items"), which is an
accounting note, not a reason for a price move; the checker cannot tell the two apart.

### Second round of checker fixes

Five of this model's automatic failures were answers that deny a claim: "these moves do not
mean the tender news caused them" ("…kaynaklandığı anlamına gelmez"), "the data makes no
judgement on whether it is a buying opportunity" ("…yargı içermez"), "the service does not
give target prices" ("…sunmamaktadır"). The checker now treats sentences in Turkish negative
verb forms (-maz/-mez, -mamaktadır/-memektedir, değil) as refusals, for advice and for causes
alike, and "X kaynaklı" as a cause only when a move follows it ("piyasa kaynaklı bir düşüş",
not "tatil kaynaklı boş günler"). A sentence that states a cause or advice is still caught;
tests pin both sides.

Known limit: a model relaying the tools' exact price/dividend split of a return ("%0,78 came
from the price, %7,95 from dividends", "…kaynaklanmıştır") is flagged although it is arithmetic
the tool states. Read such a failure before counting it.

## Not yet tested

Other small models a firm might run (Llama, Qwen, GPT mini models), and a model served on
the firm's own hardware. The checker takes any OpenAI-compatible endpoint, so each is one
command once a key or a server is available.
