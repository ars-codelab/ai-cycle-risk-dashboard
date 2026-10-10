"""Compute dashboard indicators, traffic lights, plain-language meanings and write site/data/status.json.

Rules are deterministic. An optional AI-written note (gemini_note.py) is added separately and never changes a status.
Thresholds are DRAFT: most are not validated against history. Edit INDICATORS below.
Run: python fetch_data.py && python status.py
"""
import json
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data_raw"
OUT = ROOT / "site" / "data" / "status.json"

CLUSTERS = {
    "Rates": "The price of money. Higher long-term rates press on expensive stocks and on companies that borrowed a lot.",
    "Curve": "The shape of the yield curve (long rates minus short rates). A flip back to normal after an inversion has been the best single warning in the sample tested.",
    "Market stress": "Fear and falling prices in the stock market as a whole. These usually confirm trouble rather than predict it.",
    "Yen / funding": "Whether the yen is jumping. Fast yen rises have forced investors to unwind borrowed-yen trades and sell other assets.",
    "AI chain": "Chip makers and memory, the suppliers who sell into the AI spending boom.",
    "AI financing": "The borrowers paying for AI buildouts and the market for risky debt. Credit stress often shows up here before stock indexes.",
    "Breadth": "Whether the market is moving together or only a few giants are carrying it.",
    "Background": "Slow conditions that make a fall larger if one comes. They say nothing about timing, so they do not trigger actions.",
}

