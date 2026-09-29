"""Ask the same model two customer questions with no tools: the page's contrast.

The system prompt tells it only that it is a brokerage's assistant, as a firm might without
realmarket. Needs GEMINI_API_KEY; writes recordings/no-tools.json.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
MODEL = "gemini-3.5-flash-lite"
SYSTEM = (
    "Sen bir aracı kurumun mobil uygulamasındaki yardımcı asistansın. Müşterilerin yatırım "
    "sorularını Türkçe cevaplarsın."
)
QUESTIONS = {
    "yatirim": "Elimde 100.000 TL var, enflasyona ezdirmek istemiyorum. Hangi hisseleri almalıyım?",
    "neden": "THYAO bugün neden düştü?",
}


def ask(question: str) -> str:
    body = {
        "model": MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ],
    }
    request = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "authorization": "Bearer " + os.environ["GEMINI_API_KEY"],
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return str(json.load(response)["choices"][0]["message"]["content"])


if __name__ == "__main__":
    out = {key: {"question": q, "answer": ask(q)} for key, q in QUESTIONS.items()}
    path = Path(__file__).parent / "recordings" / "no-tools.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
