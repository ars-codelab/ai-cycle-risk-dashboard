"""Download the free public series the dashboard needs into ./data_raw/.

Sources: US Treasury daily yield curve, CBOE VIX history, ECB euro reference rates (to derive USD/JPY),
multpl.com Shiller CAPE, stockanalysis.com daily price history for a few ETFs and stocks.
No personal data is used anywhere in this folder. Run: python fetch_data.py
"""
import datetime as dt
import re
import time
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent / "data_raw"
OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
ETFS = ["SPY", "RSP", "SMH", "HYG", "IEF", "TLT"]
STOCKS = ["ORCL", "CRWV", "MU"]


def get(url):
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r


def treasury():
    this = dt.date.today().year
    for y in (this - 1, this):
        url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
               f"{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
        (OUT / f"treasury_{y}.csv").write_bytes(get(url).content)
        time.sleep(0.7)


def vix():
    (OUT / "vix_history.csv").write_bytes(get("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv").content)


def ecb():
    start = (dt.date.today() - dt.timedelta(days=400)).isoformat()
    for cur in ("USD", "JPY"):
        url = f"https://data-api.ecb.europa.eu/service/data/EXR/D.{cur}.EUR.SP00.A?format=csvdata&startPeriod={start}"
        (OUT / f"ecb_eur_{cur.lower()}.csv").write_bytes(get(url).content)


def cape():
    html = get("https://www.multpl.com/shiller-pe/table/by-month").text
    rows = re.findall(r"<td>([A-Z][a-z]{2} \d{1,2}, \d{4})</td>\s*<td>\s*(?:&#x2002;)?\s*([\d.]+)", html)
    iso = [(dt.datetime.strptime(d, "%b %d, %Y").date().isoformat(), v) for d, v in rows]
    if not iso:
        raise RuntimeError("CAPE table not found")
    (OUT / "cape_monthly.csv").write_text("date,cape\n" + "\n".join(f"{d},{v}" for d, v in iso))


def prices():
    for tk in ETFS + STOCKS:
        kind = "etf" if tk in ETFS else "stocks"
        html = get(f"https://stockanalysis.com/{kind}/{tk.lower()}/history/").text
        i = html.find("data:[{")
        j = html.find("]", i)
        out = {}
        for o in re.findall(r"\{[^{}]*\}", html[i:j + 1]):
            t = re.search(r't:"(\d{4}-\d{2}-\d{2})"', o)
            c = re.search(r"\bc:(-?[\d.]+)", o)
            a = re.search(r"\ba:(-?[\d.]+)", o)
            if t and c:
                out[t.group(1)] = a.group(1) if a else c.group(1)
        if not out:
            raise RuntimeError(f"no price rows for {tk}")
        (OUT / f"px_{tk}.csv").write_text("date,adj_close\n" + "\n".join(f"{d},{out[d]}" for d in sorted(out)))
        time.sleep(1.0)


if __name__ == "__main__":
    failed = []
    for f in (treasury, vix, ecb, cape, prices):
        try:
            f()
            print("ok", f.__name__)
        except Exception as e:  # keep going; status.py marks missing series as unavailable
            failed.append(f.__name__)
            print("FAILED", f.__name__, e)
    raise SystemExit(1 if len(failed) == 5 else 0)