# kind: level | change6m | drawdown | pctchg | flag | ratio_pct20 | ratio_dd
# dir 'up' = higher is worse, 'down' = lower is worse.
INDICATORS = [
    dict(id="y10", label="10-year US yield", cluster="Rates", unit="%", dp=2, dir="up", y=5.25, r=5.50, src="Treasury",
         what="What the US government pays to borrow for 10 years. It sets the price of money for mortgages, companies and stock valuations.",
         g="Below 5.25%: borrowing costs are high but not at the level that has been squeezing stocks.",
         ye="Above 5.25%: high enough to press on expensive stocks and heavily indebted companies.",
         re="Above 5.5%: a level that hits expensive stocks and AI-related debt hard."),
    dict(id="y10_chg", label="10-year yield, 6-month change", cluster="Rates", unit="pts", dp=2, dir="up", y=0.75, r=1.0, src="Treasury",
         what="How quickly the 10-year yield has risen in half a year. Speed matters as much as level.",
         g="Rates have not risen unusually fast.",
         ye="Up 0.75 points or more in 6 months: a fast climb. On its own this was a weak warning historically.",
         re="Up 1 point or more in 6 months: a sharp rate shock (2022 style). Bonds may not cushion stock losses in this setting."),
    dict(id="tlt", label="Long bonds (TLT), 3 months", cluster="Rates", unit="%", dp=1, dir="down", y=-6, r=-10, src="Price history",
         what="The price of long-term US government bonds over 3 months. Falling prices mean lenders want more pay to lend long.",
         g="Long bonds are steady.", ye="Long bonds are falling: markets are asking for more pay to lend long.",
         re="Long bonds are falling fast: a term-premium shock. Stocks and bonds may fall together."),
    dict(id="curve", label="Yield curve flips back to normal", cluster="Curve", unit="pts", dp=2, dir="flag", src="Treasury",
         what="10-year yield minus 3-month yield. It is 'inverted' when it is negative. In 1990-2026 the highest-odds warning was the curve turning positive again within 6 months of being inverted (about 2.7x the usual chance of a 20% fall within a year).",
         g="No flip back in the last 6 months.", ye="The curve was inverted within the last 6 months and is now positive. Historically the best single flag in this sample.",
         re=""),
    dict(id="vix", label="VIX ('fear gauge')", cluster="Market stress", unit="", dp=1, dir="up", y=22, r=30, src="CBOE",
         what="How much protection investors are paying for against stock-market swings. Higher means more fear.",
         g="Calm: below 22.", ye="Nervous: 22 to 30.", re="Fear: above 30. Usually seen during a fall, not before it."),
    dict(id="vix_jump", label="VIX, 20-day jump", cluster="Market stress", unit="%", dp=0, dir="up", y=30, r=60, src="CBOE",
         what="How fast fear has risen in about a month.",
         g="No sudden jump in fear.", ye="Fear is up 30%+ in a month: something is unsettling markets.",
         re="Fear is up 60%+ in a month: a shock is under way."),
    dict(id="spy_dd", label="S&P 500 vs 6-month high", cluster="Market stress", unit="%", dp=1, dir="down", y=-5, r=-10, src="Price history",
         what="How far the US stock market is below its highest level in the last six months.",
         g="Within 5% of its high.", ye="5% to 10% below its high: a pullback.", re="More than 10% below its high: a correction is under way."),
    dict(id="usdjpy", label="Dollar vs yen, 20 days", cluster="Yen / funding", unit="%", dp=1, dir="down", y=-3, r=-5, src="ECB reference rates",
         what="Percent change in dollars per yen over 20 days. A fall means the yen is getting stronger.",
         g="No sharp yen rise.", ye="The yen is strengthening fast. Past sudden yen jumps forced investors to close borrowed-yen trades and sell other assets.",
         re="A sharp yen jump: funding-shock risk. These moves are fast and often partly reverse."),
    dict(id="smh", label="Semiconductors (SMH) vs 6-month high", cluster="AI chain", unit="%", dp=1, dir="down", y=-10, r=-20, src="Price history",
         what="How far chip stocks are below their 6-month high. Chips are the clearest read on AI spending expectations.",
         g="Chip stocks are near their highs.", ye="Chip stocks are 10%+ off their high: investors are getting cautious on AI demand.",
         re="Chip stocks are 20%+ off their high: a bear-market move in the AI supply chain."),
    dict(id="mu", label="Memory maker (Micron) vs 6-month high", cluster="AI chain", unit="%", dp=1, dir="down", y=-15, r=-30, src="Price history",
         what="Micron is a proxy for memory prices and inventory, one of the earliest places a demand slowdown shows up.",
         g="Memory stocks are near their highs.", ye="Memory stocks are 15%+ off their high: the memory cycle may be turning.",
         re="Memory stocks are 30%+ off their high: a sharp memory-cycle reversal."),
    dict(id="orcl", label="Oracle vs 6-month high", cluster="AI financing", unit="%", dp=1, dir="down", y=-15, r=-30, src="Price history",
         what="Oracle spends about twice its operating cash flow on capex, funded by debt. Its stock is a stand-in for AI-debt worries (its bond spreads are paid data).",
         g="Oracle is near its highs.", ye="Oracle is 15%+ off its high: investors are worried about the debt-funded buildout.",
         re="Oracle is 30%+ off its high: serious stress in a major AI borrower."),
    dict(id="crwv", label="CoreWeave vs 6-month high", cluster="AI financing", unit="%", dp=1, dir="down", y=-25, r=-40, src="Price history",
         what="CoreWeave rents AI computing capacity and is funded by high-cost debt. It is a canary for AI-credit stress.",
         g="CoreWeave is near its highs.", ye="CoreWeave is 25%+ off its high.", re="CoreWeave is 40%+ off its high: financing stress is visible."),
    dict(id="hyg_ief", label="Junk bonds vs Treasuries, vs 3-month high", cluster="AI financing", unit="%", dp=2, dir="down", y=-1.5, r=-3.0, src="Price history",
         what="Price of high-yield bonds relative to safe Treasuries. It falls when lenders get nervous about risky borrowers (a stand-in for credit spreads).",
         g="Lenders are relaxed.", ye="Risky-credit prices are slipping against Treasuries.", re="Risky credit is selling off: spreads are widening."),
    dict(id="rspspy", label="Equal-weight vs cap-weight (RSP/SPY), 20 days", cluster="Breadth", unit="%", dp=2, dir="down", y=-1.5, r=-3.0, src="Price history",
         what="Compares the average stock to the biggest stocks. When it falls, the giants are leading and the market is narrow.",
         g="Breadth is stable.", ye="The giants are pulling away from the average stock: narrowing leadership.",
         re="Sharp narrowing: the index is leaning on very few names."),
    dict(id="cape", label="Shiller CAPE (valuation)", cluster="Background", unit="x", dp=1, dir="up", y=30, r=40, src="multpl.com",
         what="Stock prices divided by 10 years of average earnings. High values have meant lower returns later and bigger drops, but with poor timing.",
         g="Valuations are not extreme.", ye="Valuations are expensive (30+).", re="Valuations are near record territory (40+). It raises the size of a fall, not its date."),
]
# Two extra explanations per indicator: (beginner, expert)
LEVEL_WHAT = {
    "y10": ("The interest rate the US government pays to borrow money for 10 years. When it is high, borrowing gets expensive for everyone.",
            "UST 10Y constant-maturity yield; sets discount rates for equities and long-duration credit. 5.25 / 5.50 are scenario cut-offs, not validated."),
    "y10_chg": ("How fast that interest rate has gone up in the last six months. Fast rises are harder on markets than slow ones.",
                "6-month change in the 10Y yield (126 trading days). +100bp in 6m fired on about 5% of days since 1990 with weak standalone lift."),
    "tlt": ("The price of long-term government bonds. If it falls, lenders are asking for more interest to lend for a long time.",
            "TLT 63-day return as a proxy for long-end / term-premium repricing. Watch for equity-bond correlation turning positive (2022 regime)."),
    "curve": ("Compares what the government pays on short loans and long loans. When short rates are higher it is called inverted; history says the flip back to normal is a warning sign.",
              "10Y minus 3M slope; flag = un-inverted within 6m after being below zero. 1990-2026 sample: about 2.7x conditional odds of a 20% drawdown within 12m, 10 episodes, high false-alarm rate."),
    "vix": ("A number showing how nervous investors are about the next month. Higher means more fear.",
            "CBOE VIX (30-day S&P 500 implied vol). Mostly coincident with equity drawdowns; seven bear peaks since 1990 occurred at VIX 12-23."),
    "vix_jump": ("How quickly that fear number has gone up over the last month.",
                 "20-trading-day % change in VIX; +60% had about 1.6x lift in the 1990-2026 sample."),
    "spy_dd": ("How far the whole US stock market has fallen from its highest point in the last six months.",
               "SPY drawdown from the 126-day high. Confirmation variable (coincident in the study)."),
    "usdjpy": ("How much the yen has gained or lost against the dollar over the last month. Sudden yen jumps have forced investors to sell other things.",
               "USD/JPY (ECB cross) 20-day change; carry-unwind proxy. Aug-2024 reference: about -12% in a month. Negative = yen strength."),
    "smh": ("How far the shares of big chip companies have fallen from their recent peak. Chips are where AI spending shows up first.",
            "SMH drawdown from the 126-day high; AI-capex beta proxy."),
    "mu": ("How far a major computer-memory maker's shares have fallen from their recent peak. Memory is often the first to feel a slowdown.",
           "MU drawdown from the 126-day high; stand-in for the DRAM/HBM contract-price and inventory cycle (paid data not available here)."),
    "orcl": ("How far Oracle's shares have fallen. Oracle is borrowing heavily to build AI data centers, so its share price reflects worry about that debt.",
             "ORCL drawdown from the 126-day high; proxy for AI-capex debt stress (capex/OCF about 1.8-2.0x per Gemini report; CDS is paid data)."),
    "crwv": ("How far CoreWeave's shares have fallen. It rents out AI computing and is funded with expensive debt, so it works like a canary in a coal mine.",
             "CRWV drawdown from the 126-day high; high-beta neocloud credit proxy (GPU-backed financing)."),
    "hyg_ief": ("Compares the price of riskier company bonds with safe government bonds. If the risky ones fall behind, lenders are getting nervous.",
                "HYG/IEF ratio vs its 63-day high; spread proxy because ICE BofA HY OAS is not available in the free feed."),
    "rspspy": ("Compares the average stock with the biggest stocks. If the average stock lags, the market is leaning on a few giants.",
               "RSP/SPY 20-day change; equal-weight vs cap-weight breadth. Concentration is high (top-10 weight about 39% per Gemini report)."),
    "cape": ("How expensive stocks are compared with their long-run profits. It says how big a fall could be, not when.",
             "Shiller CAPE (multpl.com). At 30+ the lift for a 20% drawdown within 12m was about 1.7x (1926-2025); poor timing."),
}
SHORT = {"y10": "10Y", "y10_chg": "10Y 6m chg", "tlt": "TLT 3m", "curve": "10Y-3M", "vix": "VIX", "vix_jump": "VIX 20d",
         "spy_dd": "SPY vs 6m high", "usdjpy": "USDJPY 20d", "smh": "SMH", "mu": "MU", "orcl": "ORCL", "crwv": "CRWV",
         "hyg_ief": "HYG/IEF", "rspspy": "RSP/SPY 20d", "cape": "CAPE"}
