#!/usr/bin/env python3
"""
render.py — read goals.yaml + state files + settings, write index.html
            AND analytics.html.

`index.html` is the daily dashboard (today + last 7 days).
`analytics.html` is the history view (every day in state/, aggregate
per-goal stats: total %, current streak, longest streak).

Both share styling and the card shape. Both rebuild on every push via
the render workflow (.github/workflows/render.yml) and deploy to Pages.

Tap-to-mark: index.html embeds the webhook URL + shared secret as
window.LIFE_* globals so the inline JS can POST goal completions.
Sourced from $WEBHOOK_URL / $SHARED_SECRET env vars in CI, falling
back to settings.yaml for local renders.
"""

from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent
GOALS_FILE = ROOT / "goals.yaml"
SETTINGS_FILE = ROOT / "settings.yaml"
STATE_DIR = ROOT / "state"
OUT_INDEX = ROOT / "index.html"
OUT_ANALYTICS = ROOT / "analytics.html"

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
WINDOW_ORDER = {"morning": 0, "afternoon": 1, "evening": 2, "any": 3}

HISTORY_DAYS = 7  # dashboard strip
FOOD_GOAL_ID = "food"

CATEGORIES = [
    ("all",    "all"),
    ("health", "health"),
    ("mind",   "mind"),
    ("skills", "skills"),
    ("social", "social"),
]

SECTIONS = [
    ("morning",   "morning",   "06 — 12"),
    ("afternoon", "afternoon", "12 — 18"),
    ("evening",   "evening",   "18 — 23"),
    ("any",       "anytime",   ""),
]


# ---------- loading ----------

def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def today_local(tz: ZoneInfo, rollover_hour: int) -> datetime:
    now = datetime.now(tz)
    if now.hour < rollover_hour:
        now -= timedelta(days=1)
    return now


def load_state_for(date_str: str) -> dict:
    path = STATE_DIR / f"{date_str}.yaml"
    if path.exists():
        return load_yaml(path)
    return {"date": date_str, "completions": [], "notifications_sent": [], "scheduled_blocks": []}


def load_recent_states(today: datetime, days: int) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        out[d] = load_state_for(d)
    return out


def load_all_states() -> dict[str, dict]:
    """Every state/*.yaml on disk, oldest first."""
    out: dict[str, dict] = {}
    if not STATE_DIR.exists():
        return out
    for path in sorted(STATE_DIR.glob("*.yaml")):
        date_str = path.stem  # YYYY-MM-DD
        out[date_str] = load_yaml(path)
    return out


def all_dates_continuous(all_states: dict[str, dict], today: datetime) -> list[str]:
    """All dates from the earliest state file to today, oldest first,
    with no gaps. Missing days fall through to load_state_for() defaults."""
    if not all_states:
        return [today.strftime("%Y-%m-%d")]
    earliest = min(all_states.keys())
    start = datetime.strptime(earliest, "%Y-%m-%d")
    out = []
    cur = start
    end_str = today.strftime("%Y-%m-%d")
    while cur.strftime("%Y-%m-%d") <= end_str:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


# ---------- time ----------

def _split_hour(hr: float) -> tuple[int, int]:
    h = int(hr)
    m = int(round((hr - h) * 60))
    return h, m


def day_fraction_elapsed(now: datetime, start_hour: float, end_hour: float) -> float:
    sh, sm = _split_hour(start_hour)
    eh, em = _split_hour(end_hour)
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    if now <= start:
        return 0.0
    if now >= end:
        return 1.0
    return (now - start).total_seconds() / (end - start).total_seconds()


def is_past_end(now: datetime, end_hour: float) -> bool:
    eh, em = _split_hour(end_hour)
    end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    return now >= end


# ---------- per-goal status ----------

def status_for(goal_id: str, completions: list[dict]) -> str:
    relevant = [c for c in completions if c.get("goal_id") == goal_id]
    if not relevant:
        return "open"
    return relevant[-1].get("status", "open")


def history_for(goal_id: str, recent_states: dict[str, dict]) -> list[tuple[str, str]]:
    out = []
    for d, state in recent_states.items():
        out.append((d, status_for(goal_id, state.get("completions", []))))
    return out


def current_streak(history: list[tuple[str, str]], today_str: str) -> int:
    days = list(reversed(history))
    if days and days[0][0] == today_str and days[0][1] == "open":
        days = days[1:]
    streak = 0
    for d, status in days:
        if status in ("done", "partial"):
            streak += 1
        else:
            break
    return streak


