#!/usr/bin/env python3
"""
render.py — read goals.yaml + recent state files + settings, write index.html.

The page is a paper-planner — header (date · progress · filter pills) over
goals grouped by time-of-day (morning · afternoon · evening · anytime), each
goal a card with a 7-day streak strip and (when streak ≥ 3) a flame badge.
Light + dark themes, switchable via the toggle in the header. Filter pills
isolate categories (health · mind · skills · social).

Special case: the `food` goal additionally shows today's kcal sum vs the
configured target plus a one-line macros readout. Food entries live on
each day's state YAML under a `food` list — Claude appends entries when
the user logs meals through the phone. Food's done/skipped status is
ALSO computed from that list (not from Yes/No completions) because
food isn't a yes/no question. It stays "open" during the day and
auto-strikes after end_hour.

Run any time the underlying data changes.
"""

from __future__ import annotations

import html
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent
GOALS_FILE = ROOT / "goals.yaml"
SETTINGS_FILE = ROOT / "settings.yaml"
STATE_DIR = ROOT / "state"
OUT_FILE = ROOT / "index.html"

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
WINDOW_ORDER = {"morning": 0, "afternoon": 1, "evening": 2, "any": 3}

HISTORY_DAYS = 7  # how many days of history to show in each card's strip

FOOD_GOAL_ID = "food"  # the one goal that gets a kcal/macros readout

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
    """Local 'today' respecting rollover_hour."""
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
    """Return {date_str: state} for the last `days` days, oldest first."""
    out: dict[str, dict] = {}
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        out[d] = load_state_for(d)
    return out


# ---------- computation ----------

def _split_hour(hr: float) -> tuple[int, int]:
    """Split a fractional hour like 5.5 into (5, 30)."""
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
    """True if local clock is past the configured end_hour today."""
    eh, em = _split_hour(end_hour)
    end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    return now >= end


def status_for(goal_id: str, completions: list[dict]) -> str:
    """Latest status for a goal: done | partial | skipped | open."""
    relevant = [c for c in completions if c.get("goal_id") == goal_id]
    if not relevant:
        return "open"
    return relevant[-1].get("status", "open")


def history_for(goal_id: str, recent_states: dict[str, dict]) -> list[tuple[str, str]]:
    """Return [(date_str, status), ...] oldest first."""
    out = []
    for d, state in recent_states.items():
        out.append((d, status_for(goal_id, state.get("completions", []))))
    return out


def current_streak(history: list[tuple[str, str]], today_str: str) -> int:
    """Count consecutive done-or-partial days ending at today (or yesterday if today is open)."""
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
    """Sum kcal + macros across a day's food entries. Safe with None / empty."""
    totals = {"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    for entry in food or []:
        for k in totals:
            v = entry.get(k)
            if isinstance(v, (int, float)):
                totals[k] += int(round(v))
    return totals


def food_status_for_day(day_state: dict, is_today: bool, past_end: bool) -> str:
    """Food status for one day, ignoring completions entirely.

    Food isn't a yes/no question — it's a "how much" question, so done/skipped
    is derived from whether any food entries exist that day.
      - today, still in the day:    "open"   (active, no fade)
      - today, after end_hour:      "done" if any entries logged, else "skipped"
      - past day:                   "done" if any entries logged, else "skipped"
    """
    if is_today and not past_end:
        return "open"
    return "done" if (day_state.get("food") or []) else "skipped"


def food_history(recent_states: dict[str, dict], today_str: str,
                 past_end: bool) -> list[tuple[str, str]]:
    """Drop-in replacement for history_for() that uses food entries instead
    of completion records."""
    out = []
    for d, s in recent_states.items():
        is_today = (d == today_str)
        out.append((d, food_status_for_day(s, is_today=is_today, past_end=past_end)))
    return out


# ---------- rendering ----------

def category_of(goal: dict) -> str:
    return goal.get("category", "health")


def food_body(state: dict, settings: dict) -> str:
    """Compact two-line kcal + macros readout for the Food card."""
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


def goal_card(goal: dict, history: list[tuple[str, str]], today_str: str,
              state: dict | None = None, settings: dict | None = None) -> str:
    title = html.escape(goal.get("title", goal.get("id", "")))
    cat = category_of(goal)

    today_status = "open"
    cells = []
    for d, status in history:
        is_today = d == today_str
        title_attr = html.escape(d)
        cell_class = f"cell cell--{status}" + (" cell--today" if is_today else "")
        cells.append(f'<span class="{cell_class}" title="{title_attr}: {status}"></span>')
        if is_today:
            today_status = status

    streak = current_streak(history, today_str)
    flame = (
        f'<span class="goal__flame">✦ {streak:02d}</span>'
        if streak >= 3
        else ''
    )

    # Food gets a kcal/macros readout between title and foot. Everything
    # else just has title → foot.
    extras = ""
    if goal.get("id") == FOOD_GOAL_ID and state is not None and settings is not None:
        extras = food_body(state, settings)

    return f"""
        <article class="goal goal--cat-{cat} goal--{today_status}" data-cat="{cat}">
          <h3 class="goal__title">{title}</h3>
          {extras}
          <div class="goal__foot">
            <div class="goal__strip" aria-label="{HISTORY_DAYS}-day history">{''.join(cells)}</div>
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
        cards_html.append(goal_card(g, hist, today_str,
                                    state=state, settings=settings))
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

    # bucket goals into sections by window
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

    # tiny inline script: theme + filter persistence + filter behavior
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
    b.addEventListener('click', function(){
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
    p.addEventListener('click', function(){ setFilter(p.dataset.filter); });
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
      <span>v1</span>
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
    recent_states = load_recent_states(today, HISTORY_DAYS)
    now = datetime.now(tz)

    out = render_html(
        settings=settings,
        goals_data=goals,
        recent_states=recent_states,
        today=today,
        now=now,
    )
    OUT_FILE.write_text(out)
    print(f"wrote {OUT_FILE} ({len(out)} bytes) for {today.strftime('%Y-%m-%d')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