BEGINNER_STATUS = {"green": "Nothing worrying here.", "yellow": "Worth keeping an eye on.", "red": "This is where the pressure is highest."}
BEGINNER_AREA = {"AI financing": "companies that borrowed a lot to build AI", "AI chain": "the chip and memory makers",
                 "Rates": "interest rates", "Curve": "the shape of interest rates", "Market stress": "how scared investors are",
                 "Yen / funding": "the Japanese yen", "Breadth": "whether only a few giant companies are carrying the market"}

BYID = {i["id"]: i for i in INDICATORS}
MEANING_NEUTRAL = "Data unavailable right now."

PATHS = [
    dict(id="A", name="Valuation squeeze", clusters={"Rates": 1, "Curve": 1},
         story="Rates rise, expensive stocks re-price lower, the index slides while profits hold. Typical size 10-15%."),
    dict(id="B", name="Financing crack", clusters={"AI financing": 1, "AI chain": 0.5, "Breadth": 0.5},
         story="Stress appears at leveraged AI borrowers, risky-credit prices fall, capex gets cut, chip stocks drop, then the index. Typical size 25-35%."),
    dict(id="C", name="Funding shock", clusters={"Yen / funding": 1, "Market stress": 1},
         story="The yen jumps, borrowed-yen trades close, investors sell everything in days. Often partly reverses. Typical size 10-15%."),
    dict(id="D", name="Demand disappointment", clusters={"AI chain": 1, "Breadth": 0.5, "Market stress": 0.5},
         story="An AI revenue or spending disappointment hits chips first, then the giants. Typical size 30-45% in AI-linked names."),
]


