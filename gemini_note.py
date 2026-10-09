"""Optional: add a short plain-language note written by a Gemini model to site/data/status.json.

The note is display-only. Traffic lights come from fixed rules in status.py and never depend on it.
Needs env var GEMINI_API_KEY (store it as a GitHub Actions secret; never commit it). Optional: GEMINI_MODEL.
Run: python gemini_note.py [--dry-run]
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent / "site" / "data" / "status.json"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def prompt(st):
    lines = [f"Overall state: {st['overall']}.",
             "Areas: " + "; ".join(f"{k}={v['status']}" for k, v in st["clusters"].items() if v["status"] != "na")]
    for i in st["items"]:
        if i.get("status") in ("yellow", "red"):
            lines.append(f"- {i['label']}: {i.get('value')} ({i['status']}). {i['meaning']}")
    lines.append("Pattern notes: " + " ".join(st["combos"]))
    lines.append("Closest stories: " + ", ".join(f"{p['name']} {p['score']}/{p['max']}" for p in st["paths"][:2]))
    data = "\n".join(lines)
    return ("You write a short daily note for a non-expert reader of a market-risk dashboard. Use only the readings below. "
            "Write 4 to 6 plain sentences. Define any jargon. Say what changed or stands out, what it does and does not "
            "mean, and what to watch next. Do not give investment advice, do not predict prices or dates, and do not "
            "tell the reader to buy or sell. Mention uncertainty once.\n\nREADINGS\n" + data)


def main():
    st = json.loads(OUT.read_text())
    text = prompt(st)
    if "--dry-run" in sys.argv:
        print(text)
        return
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY not set; skipping AI note")
        return
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": text}]}], "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400}},
            timeout=60)
        r.raise_for_status()
        out = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:  # never break the dashboard because of the note
        print("AI note failed:", type(e).__name__)
        st["ai_note"] = None
        OUT.write_text(json.dumps(st, separators=(",", ":")))
        return
    st["ai_note"] = {"text": out[:1200], "model": MODEL, "when": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")}
    OUT.write_text(json.dumps(st, separators=(",", ":")))
    print("AI note added")


if __name__ == "__main__":
    main()
