(function () {
  "use strict";
  var ICON = { green: "✓", yellow: "▲", red: "●", na: "–" };
  var LABEL = { green: "OK", yellow: "Watch", red: "Alert", na: "No data" };
  var LEVELS = ["beginner", "medium", "expert"];
  var OVERALL = {
    normal: { title: "Normal", status: "green",
      text: "Nothing unusual is flashing. Stay on your plan's schedule and do not act on daily noise.",
      acts: ["Keep your scheduled steps.", "Check once a day at most; most days nothing changes."],
      actsB: ["Nothing to do today.", "You do not need to check this every day."],
      actsX: ["No rule fired. Maintain schedule.", "Review thresholds at quarter-end."] },
    prepare: { title: "Prepare", status: "yellow",
      text: "Stress is building in parts of the market. Treat this as a prompt to check readiness, not a reason to rush.",
      acts: ["Confirm your next planned step and that cash is where you want it.",
             "Re-read your written rules now, while markets are calm.",
             "Watch whether more areas turn yellow or red."],
      actsB: ["Make sure you know your plan and where your cash is.", "Do not make big changes because of this page alone.",
              "Look again in a few days to see if more warnings appear."],
      actsX: ["Confirm next scheduled step and funding of the cash sleeve.",
              "Pre-commit escalation: second cluster red, or SPY more than 10% below its high.",
              "Monitor HYG/IEF, MU and 10Y vs 5.25 / 5.50 for confirmation."] },
    accelerate: { title: "Move faster", status: "red",
      text: "Several independent warning areas are red together, or a red area is joined by a market correction. Your rules call for the faster setting.",
      acts: ["Do the remaining planned steps sooner.", "Stop adding to the most AI-heavy holdings.",
             "Keep your buy-in rules for the cash you hold; they are separate from these warnings."],
      actsB: ["Several warnings are on at once, so your plan says to move faster.", "Do the steps you already planned, sooner.",
              "Keep following your plan, not the news."],
      actsX: ["Escalation rule met: execute remaining steps ahead of schedule.", "Hold buy-in tranches on price triggers, independent of these lights.",
              "Park proceeds in T-bills promptly."] }
  };
  var level = "medium";
  var data = null;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function chip(status, big, label) {
    var c = el("span", "chip " + status + (big ? " big" : ""));
    c.appendChild(el("span", null, ICON[status] || ICON.na));
    c.appendChild(el("span", null, label || LABEL[status] || LABEL.na));
    return c;
  }
  function fmt(it) {
    if (it.value === undefined) return "n/a";
    var v = it.value.toFixed(it.dp);
    if (it.unit === "%") return (it.value > 0 && it.id !== "y10" ? "+" : "") + v + "%";
    if (it.unit === "pts") return (it.value > 0 ? "+" : "") + v + " pts";
    if (it.unit === "x") return v + "x";
    return v;
  }
  var tip = document.getElementById("tip");
  function spark(series, label) {
    var W = 96, H = 32, P = 4;
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("class", "spark");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label + " trend, last " + series.length + " observations");
    var vals = series.map(function (p) { return p[1]; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var span = hi - lo || 1;
    function xy(i) { return [P + (W - 2 * P) * i / Math.max(1, series.length - 1), H - P - (H - 2 * P) * (vals[i] - lo) / span]; }
    var d = series.map(function (_, i) { var p = xy(i); return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join("");
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    svg.appendChild(path);
    var last = xy(series.length - 1);
    var dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", last[0]); dot.setAttribute("cy", last[1]); dot.setAttribute("r", 3.5);
    svg.appendChild(dot);
    function show(ev) {
      var r = svg.getBoundingClientRect();
      var x = (ev.clientX - r.left) / r.width * W;
      var i = Math.round((x - P) / (W - 2 * P) * (series.length - 1));
      i = Math.max(0, Math.min(series.length - 1, i));
      tip.textContent = series[i][0] + ": " + series[i][1];
      tip.hidden = false;
      tip.style.left = Math.min(window.innerWidth - 150, ev.clientX + 10) + "px";
      tip.style.top = (ev.clientY - 34) + "px";
    }
    svg.addEventListener("pointermove", show);
    svg.addEventListener("pointerdown", show);
    svg.addEventListener("pointerleave", function () { tip.hidden = true; });
    return svg;
  }
  function pick(it, base) {
    if (level === "beginner" && it[base + "_b"]) return it[base + "_b"];
    if (level === "expert" && it[base + "_x"]) return it[base + "_x"];
    return it[base];
  }

  function render(s) {
    var o = OVERALL[s.overall] || OVERALL.normal;
    var hero = document.getElementById("overall");
    hero.textContent = "";
    var row = el("div", "cl-head");
    row.appendChild(el("h2", null, "Overall: " + o.title + "  \u00B7  " + level.charAt(0).toUpperCase() + level.slice(1) + " view"));
    row.appendChild(chip(o.status, true, o.title));
    hero.appendChild(row);

    var sl = s.summary_levels && s.summary_levels[level] ? s.summary_levels[level] : (s.summary || { text: o.text, source: "rules" });
    sl.text.split("\n").forEach(function (para) {
      para = para.trim();
      if (!para) return;
      var m = para.match(/^(Bottom line:|Why:|What this does not mean:|What to watch:)\s*(.*)$/);
      var p = el("p", "summary");
      if (m) { p.appendChild(el("strong", null, m[1] + " ")); p.appendChild(document.createTextNode(m[2])); }
      else p.textContent = para;
      hero.appendChild(p);
    });
    var src = sl.source === "gemini"
      ? "Written by " + sl.model + " on " + sl.when + " from the readings below, for the " + level + " level. It can be wrong. The traffic lights come from fixed rules, not from this text."
      : "Summary built from fixed rules and the readings below (" + level + " level).";
    hero.appendChild(el("p", "muted small", src));
    hero.appendChild(el("h3", "sm-h", "What this suggests for today"));
    var ul = el("ul", "plain");
    var acts = level === "beginner" ? o.actsB : (level === "expert" ? o.actsX : o.acts);
    acts.forEach(function (a) { ul.appendChild(el("li", null, a)); });
    hero.appendChild(ul);
    hero.appendChild(el("p", "muted small", "Areas: " + s.counts.red + " red, " + s.counts.yellow + " yellow, " + s.counts.green + " green. Newest data: " + (s.newest_data || "n/a") + "."));

    var stale = document.getElementById("stale");
    if (s.stale_days !== null && s.stale_days > 4) {
      stale.hidden = false;
      stale.textContent = "This page has not refreshed for " + s.stale_days + " days. Do not rely on it until it updates.";
    } else { stale.hidden = true; }

    var host = document.getElementById("clusters");
    host.textContent = "";
    Object.keys(s.clusters).forEach(function (name) {
      var items = s.items.filter(function (i) { return i.cluster === name; });
      if (!items.length) return;
      var c = s.clusters[name];
      var card = el("div", "card");
      var head = el("div", "cl-head");
      head.appendChild(el("h3", null, name));
      head.appendChild(name === "Background" ? chip("na", false, "Context only") : chip(c.status));
      card.appendChild(head);
      card.appendChild(el("p", "cl-blurb", c.blurb));
      var t = el("table");
      var th = el("thead"); var trh = el("tr");
      ["Indicator", "Now", "Trend", "Status"].forEach(function (h, k) {
        var x = el("th", k === 2 ? "hide-sm" : null, h); x.scope = "col"; trh.appendChild(x);
      });
      th.appendChild(trh); t.appendChild(th);
      var tb = el("tbody");
      items.forEach(function (it) {
        var tr = el("tr");
        var td = el("td");
        td.appendChild(el("span", "name", it.label));
        td.appendChild(el("span", "mean", pick(it, "meaning")));
        var det = el("details");
        if (level === "expert") det.open = true;
        det.appendChild(el("summary", null, level === "expert" ? "Definition, thresholds, source" : "What this measures"));
        det.appendChild(el("p", null, pick(it, "what")));
        if (level !== "beginner") {
          det.appendChild(el("p", "muted", "Draft thresholds: " + (it.threshold || "n/a") + ". Source: " + it.src + (it.asof ? ", as of " + it.asof : "") + "."));
        }
        td.appendChild(det);
        tr.appendChild(td);
        var v = el("td", "num", fmt(it));
        if (it.note && it.note !== "flip") v.appendChild(el("span", "mean", it.note));
        tr.appendChild(v);
        var sp = el("td", "hide-sm");
        if (it.series && it.series.length > 1) sp.appendChild(spark(it.series, it.label));
        tr.appendChild(sp);
        var st = el("td"); st.appendChild(chip(it.status)); tr.appendChild(st);
        tb.appendChild(tr);
      });
      t.appendChild(tb);
      card.appendChild(t);
      host.appendChild(card);
    });

    var ph = document.getElementById("paths");
    ph.textContent = "";
    s.paths.forEach(function (p) {
      var d = el("div", "path");
      var top = el("div", "path-top");
      top.appendChild(el("b", null, p.name));
      var ratio = p.max ? p.score / p.max : 0;
      var word = ratio >= 0.7 ? "Strong match" : (ratio >= 0.35 ? "Partial match" : "Little match");
      top.appendChild(el("span", "muted small", level === "expert" ? "score " + p.score + " / " + p.max : word));
      d.appendChild(top);
      var m = el("div", "meter");
      m.setAttribute("role", "img");
      m.setAttribute("aria-label", p.name + ": " + word);
      var n = Math.max(4, Math.round(p.max * 2));
      var on = Math.round(p.score * 2);
      for (var k = 0; k < n; k++) m.appendChild(el("i", k < on ? "on" : ""));
      d.appendChild(m);
      if (level !== "expert") {
        d.appendChild(el("div", "muted small", p.story + (p.drivers.length ? " Active now: " + p.drivers.join(", ") + "." : "")));
      } else if (p.drivers.length) {
        d.appendChild(el("div", "muted small", "Active: " + p.drivers.join(", ")));
      }
      ph.appendChild(d);
    });

    var cb = document.getElementById("combos");
    cb.textContent = "";
    var cl = (s.combos_levels && s.combos_levels[level]) || s.combos;
    cl.forEach(function (t) { cb.appendChild(el("li", null, t)); });
    document.getElementById("gen").textContent = "Generated " + s.generated + ". Rules are fixed and published in the repository.";
  }

  function setLevel(l, noRender) {
    if (LEVELS.indexOf(l) < 0) l = "medium";
    level = l;
    document.documentElement.setAttribute("data-level", l);
    Array.prototype.forEach.call(document.querySelectorAll("#levels button"), function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-level") === l ? "true" : "false");
    });
    try { localStorage.setItem("level", l); } catch (e) {}
    if (!noRender && data) render(data);
  }
  Array.prototype.forEach.call(document.querySelectorAll("#levels button"), function (b) {
    b.addEventListener("click", function () { setLevel(b.getAttribute("data-level")); });
  });
  var savedLevel = "medium";
  try { savedLevel = localStorage.getItem("level") || "medium"; } catch (e) {}
  setLevel(savedLevel, true);

  var btn = document.getElementById("theme");
  btn.addEventListener("click", function () {
    var cur = document.documentElement.getAttribute("data-theme");
    var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    var next = cur ? (cur === "dark" ? "light" : "dark") : (dark ? "light" : "dark");
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
  });
  try { var saved = localStorage.getItem("theme"); if (saved) document.documentElement.setAttribute("data-theme", saved); } catch (e) {}

  fetch("data/status.json", { cache: "no-store" }).then(function (r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function (s) { data = s; render(s); }).catch(function () {
    var h = document.getElementById("overall");
    h.textContent = "";
    h.appendChild(el("p", null, "Latest readings could not be loaded. Try again later."));
  });
})();