def read_px(tk):
    p = RAW / f"px_{tk}.csv"
    if not p.exists():
        return None
    s = pd.read_csv(p, parse_dates=["date"]).set_index("date")["adj_close"].astype(float).sort_index()
    return s


def load():
    d = {}
    ty = []
    for p in sorted(RAW.glob("treasury_*.csv")):
        t = pd.read_csv(p)
        t["date"] = pd.to_datetime(t["Date"], format="%m/%d/%Y")
        ty.append(t.set_index("date"))
    if ty:
        ty = pd.concat(ty).sort_index()
        ty = ty[~ty.index.duplicated()]
        d["y10"] = ty["10 Yr"].dropna()
        d["slope"] = (ty["10 Yr"] - ty["3 Mo"]).dropna()
    v = RAW / "vix_history.csv"
    if v.exists():
        x = pd.read_csv(v)
        d["vix"] = x.assign(date=pd.to_datetime(x["DATE"], format="%m/%d/%Y")).set_index("date")["CLOSE"].astype(float)
    try:
        e = {c: pd.read_csv(RAW / f"ecb_eur_{c}.csv").set_index("TIME_PERIOD")["OBS_VALUE"].astype(float) for c in ("usd", "jpy")}
        j = (e["jpy"] / e["usd"]).dropna()
        j.index = pd.to_datetime(j.index)
        d["usdjpy"] = j.sort_index()
    except Exception:
        pass
    c = RAW / "cape_monthly.csv"
    if c.exists():
        x = pd.read_csv(c, parse_dates=["date"]).sort_values("date")
        d["cape"] = x.set_index("date")["cape"].astype(float)
    for tk in ("SPY", "RSP", "SMH", "HYG", "IEF", "TLT", "ORCL", "CRWV", "MU"):
        s = read_px(tk)
        if s is not None:
            d[tk] = s
    return d


