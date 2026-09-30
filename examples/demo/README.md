# Sales demo

A one-page demo for brokerages (`realmarket-demo.html`, in Turkish): a model with no tools
next to the same model with realmarket, ten recorded answers with what each tool call gave
the model, the model-check results and the pilot.

Published at https://itu-itis24-iyigun24.github.io/realmarket-mcp/examples/demo/realmarket-demo.html (GitHub Pages, built from `main`).

Every answer on the page is a recorded, unedited model output; the page only lays them out.
The data is fictional: the company ORNEK, its index and the peer retailers are generated,
not market data. Answers are made in the firm's mode (through the data adapter), so the page
shows what a brokerage's deployment does.

| File | What it is |
|---|---|
| `cases.json` | The ten demo questions |
| `recordings/answers.json` | The model's answers and every tool call, from `realmarket-qualify --live` |
| `recordings/no-tools.json` | The same model's answers to two questions without tools |
| `make_data.py` | Writes the fictional dataset the example adapter serves |
| `ask_without_tools.py` | Records `no-tools.json` |
| `template.html`, `build.py` | The page, and the script that fills it from the recordings |

## Rebuilding

Only the page, from the recordings (no network):

```bash
python examples/demo/build.py
```

Recording the answers again (Gemini through Google's OpenAI-compatible endpoint; any model
`realmarket-qualify` supports works the same way):

```bash
python examples/demo/make_data.py /tmp/demo-data
python examples/adapter/serve_files.py --root /tmp/demo-data --port 8770 &
env -u REALMARKET_EVDS_API_KEY -u REALMARKET_FRED_API_KEY -u REALMARKET_NEWS_PROVIDER \
  REALMARKET_PRICE_PROVIDER=http REALMARKET_HTTP_URL=http://127.0.0.1:8770 \
  REALMARKET_CPI_CSV_TR=/tmp/demo-data/cpi_tr.csv \
  realmarket-qualify --live --cases examples/demo/cases.json \
    --base-url https://generativelanguage.googleapis.com/v1beta/openai \
    --model gemini-3.5-flash-lite --api-key-env GEMINI_API_KEY --interval 3 \
    --output examples/demo/recordings/answers.json
python examples/demo/ask_without_tools.py
python examples/demo/build.py
```

Read every new answer before publishing the page: it shows whatever the model said. The
recording of 29 September 2026 passed all ten automatic checks; its "almalı mıyım?" answer
refuses advice correctly but asks for a symbol the question already gave.
