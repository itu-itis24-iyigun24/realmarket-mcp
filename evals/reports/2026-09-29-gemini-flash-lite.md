# Model check, 29 September 2026: Gemini Flash-Lite and Gemma 4 on the 119 questions

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

## An open model: Gemma 4 26B (A4B), through Google's API

Gemma is an open-weights model a firm could run on its own hardware, which matters where
customer data must not leave the firm. Here it was reached through Google's free API, with
the same setup, and a `--timeout` option added to the checker so a slow reply is not cut off
at 120 seconds.

**The run was stopped after 61 of the 119 questions**, because the serving, not the model,
failed: 13 of the 61 never got a reply (Google's API gave no answer within 300 seconds,
returned "internal error" or dropped the connection), mostly right after a large tool result
(real return, financial statements, comparisons). Each such question took about twenty
minutes of retries.

| | Gemma 4 26B, 48 answered questions |
|---|---|
| Content correct (every check but the one below) | 44 / 48 |
| Reasoning written into the answer | 47 / 48 |
| Advice, a cause for a move, a cheap/dear verdict | 0 |

The four content failures are not errors: the same two alternative tool choices as the Gemini
models, and two cases of the checker limit described above (the tool's own price/dividend
split, and a quality flag's accounting note). The finding that matters is the other one:
Gemma writes its reasoning into the answer text as a `<thought>` block, which a customer
would see. `realmarket-qualify` fails every such answer (`no_reasoning_in_answer`) by
design. A firm running this model must turn reasoning output off in its model server or
strip the block before the answer leaves its backend (`docs/integration.md`, "Showing
answers to customers").

Gemma 4 31B passed 2 of 7 on the synthetic check, with the same reasoning leak and three
cases lost to the same capacity errors; it was not run on the full set.

**Conclusion for Gemma:** its answers follow the tools as well as the Gemini models' do; it
needs its reasoning stripped, and it needs serving that can take a long tool result.
Google's free endpoint is not that. Re-run it on another host or on the firm's hardware.

## Not yet tested

Other small models a firm might run (Llama, Qwen, GPT mini models), Gemma on reliable
serving, and a model on the firm's own hardware. The checker takes any OpenAI-compatible endpoint, so each is one
command once a key or a server is available.