def compute(d):
    out = {}

    def put(i, value, series, asof, note=""):
        out[i] = dict(value=float(value), series=series, asof=asof, note=note)

    def tail(s, n=126):
        s = s.dropna().iloc[-n:]
        return [[k.strftime("%Y-%m-%d"), round(float(v), 4)] for k, v in s.items()]

    if "y10" in d:
        y = d["y10"]
        put("y10", y.iloc[-1], tail(y), y.index[-1])
        put("y10_chg", y.iloc[-1] - y.iloc[-127], tail(y), y.index[-1])
    if "TLT" in d:
        s = d["TLT"]
        put("tlt", (s.iloc[-1] / s.iloc[-64] - 1) * 100, tail(s), s.index[-1])
    if "slope" in d:
        sl = d["slope"]
        flag = bool(sl.iloc[-127:].min() < 0 and sl.iloc[-1] > 0)
        put("curve", sl.iloc[-1], tail(sl), sl.index[-1], "flip" if flag else "")
    if "vix" in d:
        v = d["vix"]
        put("vix", v.iloc[-1], tail(v), v.index[-1])
        put("vix_jump", (v.iloc[-1] / v.iloc[-21] - 1) * 100, tail(v), v.index[-1])
    if "SPY" in d:
        s = d["SPY"]
        put("spy_dd", (s.iloc[-1] / s.max() - 1) * 100, tail(s), s.index[-1])
    if "usdjpy" in d:
        s = d["usdjpy"]
        put("usdjpy", (s.iloc[-1] / s.iloc[-21] - 1) * 100, tail(s), s.index[-1], f"level {s.iloc[-1]:.1f}")
    for i, tk in (("smh", "SMH"), ("mu", "MU"), ("orcl", "ORCL"), ("crwv", "CRWV")):
        if tk in d:
            s = d[tk]
            put(i, (s.iloc[-1] / s.max() - 1) * 100, tail(s), s.index[-1])
    if "HYG" in d and "IEF" in d:
        r = (d["HYG"] / d["IEF"]).dropna()
        put("hyg_ief", (r.iloc[-1] / r.iloc[-63:].max() - 1) * 100, tail(r), r.index[-1])
    if "RSP" in d and "SPY" in d:
        r = (d["RSP"] / d["SPY"]).dropna()
        put("rspspy", (r.iloc[-1] / r.iloc[-21] - 1) * 100, tail(r), r.index[-1])
    if "cape" in d:
        c = d["cape"]
        put("cape", c.iloc[-1], tail(c, 60), c.index[-1])
    return out


PREV = RAW / "previous_status.json"
OVERALL_PLAIN = {
    "normal": "Nothing unusual is flashing right now.",
    "prepare": "Some stress is building in parts of the market, but the market as a whole has not broken.",
    "accelerate": "Several independent warning areas are red at the same time.",
}


def previous():
    try:
        return json.loads(PREV.read_text())
    except Exception:
        return None


