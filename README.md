# AI-Cycle Risk Dashboard

A static web page that shows early-warning indicators for an AI-driven market downturn, each as a traffic light with a plain-language
meaning, grouped into areas, with a rule-based overall state (Normal / Prepare / Move faster).

- **Public data only.** No balances, holdings or personal details are in this folder. GitHub Pages sites on personal accounts are public,
  so keep it that way. Personal interpretation stays in your private project (`scripts/personal_overlay.py` there).
- **Rules are fixed and visible** in `status.py`. Thresholds are drafts; most are not validated.
- **Optional AI note** from a Gemini model (`gemini_note.py`). It is display-only and never changes a traffic light.

## Run locally
```
pip install -r requirements.txt
python fetch_data.py      # downloads public series into data_raw/
python status.py          # writes site/data/status.json
cd site && python -m http.server 8000   # open http://localhost:8000
```

## Publish on GitHub Pages
1. Create a new **public** repository and push the contents of this folder to it (not your private project).
2. Settings -> Pages -> Build and deployment -> Source: **GitHub Actions**.
3. Actions tab -> "Build and deploy dashboard" -> Run workflow. It then runs every weekday after the US close.
4. Optional AI note: Settings -> Secrets and variables -> Actions -> New repository secret named `GEMINI_API_KEY`.
   Never put the key in a file or paste it into a chat.

## Things that can break
- Free sources change their pages (stockanalysis.com, multpl.com). If one fails, its gauges show "No data" and the page warns when it is stale.
- GitHub pauses scheduled workflows after 60 days without repository activity. Re-run it manually if the page goes stale.
- Credit spreads, Oracle/CoreWeave bond spreads and memory prices are paid data; stocks and ETF prices stand in for them.