def daily_food_totals(food: list[dict] | None) -> dict[str, int]:
    totals = {"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    for entry in food or []:
        for k in totals:
            v = entry.get(k)
            if isinstance(v, (int, float)):
                totals[k] += int(round(v))
    return totals


def food_status_for_day(day_state: dict, is_today: bool, past_end: bool) -> str:
    """Food status: open while today is in progress; done/skipped based on
    whether any entries were logged."""
    if is_today and not past_end:
        return "open"
    return "done" if (day_state.get("food") or []) else "skipped"


def food_history(recent_states: dict[str, dict], today_str: str,
                 past_end: bool) -> list[tuple[str, str]]:
    out = []
    for d, s in recent_states.items():
        is_today = (d == today_str)
        out.append((d, food_status_for_day(s, is_today=is_today, past_end=past_end)))
    return out


# ---------- aggregate stats (analytics) ----------

def goal_aggregate(goal_id: str, all_states: dict, all_dates: list[str],
                   today_str: str, past_end_today: bool) -> dict:
    """Aggregate stats for one goal across all_dates, oldest first."""
    done = 0
    skipped = 0
    open_count = 0
    longest = 0
    run = 0
    history: list[tuple[str, str]] = []

    for d in all_dates:
        state = all_states.get(d, {})
        is_today = (d == today_str)
        if goal_id == FOOD_GOAL_ID:
            status = food_status_for_day(state, is_today=is_today, past_end=past_end_today)
        else:
            status = status_for(goal_id, state.get("completions", []) or [])
        history.append((d, status))

        if status in ("done", "partial"):
            done += 1
            run += 1
            longest = max(longest, run)
        elif status == "skipped":
            skipped += 1
            run = 0
        else:  # open
            open_count += 1
            if not is_today:
                run = 0

    total = len(all_dates)
    pct = (done / total * 100) if total else 0
    return {
        "history": history,
        "done": done,
        "skipped": skipped,
        "open": open_count,
        "total": total,
        "pct": pct,
        "current_streak": run,
        "longest_streak": longest,
    }


def food_aggregate(all_states: dict, all_dates: list[str]) -> dict:
    """Daily averages + best/worst kcal days. Only includes days that
    have any food logged."""
    logged = []
    for d in all_dates:
        food = all_states.get(d, {}).get("food", []) or []
        if food:
            logged.append((d, daily_food_totals(food)))
    n = len(logged)
    if n == 0:
        return {"days_logged": 0, "total_days": len(all_dates)}
    return {
        "days_logged": n,
        "total_days": len(all_dates),
        "avg_kcal":    sum(t["kcal"]      for _, t in logged) // n,
        "avg_protein": sum(t["protein_g"] for _, t in logged) // n,
        "avg_carbs":   sum(t["carbs_g"]   for _, t in logged) // n,
        "avg_fat":     sum(t["fat_g"]     for _, t in logged) // n,
        "max_day":     max(logged, key=lambda x: x[1]["kcal"]),
        "min_day":     min(logged, key=lambda x: x[1]["kcal"]),
    }


# ---------- rendering (shared) ----------

def category_of(goal: dict) -> str:
    return goal.get("category", "health")


def food_body(state: dict, settings: dict) -> str:
    """Today's kcal + macros readout for the dashboard's Food card."""
    totals = daily_food_totals(state.get("food"))
    targets = settings.get("nutrition", {}) or {}
    kcal_target = int(targets.get("calorie_target", 2200))
    return (
        f'<div class="food__stats">'
        f'<p class="food__kcal">'
        f'<span class="food__kcal-num">{totals["kcal"]}</span>'
        f'<span class="food__kcal-sep"> / </span>'
        f'<span class="food__kcal-target">{kcal_target}</span>'
        f'<span class="food__kcal-unit">kcal</span>'
        f'</p>'
        f'<p class="food__macros">'
        f'p {totals["protein_g"]} · c {totals["carbs_g"]} · f {totals["fat_g"]}'
        f'</p>'
        f'</div>'
    )


def render_strip(history: list[tuple[str, str]], today_str: str, label: str) -> str:
    cells = []
    for d, status in history:
        is_today = d == today_str
        title_attr = html.escape(d)
        cell_class = f"cell cell--{status}" + (" cell--today" if is_today else "")
        cells.append(f'<span class="{cell_class}" title="{title_attr}: {status}"></span>')
    return f'<div class="goal__strip" aria-label="{label}">{"".join(cells)}</div>'


# ---------- rendering (dashboard) ----------

def goal_card(goal: dict, history: list[tuple[str, str]], today_str: str,
              state: dict | None = None, settings: dict | None = None) -> str:
    title = html.escape(goal.get("title", goal.get("id", "")))
    cat = category_of(goal)
    gid = html.escape(goal.get("id", ""))

    today_status = "open"
    for d, status in history:
        if d == today_str:
            today_status = status

    streak = current_streak(history, today_str)
    flame = (
        f'<span class="goal__flame">✦ {streak:02d}</span>'
        if streak >= 3 else ''
    )

    extras = ""
    if goal.get("id") == FOOD_GOAL_ID and state is not None and settings is not None:
        extras = food_body(state, settings)

    strip_html = render_strip(history, today_str, f"{HISTORY_DAYS}-day history")

    return f"""
        <article class="goal goal--cat-{cat} goal--{today_status}" data-cat="{cat}" data-id="{gid}">
          <h3 class="goal__title">{title}</h3>
          {extras}
          <div class="goal__foot">
            {strip_html}
            {flame}
          </div>
        </article>"""


def section_block(window_key: str, label: str, range_label: str,
                  goals: list[dict], recent_states: dict, today_str: str,
                  state: dict, settings: dict, past_end: bool) -> str:
    if not goals:
        return ""
    cards_html = []
    for g in goals:
        if g["id"] == FOOD_GOAL_ID:
            hist = food_history(recent_states, today_str, past_end)
        else:
            hist = history_for(g["id"], recent_states)
        cards_html.append(goal_card(g, hist, today_str, state=state, settings=settings))
    cards = "".join(cards_html)

    range_html = (
        f'<span class="sec-range">{range_label}</span>' if range_label else ''
    )
    return f"""
      <section class="section" data-window="{window_key}">
        <header class="sec-head">
          <h2 class="sec-title">{label}</h2>
          {range_html}
          <span class="sec-rule"></span>
          <span class="sec-count">{len(goals):02d}</span>
        </header>
        <div class="cards">{cards}
        </div>
      </section>"""


def filter_pills(active_goals: list[dict]) -> str:
    by_cat: dict[str, int] = {"all": len(active_goals)}
    for g in active_goals:
        c = category_of(g)
        by_cat[c] = by_cat.get(c, 0) + 1
    pills = []
    for cid, label in CATEGORIES:
        count = by_cat.get(cid, 0)
        pills.append(
            f'<button class="pill pill--{cid}" data-filter="{cid}" type="button">'
            f'<span class="pill__dot"></span>{label}'
            f'<span class="pill__count">{count}</span>'
            f'</button>'
        )
    return f'<nav class="filters" aria-label="Filter by category">{"".join(pills)}</nav>'


def render_html(*, settings: dict, goals_data: dict, recent_states: dict[str, dict],
                today: datetime, now: datetime) -> str:
    today_str = today.strftime("%Y-%m-%d")
    state = recent_states[today_str]
    completions = state.get("completions", [])
    notifications = state.get("notifications_sent", [])

    all_goals = goals_data.get("goals", [])
    active = [g for g in all_goals if g.get("active", True)]

    statuses = {g["id"]: status_for(g["id"], completions) for g in active}
    n_total = len(active)
    n_done = sum(1 for s in statuses.values() if s in ("done", "partial"))
    pct_done = (n_done / n_total * 100) if n_total else 0
    pct_done_int = int(round(pct_done))

    buckets: dict[str, list[dict]] = {}
    for g in active:
        buckets.setdefault(g.get("window", "any"), []).append(g)

    day = settings.get("day", {})
    end_hour = day.get("end_hour", 23)
    past_end = is_past_end(now, end_hour)

    section_html = "".join(
        section_block(wkey, label, rng, buckets.get(wkey, []), recent_states,
                      today_str, state, settings, past_end)
        for wkey, label, rng in SECTIONS
    )

    date_label = now.strftime("%-d %B %Y | %A")
    folio_label = today.strftime("%Y-%m-%d")
    title_date = now.strftime("%A, %B %-d")
    time_label = now.strftime("%H:%M")

    last_notif = (
        f"last nudge · {html.escape(notifications[-1].get('level', '?'))} "
        f"@ {html.escape(notifications[-1].get('at', '?'))}"
        if notifications
        else "no nudges sent today"
    )

    pills = filter_pills(active)

    webhook_cfg = settings.get("webhook", {}) or {}
    webhook_url = os.environ.get("WEBHOOK_URL") or webhook_cfg.get("url", "")
    webhook_secret = os.environ.get("SHARED_SECRET") or webhook_cfg.get("shared_secret", "")
    webhook_url_js = json.dumps(webhook_url)
    webhook_secret_js = json.dumps(webhook_secret)

    script = """
(function(){
  var body = document.body;
  function setTheme(t){
    body.dataset.theme = t;
    try { localStorage.setItem('life.theme', t); } catch(e){}
    document.querySelectorAll('[data-action=theme]').forEach(function(b){ b.textContent = t; });
  }
  var savedTheme = 'light';
  try { savedTheme = localStorage.getItem('life.theme') || 'light'; } catch(e){}
  setTheme(savedTheme);
  document.querySelectorAll('[data-action=theme]').forEach(function(b){
    b.addEventListener('click', function(e){
      e.stopPropagation();
      setTheme(body.dataset.theme === 'light' ? 'dark' : 'light');
    });
  });

  function setFilter(f){
    body.dataset.filter = f;
    try { localStorage.setItem('life.filter', f); } catch(e){}
    document.querySelectorAll('.pill').forEach(function(p){
      p.classList.toggle('is-active', p.dataset.filter === f);
    });
    document.querySelectorAll('.goal').forEach(function(g){
      g.hidden = !(f === 'all' || g.dataset.cat === f);
    });
    document.querySelectorAll('.section').forEach(function(s){
      s.hidden = s.querySelectorAll('.goal:not([hidden])').length === 0;
    });
  }
  var savedFilter = 'all';
  try { savedFilter = localStorage.getItem('life.filter') || 'all'; } catch(e){}
  setFilter(savedFilter);
  document.querySelectorAll('.pill').forEach(function(p){
    p.addEventListener('click', function(e){
      e.stopPropagation();
      setFilter(p.dataset.filter);
    });
  });

  // tap-to-mark
  var webhook = window.LIFE_WEBHOOK_URL || '';
  var secret  = window.LIFE_SECRET || '';
  function markDone(card){
    var goalId = card.dataset.id;
    if (!goalId || goalId === 'food') return;
    if (card.classList.contains('goal--done')) return;
    if (card.classList.contains('goal--partial')) return;
    if (card.classList.contains('is-marking')) return;
    if (!webhook || !secret){ console.warn('webhook not configured', goalId); return; }
    card.classList.add('is-marking');
    fetch(webhook + '?goal=' + encodeURIComponent(goalId) + '&status=done', {
      method: 'GET', headers: { 'X-Secret': secret }
    }).then(function(r){
      if (!r.ok){ return r.text().then(function(t){ throw new Error(r.status + ' ' + t); }); }
      card.classList.remove('goal--open');
      card.classList.add('goal--done');
    }).catch(function(err){
      console.error('mark failed', goalId, err);
      card.classList.add('goal--mark-error');
      setTimeout(function(){ card.classList.remove('goal--mark-error'); }, 2000);
    }).finally(function(){
      card.classList.remove('is-marking');
    });
  }
  document.querySelectorAll('.goal[data-id]').forEach(function(card){
    if (card.dataset.id === 'food') return;
    card.addEventListener('click', function(){ markDone(card); });
  });
})();
"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title_date)} — Life · Folio {folio_label}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,wght@0,400;0,500;1,400;1,500&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css" />
<script>window.LIFE_WEBHOOK_URL = {webhook_url_js}; window.LIFE_SECRET = {webhook_secret_js};</script>
</head>
<body data-theme="light" data-filter="all">
  <div class="paper">
    <header class="head">
      <div class="headline">
        <h1 class="date">{date_label}</h1>
        <span class="time">{time_label}</span>
        <button class="theme-btn" data-action="theme" type="button" aria-label="Toggle theme">light</button>
      </div>
      <div class="progress">
        <span class="progress__track"><span class="progress__fill" style="width: {pct_done:.1f}%"></span></span>
        <span class="progress__num">{pct_done_int}<span class="progress__suf">%</span></span>
        <span class="progress__count">{n_done:02d} / {n_total:02d}</span>
      </div>
      {pills}
    </header>

    <main class="main">{section_html}
    </main>

    <footer class="foot">
      <span>{folio_label}</span>
      <span class="foot__mid">{html.escape(last_notif)}</span>
      <span><a class="foot__link" href="analytics.html">analytics →</a></span>
    </footer>
  </div>
  <script>{script}</script>
</body>
</html>
"""


# ---------- rendering (analytics) ----------

def analytics_card(goal: dict, stats: dict, today_str: str) -> str:
    title = html.escape(goal.get("title", goal["id"]))
    cat = category_of(goal)
    gid = html.escape(goal.get("id", ""))
    pct = int(round(stats["pct"]))
    strip_html = render_strip(stats["history"], today_str, "full history")
    return f"""
        <article class="goal goal--cat-{cat} ana" data-cat="{cat}" data-id="{gid}">
          <h3 class="goal__title">{title}</h3>
          <p class="ana__count">
            <span class="ana__num">{stats['done']}</span><span class="ana__sep">/</span><span class="ana__dim">{stats['total']}</span>
            <span class="ana__pct">{pct}%</span>
          </p>
          <p class="ana__streak">
            now <span class="ana__num">{stats['current_streak']}</span>
            · best <span class="ana__num">{stats['longest_streak']}</span>
          </p>
          <div class="goal__foot">{strip_html}</div>
        </article>"""


def analytics_food_card(stats: dict, history: list[tuple[str, str]], today_str: str) -> str:
    strip_html = render_strip(history, today_str, "full history")
    if stats["days_logged"] == 0:
        body = '<p class="ana__empty">No food logged yet — log via Claude.</p>'
    else:
        body = (
            f'<p class="ana__count">'
            f'<span class="ana__num">{stats["avg_kcal"]}</span>'
            f'<span class="ana__unit">kcal avg</span>'
            f'</p>'
            f'<p class="food__macros">'
            f'p {stats["avg_protein"]} · c {stats["avg_carbs"]} · f {stats["avg_fat"]}'
            f'</p>'
            f'<p class="ana__streak">'
            f'logged <span class="ana__num">{stats["days_logged"]}</span>'
            f' / {stats["total_days"]} days'
            f'</p>'
        )
    return f"""
        <article class="goal goal--cat-health ana" data-cat="health" data-id="food">
          <h3 class="goal__title">Food</h3>
          {body}
          <div class="goal__foot">{strip_html}</div>
        </article>"""


def render_analytics_html(*, settings: dict, goals_data: dict,
                          all_states: dict, all_dates: list[str],
                          today: datetime, now: datetime) -> str:
    today_str = today.strftime("%Y-%m-%d")

    all_goals = goals_data.get("goals", [])
    active = [g for g in all_goals if g.get("active", True)]

    day = settings.get("day", {})
    end_hour = day.get("end_hour", 23)
    past_end_today = is_past_end(now, end_hour)

    # Bucket by window (mirrors dashboard)
    buckets: dict[str, list[dict]] = {}
    for g in active:
        buckets.setdefault(g.get("window", "any"), []).append(g)

    def render_section(wkey: str, label: str, range_label: str) -> str:
        goals = buckets.get(wkey, [])
        if not goals:
            return ""
        cards_html = []
        for g in goals:
            if g["id"] == FOOD_GOAL_ID:
                food_st = food_aggregate(all_states, all_dates)
                food_hist = []
                for d in all_dates:
                    is_today = (d == today_str)
                    food_hist.append((d, food_status_for_day(
                        all_states.get(d, {}), is_today=is_today,
                        past_end=past_end_today)))
                cards_html.append(analytics_food_card(food_st, food_hist, today_str))
            else:
                stats = goal_aggregate(g["id"], all_states, all_dates,
                                       today_str, past_end_today)
                cards_html.append(analytics_card(g, stats, today_str))
        range_html = f'<span class="sec-range">{range_label}</span>' if range_label else ''
        return f"""
      <section class="section" data-window="{wkey}">
        <header class="sec-head">
          <h2 class="sec-title">{label}</h2>
          {range_html}
          <span class="sec-rule"></span>
          <span class="sec-count">{len(goals):02d}</span>
        </header>
        <div class="cards">{"".join(cards_html)}
        </div>
      </section>"""

    section_html = "".join(render_section(w, l, r) for w, l, r in SECTIONS)

    earliest = all_dates[0]
    days_count = len(all_dates)
    date_range_label = f"{earliest} → {today_str} · {days_count} day{'' if days_count == 1 else 's'}"

    pills = filter_pills(active)
    title = "Analytics"

    script = """
(function(){
  var body = document.body;
  function setTheme(t){
    body.dataset.theme = t;
    try { localStorage.setItem('life.theme', t); } catch(e){}
    document.querySelectorAll('[data-action=theme]').forEach(function(b){ b.textContent = t; });
  }
  var savedTheme = 'light';
  try { savedTheme = localStorage.getItem('life.theme') || 'light'; } catch(e){}
  setTheme(savedTheme);
  document.querySelectorAll('[data-action=theme]').forEach(function(b){
    b.addEventListener('click', function(e){
      e.stopPropagation();
      setTheme(body.dataset.theme === 'light' ? 'dark' : 'light');
    });
  });
  function setFilter(f){
    body.dataset.filter = f;
    try { localStorage.setItem('life.filter', f); } catch(e){}
    document.querySelectorAll('.pill').forEach(function(p){
      p.classList.toggle('is-active', p.dataset.filter === f);
    });
    document.querySelectorAll('.goal').forEach(function(g){
      g.hidden = !(f === 'all' || g.dataset.cat === f);
    });
    document.querySelectorAll('.section').forEach(function(s){
      s.hidden = s.querySelectorAll('.goal:not([hidden])').length === 0;
    });
  }
  var savedFilter = 'all';
  try { savedFilter = localStorage.getItem('life.filter') || 'all'; } catch(e){}
  setFilter(savedFilter);
  document.querySelectorAll('.pill').forEach(function(p){
    p.addEventListener('click', function(e){
      e.stopPropagation();
      setFilter(p.dataset.filter);
    });
  });
})();
"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Analytics — Life · {date_range_label}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,wght@0,400;0,500;1,400;1,500&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css" />
</head>
<body data-theme="light" data-filter="all" data-page="analytics">
  <div class="paper">
    <header class="head">
      <div class="headline">
        <h1 class="date">{title}</h1>
        <span class="time">{html.escape(date_range_label)}</span>
        <button class="theme-btn" data-action="theme" type="button" aria-label="Toggle theme">light</button>
      </div>
      {pills}
    </header>

    <main class="main">{section_html}
    </main>

    <footer class="foot">
      <span>{today_str}</span>
      <span class="foot__mid">aggregate stats across all of state/</span>
      <span><a class="foot__link" href="index.html">← dashboard</a></span>
    </footer>
  </div>
  <script>{script}</script>
</body>
</html>
"""


# ---------- entry point ----------

def main() -> int:
    if not GOALS_FILE.exists():
        print(f"missing {GOALS_FILE}", file=sys.stderr)
        return 1
    if not SETTINGS_FILE.exists():
        print(f"missing {SETTINGS_FILE} (copy from settings.example.yaml)", file=sys.stderr)
        return 1

    settings = load_yaml(SETTINGS_FILE)
    goals = load_yaml(GOALS_FILE)

    tz_name = settings.get("user", {}).get("timezone", "UTC")
    tz = ZoneInfo(tz_name)
    rollover = settings.get("day", {}).get("rollover_hour", 3)

    today = today_local(tz, rollover)
    now = datetime.now(tz)

    # Dashboard (7-day window)
    recent_states = load_recent_states(today, HISTORY_DAYS)
    dash_html = render_html(
        settings=settings,
        goals_data=goals,
        recent_states=recent_states,
        today=today,
        now=now,
    )
    OUT_INDEX.write_text(dash_html)
    print(f"wrote {OUT_INDEX} ({len(dash_html)} bytes) for {today.strftime('%Y-%m-%d')}")

    # Analytics (full history)
    all_states = load_all_states()
    # ensure today is included even if no state file exists yet
    if today.strftime("%Y-%m-%d") not in all_states:
        all_states[today.strftime("%Y-%m-%d")] = load_state_for(today.strftime("%Y-%m-%d"))
    all_dates = all_dates_continuous(all_states, today)
    ana_html = render_analytics_html(
        settings=settings,
        goals_data=goals,
        all_states=all_states,
        all_dates=all_dates,
        today=today,
        now=now,
    )
    OUT_ANALYTICS.write_text(ana_html)
    print(f"wrote {OUT_ANALYTICS} ({len(ana_html)} bytes) covering {len(all_dates)} day(s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