def plain_summary(overall, clus, items, paths, changes):
    """Deterministic 'in plain words' paragraph. Used on the page when no AI note is available or the AI note fails checks."""
    lines = [OVERALL_PLAIN[overall]]
    reds = [i for i in items if i["status"] == "red" and i["cluster"] != "Background"]
    yels = [i for i in items if i["status"] == "yellow"]
    if reds:
        areas = sorted({i["cluster"] for i in reds})
        lines.append("The loudest warning is in " + " and ".join(areas) + ". " + " ".join(i["meaning"] for i in reds[:2]))
    watch = sorted({i["cluster"] for i in yels} - {i["cluster"] for i in reds})
    if watch:
        lines.append("Also worth watching: " + ", ".join(watch) + " (each is yellow: not alarming alone, but moving the wrong way).")
    top = paths[0] if paths else None
    if top and top["score"] >= 2:
        lines.append(f"The pattern most like today is the \"{top['name']}\" story: {top['story']}")
    lines.append("This does not say when, or whether, a fall will happen. Past market peaks have often looked calm, so the point of this page "
                 "is to be ready and to see which story is unfolding, not to guess a date.")
    if changes:
        lines.append("Since the last update: " + "; ".join(changes[:3]) + ".")
    return "\n".join(lines)


def beginner_summary(overall, clus, items, paths, changes):
    first = {"normal": "Nothing looks worrying right now.",
             "prepare": "The market as a whole looks fine, but some of the pieces of the AI boom are under pressure, and that is usually where trouble shows up first.",
             "accelerate": "Several different warning signs are flashing at the same time, which is unusual."}[overall]
    reds = sorted({i["cluster"] for i in items if i["status"] == "red" and i["cluster"] != "Background"})
    yels = sorted({i["cluster"] for i in items if i["status"] == "yellow"} - set(reds))
    L = [first]
    if reds:
        L.append("The biggest worry is " + " and ".join(BEGINNER_AREA.get(r, r) for r in reds) + ".")
    if yels:
        L.append("Smaller warning signs: " + ", ".join(BEGINNER_AREA.get(y, y) for y in yels) + ".")
    L.append("This does not mean a crash is coming, and nobody can say when one would start. It means this is a good time to make sure you are ready, not a time to panic.")
    if changes:
        L.append("What changed since last time: " + "; ".join(changes[:2]) + ".")
    return "\n".join(L)


def expert_summary(overall, clus, items, paths, changes, counts):
    def f(i):
        v = i.get("value")
        u = i.get("unit", "")
        sfx = {"%": "%", "pts": "pp", "x": "x"}.get(u, "")
        tag = SHORT.get(i["id"], i["id"].upper())
        return f"{tag} {v:+.{i['dp']}f}{sfx}" if v is not None else tag
    L = [f"State: {overall.upper()} ({counts['red']} red, {counts['yellow']} yellow, {counts['green']} green clusters)."]
    for st_, name in (("red", "Red"), ("yellow", "Yellow")):
        grp = {}
        for i in items:
            if i["status"] == st_ and i["cluster"] != "Background":
                grp.setdefault(i["cluster"], []).append(f(i))
        if grp:
            L.append(f"{name}: " + "; ".join(f"{c} ({', '.join(v)})" for c, v in grp.items()) + ".")
    cape = next((i for i in items if i["id"] == "cape" and i.get("value") is not None), None)
    if cape:
        L.append(f"Background: CAPE {cape['value']:.1f}x (context only, not in the action rule).")
    if paths:
        L.append("Pattern match: " + ", ".join(f"{p['name']} {p['score']}/{p['max']}" for p in paths[:2]) + ".")
    L.append("Caveats: thresholds unvalidated; free proxies replace HY OAS, CDS and DRAM/HBM prices; lights are coincident-to-late more often than leading.")
    if changes:
        L.append("Delta: " + "; ".join(changes[:3]) + ".")
    return "\n".join(L)


def classify(ind, rec):
    if ind["dir"] == "flag":
        return "yellow" if rec["note"] == "flip" else "green"
    v = rec["value"]
    bad = (lambda t: v >= t) if ind["dir"] == "up" else (lambda t: v <= t)
    return "red" if bad(ind["r"]) else ("yellow" if bad(ind["y"]) else "green")


