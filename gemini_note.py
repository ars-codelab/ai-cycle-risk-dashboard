"""Optional: replace the rule-based summaries with ones written by a Gemini model, for three reader levels, with safety checks.

- Input is only the public readings in site/data/status.json. No personal data exists in this project.
- Each level's output must pass checks (length, no buy/sell/predict wording, labelled lines, numbers must come from the readings).
  A level that fails keeps its rule-based text; the others can still be AI-written. Traffic lights never depend on this text.
- Needs env var GEMINI_API_KEY (a GitHub Actions secret; never commit it). Optional: GEMINI_MODEL (default gemini-3.8-flash), GEMINI_API_BASE.
Run: python gemini_note.py [--dry-run]
"""
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent / "site" / "data" / "status.json"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
# Keys that start with "AQ." are Vertex AI express-mode keys; "AIza..." keys are Google AI Studio keys. They use different endpoints.
VERTEX_BASE = "https://aiplatform.googleapis.com/v1/publishers/google/models"
STUDIO_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
# Advice and prediction wording. "guaranteed" is allowed because it appears in sentences like "a fall is not guaranteed".
BANNED = re.compile(r"\b(buy(?:ing)?|sell(?:ing)?(?![- ]?off)|shorting|short (?:the|it|them|stocks?)|you should|must (?:buy|sell)|"
                    r"will crash|going to crash|will fall|will rise|price target)\b", re.I)
LABELS = ["Bottom line:", "Why:", "What this does not mean:", "What to watch:"]
LEVELS = {
    "beginner": ("for someone who has never followed markets: no jargon at all, everyday comparisons are fine, short sentences", (160, 700)),
    "medium": ("for an intelligent adult who is not a finance expert: define any term in a few words", (200, 1000)),
    "expert": ("for a finance professional: terse, use proper terms (spreads, term premium, carry, breadth, drawdown), include the key numbers", (200, 1200)),
}


def readings_text(st):
    lines = [f"Overall state (from fixed rules): {st['overall']}.",
             "Areas: " + "; ".join(f"{k} is {v['status']}" for k, v in st["clusters"].items() if v["status"] != "na")]
    for i in st["items"]:
        if i.get("status") in ("yellow", "red"):
            lines.append(f"- {i['label']}: {i.get('value')} ({i['status']}). {i['meaning']}")
    if st.get("changes"):
        lines.append("Changed since the last update: " + "; ".join(st["changes"]))
    lines.append("Closest stories: " + ", ".join(f"{p['name']} {p['score']} of {p['max']}" for p in st["paths"][:2]))
    return "\n".join(lines)


def prompt(st):
    lv = "\n".join(f'- "{k}": {v[0]}' for k, v in LEVELS.items())
    return (
        "You write the top summary of a public market-risk dashboard about an AI-driven downturn. Use ONLY the readings below; do not add "
        "facts or numbers from elsewhere. Return a JSON object with exactly the keys beginner, medium, expert. Each value is a string of "
        "exactly four short lines separated by newline characters, starting with these labels:\n"
        "Bottom line: one sentence on how worried to be right now.\n"
        "Why: one to two sentences on what is driving it.\n"
        "What this does not mean: one sentence (for example that it does not say when or whether a fall happens).\n"
        "What to watch: one sentence on the next thing that would change the picture.\n"
        "Write each level for its reader:\n" + lv + "\n"
        "Rules: write AI as AI (do not invent other names for it); no investment advice, no buy or sell wording, no price or date predictions, no scare language.\n\nREADINGS\n" + readings_text(st))


def allowed_numbers(st):
    nums = set()
    for i in st["items"]:
        v = i.get("value")
        if v is not None:
            for x in (abs(v), abs(v) * 100 if i.get("unit") == "pts" else abs(v)):
                for d in (0, 1, 2):
                    nums.add(f"{x:.{d}f}")
                    nums.add(f"{x:.{d}f}".rstrip("0").rstrip(".") if d else f"{x:.0f}")
        for t in re.findall(r"\d+(?:\.\d+)?", i.get("meaning", "") + " " + i.get("threshold", "")):
            nums.add(t)
    for p in st["paths"]:
        nums.update([f"{p['score']:g}", f"{p['max']:g}"])
    return nums


def check(text, st, level="medium"):
    lo, hi = LEVELS[level][1]
    if not (lo <= len(text) <= hi):
        return "length"
    if BANNED.search(text):
        return "banned wording"
    if not all(l in text for l in LABELS):
        return "missing labels"
    norm = lambda n: n.rstrip("0").rstrip(".") if "." in n else n
    allowed = {norm(n) for n in allowed_numbers(st)}
    unknown = [n for n in re.findall(r"\d+(?:\.\d+)?", text) if len(n.replace(".", "")) >= 2 and norm(n) not in allowed]
    if len(unknown) > 1:
        return f"ungrounded numbers {unknown[:3]}"
    return None


def main():
    st = json.loads(OUT.read_text())
    p = prompt(st)
    if "--dry-run" in sys.argv:
        print(p)
        return
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY not set; keeping rule-based summaries")
        return
    base = os.environ.get("GEMINI_API_BASE") or (VERTEX_BASE if key.startswith("AQ.") else STUDIO_BASE)
    try:
        r = requests.post(f"{base}/{MODEL}:generateContent",
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                          json={"contents": [{"role": "user", "parts": [{"text": p}]}],
                                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4000, "responseMimeType": "application/json"}},
                          timeout=120)
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        data = json.loads(raw)
    except Exception as e:  # never break the dashboard because of the summary
        print("AI summary failed:", type(e).__name__, "- keeping rule-based summaries")
        return
    when = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    accepted = []
    for level in LEVELS:
        text = str(data.get(level, "")).strip()
        why = check(text, st, level)
        if why:
            print(f"AI summary ({level}) rejected: {why}")
            continue
        st["summary_levels"][level] = {"text": text, "source": "gemini", "model": MODEL, "when": when}
        accepted.append(level)
    st["summary"] = st["summary_levels"]["medium"]
    OUT.write_text(json.dumps(st, separators=(",", ":")))
    print("AI summaries added for:", ", ".join(accepted) or "none")


if __name__ == "__main__":
    main()