def build():
    d = load()
    vals = compute(d)
    rank = {"green": 0, "yellow": 1, "red": 2}
    items, clus = [], {}
    for ind in INDICATORS:
        rec = vals.get(ind["id"])
        if rec is None:
            items.append(dict(id=ind["id"], label=ind["label"], cluster=ind["cluster"], status="na", meaning=MEANING_NEUTRAL,
                              meaning_b=MEANING_NEUTRAL, meaning_x=MEANING_NEUTRAL, what=ind["what"], what_b=LEVEL_WHAT[ind["id"]][0],
                              what_x=LEVEL_WHAT[ind["id"]][1], src=ind["src"], unit=ind["unit"], dp=ind["dp"]))
            continue
        st = classify(ind, rec)
        meaning = ind["g"] if st == "green" else (ind["ye"] if st == "yellow" else (ind["re"] or ind["ye"]))
        th = ("flip back to positive within 6 months of inversion" if ind["dir"] == "flag" else
              f"{'at or above' if ind['dir']=='up' else 'at or below'} {ind['y']:g} (watch) / {ind['r']:g} (alert)")
        items.append(dict(id=ind["id"], label=ind["label"], cluster=ind["cluster"], unit=ind["unit"], dp=ind["dp"], value=round(rec["value"], 4),
                          asof=rec["asof"].strftime("%Y-%m-%d"), status=st, threshold=th, meaning=meaning, what=ind["what"], src=ind["src"],
                          meaning_b=BEGINNER_STATUS[st], meaning_x=f"{st.upper()} vs thresholds {th}.",
                          what_b=LEVEL_WHAT[ind["id"]][0], what_x=LEVEL_WHAT[ind["id"]][1],
                          note=rec["note"], series=rec["series"]))
        if ind["cluster"] != "Background":
            c = ind["cluster"]
            if rank[st] > rank.get(clus.get(c, "green"), 0):
                clus[c] = st
            clus.setdefault(c, st)
    nred = sum(1 for v in clus.values() if v == "red")
    nyel = sum(1 for v in clus.values() if v == "yellow")
    spy_red = any(i["id"] == "spy_dd" and i["status"] == "red" for i in items)
    if nred >= 3 or (nred >= 1 and spy_red):
        overall = "accelerate"
    elif nred >= 1 or nyel >= 3:
        overall = "prepare"
    else:
        overall = "normal"
    # which paths the readings resemble
    pts = {"green": 0, "yellow": 1, "red": 2}
    paths = []
    for p in PATHS:
        score = sum(w * pts.get(clus.get(c, "green"), 0) for c, w in p["clusters"].items())
        paths.append(dict(id=p["id"], name=p["name"], story=p["story"], score=round(score, 1), max=round(sum(p["clusters"].values()) * 2, 1),
                          drivers=[c for c in p["clusters"] if clus.get(c, "green") != "green"]))
    paths.sort(key=lambda p: -p["score"])
    # rules that combine signals
    s = {k: v for k, v in clus.items()}
    combos, combos_b, combos_x = [], [], []

    def add(med, beg, exp):
        combos.append(med); combos_b.append(beg); combos_x.append(exp)
    if s.get("AI financing") == "red" and s.get("Market stress", "green") == "green":
        add("Stress is concentrated in leveraged AI borrowers while the broad market is calm. Historically, market peaks looked calm; this is an early-stage pattern, not proof of a fall.",
            "A few companies that borrowed a lot for AI are under pressure, but the overall market is calm. Past market peaks also looked calm, so this is a reason to be ready, not a reason to panic.",
            "AI-financing red with market-stress green: idiosyncratic credit stress ahead of index confirmation. Peaks in the sample (1990-2026) printed at VIX 12-23.")
    if s.get("AI financing") == "red" and s.get("AI chain") in ("yellow", "red"):
        add("Stress at AI borrowers is reaching the chip and memory suppliers. That is how a financing crack spreads.",
            "The worry about AI borrowers is starting to reach the companies that sell chips and memory to them.",
            "AI-financing red with AI-chain >= yellow: contagion from borrowers to suppliers (path B: financing crack).")
    if s.get("Rates") in ("yellow", "red") and s.get("AI financing") in ("yellow", "red"):
        add("Higher rates and weak AI borrowers together make refinancing harder for heavily indebted AI projects.",
            "Rising interest rates make it harder for the heavily indebted AI companies to keep borrowing.",
            "Rates >= yellow with AI-financing >= yellow: refinancing channel; watch HYG/IEF and 10Y vs 5.25 / 5.50.")
    if s.get("Curve") == "yellow":
        add("The yield curve has just turned positive after an inversion. In 1990-2026 that was the strongest single warning, with many false alarms.",
            "A particular pattern in interest rates that has often come before downturns has just appeared. It also gave many false alarms.",
            "10Y-3M un-inverted within 6m: 2.7x conditional odds in the 1990-2026 sample, 10 episodes, 7 followed by a 15% drop.")
    if s.get("Yen / funding") in ("yellow", "red"):
        add("The yen is moving fast. Funding shocks are quick and can partly reverse; do not act on one day's move.",
            "The Japanese yen is moving quickly. These jumps are fast and often partly reverse, so one day's move is not a signal to act.",
            "USDJPY 20d change beyond threshold: carry-unwind risk; typically fast and partially mean-reverting (Aug 2024).")
    if s.get("Market stress") == "red" and nred + nyel >= 3:
        add("Broad stress with several areas warning: the move may already be under way. Follow your pre-agreed steps, not the headlines.",
            "Many warning signs and a falling market at once: the move may already be under way. Follow the steps you decided in advance, not the headlines.",
            "Market-stress red with 3+ clusters non-green: broad risk-off; execute pre-agreed rules.")
    if not combos:
        add("No combination of warnings is active.", "No combination of warning signs is active.", "No cross-cluster combination rule fired.")
    prev = previous()
    changes = []
    if prev:
        pm = {i["id"]: i.get("status") for i in prev.get("items", [])}
        for it in items:
            o_ = pm.get(it["id"])
            if o_ and o_ != it["status"] and it["status"] != "na" and o_ != "na":
                changes.append(f"{it['label']} moved from {o_} to {it['status']}")
        if prev.get("overall") and prev["overall"] != overall:
            changes.insert(0, f"the overall state moved from {prev['overall']} to {overall}")
    summary_rules = plain_summary(overall, clus, items, paths, changes)
    counts_ = dict(red=nred, yellow=nyel, green=sum(1 for v in clus.values() if v == "green"))
    summary_levels = {
        "beginner": dict(text=beginner_summary(overall, clus, items, paths, changes), source="rules"),
        "medium": dict(text=summary_rules, source="rules"),
        "expert": dict(text=expert_summary(overall, clus, items, paths, changes, counts_), source="rules"),
    }
    now = dt.datetime.now(dt.timezone.utc)
    asofs = [i["asof"] for i in items if i.get("asof")]
    newest = max(asofs) if asofs else None
    stale_days = (now.date() - dt.date.fromisoformat(newest)).days if newest else None
    return dict(generated=now.strftime("%Y-%m-%d %H:%M UTC"), newest_data=newest, stale_days=stale_days,
                overall=overall, clusters={k: dict(status=clus.get(k, "na"), blurb=v) for k, v in CLUSTERS.items() if k != "Background" or True},
                items=items, paths=paths, combos=combos, combos_levels=dict(beginner=combos_b, medium=combos, expert=combos_x), ai_note=None, changes=changes,
                summary=summary_levels["medium"], summary_levels=summary_levels, summary_rules=summary_rules,
                counts=dict(red=nred, yellow=nyel, green=sum(1 for v in clus.values() if v == "green")))


if __name__ == "__main__":
    st = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    old = None
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text()).get("ai_note")
        except Exception:
            pass
    st["ai_note"] = old
    OUT.write_text(json.dumps(st, separators=(",", ":")))
    print("overall:", st["overall"], "clusters:", {k: v["status"] for k, v in st["clusters"].items()})
