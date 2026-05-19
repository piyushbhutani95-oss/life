#!/usr/bin/env python3
"""
render.py — read goals.yaml + state files + settings, write index.html
            AND analytics.html.

`index.html` is the daily dashboard (today + last 7 days).
`analytics.html` is the redesigned weekly-review view: hero scan +
category heatmap + auto-picked wins/drifts + a distinct food block +
an all-time almanac + an expandable per-goal table. Range toggle
(7d / 30d / all) is server-rendered as 3 versions, hidden via CSS.

Both share styling and the card shape (where applicable). Both rebuild
on every push via the render workflow (.github/workflows/render.yml)
and deploy to Pages.

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
TODOS_FILE = STATE_DIR / "todos.yaml"
OUT_INDEX = ROOT / "index.html"
OUT_ANALYTICS = ROOT / "analytics.html"

DONE_VISIBLE = 5  # how many recently-checked todos to show in the side panel

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

RANGES = [("7d", "7d", 7), ("30d", "30d", 30), ("all", "all", None)]
DEFAULT_RANGE = "7d"

DOW_LABELS = ["M", "T", "W", "T", "F", "S", "S"]


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


# ---------- todos ----------

def load_todos() -> list[dict]:
    """All entries from state/todos.yaml, untouched. Done/open are sorted later."""
    if not TODOS_FILE.exists():
        return []
    data = load_yaml(TODOS_FILE)
    items = data.get("todos") if isinstance(data, dict) else None
    return list(items or [])


def render_todo_panel(todos: list[dict]) -> str:
    """The side-panel HTML. Closed by default; toggled by inline JS."""
    open_todos = [t for t in todos if not t.get("done_at")]
    done_todos = [t for t in todos if t.get("done_at")]
    # Most-recently-done first, cap to DONE_VISIBLE
    done_todos.sort(key=lambda t: t.get("done_at") or "", reverse=True)
    done_todos = done_todos[:DONE_VISIBLE]

    def li(t: dict, done: bool) -> str:
        tid = html.escape(str(t.get("id", "")))
        txt = html.escape(str(t.get("text", "")))
        cls = "todo todo--done" if done else "todo todo--open"
        return (
            f'<li class="{cls}" data-id="{tid}">'
            f'<button class="todo__check" type="button" aria-label="toggle done">'
            f'<span class="todo__check-mark" aria-hidden="true"></span>'
            f'</button>'
            f'<span class="todo__text">{txt}</span>'
            f'</li>'
        )

    open_html = "".join(li(t, False) for t in open_todos)
    if not open_html:
        open_html = (
            '<li class="todo todo--empty">nothing here · type below '
            'or ask Claude</li>'
        )
    done_html = "".join(li(t, True) for t in done_todos)
    done_section = (
        '<div class="todos__done-head">recently done</div>'
        f'<ul class="todos__list todos__list--done">{done_html}</ul>'
        if done_html else ''
    )

    count = len(open_todos)
    count_html = (
        f'<span class="todos__handle-count">{count}</span>'
        if count else ''
    )

    return f'''
        <aside class="todos" data-todos-open="false" aria-label="To-do list">
          <button class="todos__handle" type="button"
                  data-action="todos-toggle" aria-label="Open to-do list">
            <span class="todos__handle-label">to-do</span>
            {count_html}
          </button>
          <div class="todos__drawer" role="dialog" aria-label="To-do list">
            <header class="todos__head">
              <h2 class="todos__title">to-do</h2>
              <button class="todos__close" type="button"
                      data-action="todos-toggle" aria-label="Close">×</button>
            </header>
            <ul class="todos__list todos__list--open">{open_html}</ul>
            <form class="todos__add" data-form="todo-add" autocomplete="off">
              <input class="todos__input" type="text" name="text"
                     placeholder="add a to-do…" maxlength="200" />
            </form>
            {done_section}
          </div>
        </aside>'''


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


# ---------- aggregate stats (used by analytics) ----------

def _status_for_day(goal_id: str, state: dict, is_today: bool,
                    past_end_today: bool) -> str:
    if goal_id == FOOD_GOAL_ID:
        return food_status_for_day(state, is_today=is_today, past_end=past_end_today)
    return status_for(goal_id, state.get("completions", []) or [])


def goal_aggregate(goal_id: str, all_states: dict, dates: list[str],
                   today_str: str, past_end_today: bool) -> dict:
    """Aggregate stats for one goal across `dates`, oldest first."""
    done = 0
    skipped = 0
    open_count = 0
    longest = 0
    run = 0
    history: list[tuple[str, str]] = []

    for d in dates:
        state = all_states.get(d, {})
        is_today = (d == today_str)
        status = _status_for_day(goal_id, state, is_today, past_end_today)
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

    total = len(dates)
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


def period_dates(all_dates: list[str], range_key: str,
                 today_str: str) -> tuple[list[str], list[str]]:
    """(current_period, prior_period) date slices for delta callouts."""
    if range_key == "all":
        return all_dates, []
    n = 7 if range_key == "7d" else 30
    if today_str in all_dates:
        end_idx = all_dates.index(today_str) + 1
    else:
        end_idx = len(all_dates)
    cur = all_dates[max(0, end_idx - n):end_idx]
    prior = all_dates[max(0, end_idx - 2 * n):max(0, end_idx - n)]
    return cur, prior


def period_summary(active_goals: list[dict], all_states: dict,
                   dates: list[str], today_str: str,
                   past_end_today: bool) -> dict:
    """Hero summary: total done/total, by-category breakdown, strongest/drifting."""
    total = 0
    done = 0
    by_cat: dict[str, list[int]] = {}
    for g in active_goals:
        cat = category_of(g)
        by_cat.setdefault(cat, [0, 0])
        for d in dates:
            state = all_states.get(d, {})
            is_today = (d == today_str)
            status = _status_for_day(g["id"], state, is_today, past_end_today)
            total += 1
            by_cat[cat][1] += 1
            if status in ("done", "partial"):
                done += 1
                by_cat[cat][0] += 1

    cat_pcts = {c: (v[0] / v[1] * 100 if v[1] else 0) for c, v in by_cat.items()}
    sorted_cats = sorted(cat_pcts.items(), key=lambda x: x[1], reverse=True)
    strongest = sorted_cats[0][0] if sorted_cats else None
    drifting = sorted_cats[-1][0] if len(sorted_cats) > 1 else None

    return {
        "done": done,
        "total": total,
        "pct": (done / total * 100) if total else 0,
        "by_cat": by_cat,
        "cat_pcts": cat_pcts,
        "strongest": strongest,
        "drifting": drifting,
    }


def category_heatmap(active_goals: list[dict], all_states: dict,
                     dates: list[str], today_str: str,
                     past_end_today: bool) -> dict[str, list[tuple[str, int, int]]]:
    """Per category, per date: (date, done, total)."""
    out: dict[str, list[tuple[str, int, int]]] = {}
    for cat in ["health", "mind", "skills", "social"]:
        cat_goals = [g for g in active_goals if category_of(g) == cat]
        row = []
        for d in dates:
            state = all_states.get(d, {})
            is_today = (d == today_str)
            done_n = 0
            for g in cat_goals:
                status = _status_for_day(g["id"], state, is_today, past_end_today)
                if status in ("done", "partial"):
                    done_n += 1
            row.append((d, done_n, len(cat_goals)))
        out[cat] = row
    return out


def wins_drifts(active_goals: list[dict], all_states: dict,
                cur_dates: list[str], prior_dates: list[str],
                today_str: str, past_end_today: bool) -> dict:
    """Auto-pick wins and drifts. Capped at 3 each, deduped by goal."""
    wins: list[dict] = []
    drifts: list[dict] = []

    for g in active_goals:
        cur = goal_aggregate(g["id"], all_states, cur_dates, today_str, past_end_today)
        prior = (goal_aggregate(g["id"], all_states, prior_dates,
                                today_str, past_end_today)
                 if prior_dates else None)

        meta = {"goal_id": g["id"], "title": g.get("title", g["id"]),
                "category": category_of(g)}

        # Win: strong active streak
        if cur["current_streak"] >= 5:
            wins.append({**meta, "label": f"{cur['current_streak']}-day streak",
                         "stamp": "active", "kind": "streak",
                         "rank": 100 + cur["current_streak"]})
        elif cur["current_streak"] >= 3 and cur["total"] >= 5:
            wins.append({**meta, "label": f"{cur['current_streak']}-day streak",
                         "stamp": "", "kind": "streak",
                         "rank": 50 + cur["current_streak"]})

        # Win/drift: big swing vs prior period
        if prior and prior["total"] >= 3 and cur["total"] >= 3:
            delta = cur["pct"] - prior["pct"]
            if delta >= 25:
                wins.append({**meta, "label": f"+{int(round(delta))}% vs prior",
                             "stamp": "", "kind": "jump",
                             "rank": 60 + int(delta)})
            elif delta <= -25:
                drifts.append({**meta, "label": f"{int(round(delta))}% vs prior",
                               "stamp": "", "kind": "drop",
                               "rank": 60 + int(-delta)})

        # Drift: zero this period
        if cur["done"] == 0 and cur["total"] >= 3:
            drifts.append({**meta, "label": f"0 / {cur['total']} this period",
                           "stamp": "", "kind": "zero", "rank": 90})

        # Drift: previously had a streak that has now broken
        if prior and prior["longest_streak"] >= 3 and cur["current_streak"] == 0 \
                and cur["done"] < cur["total"]:
            # find date of last "done" within cur_dates
            last_done = None
            for d, s in reversed(cur["history"]):
                if s in ("done", "partial"):
                    last_done = d
                    break
            stamp = f"broken {last_done}" if last_done else "broken"
            drifts.append({**meta, "label": f"streak of {prior['longest_streak']} broken",
                           "stamp": stamp, "kind": "broke",
                           "rank": 70 + prior["longest_streak"]})

    # Dedup by goal_id, keep highest-ranked
    def dedup(items: list[dict]) -> list[dict]:
        items.sort(key=lambda x: x["rank"], reverse=True)
        seen = set()
        out = []
        for it in items:
            if it["goal_id"] in seen:
                continue
            seen.add(it["goal_id"])
            out.append(it)
        return out

    return {"wins": dedup(wins)[:3], "drifts": dedup(drifts)[:3]}


def food_period(all_states: dict, dates: list[str], targets: dict) -> dict:
    """Daily kcal series + macro averages for the period."""
    daily: list[tuple[str, int, int, int, int, bool]] = []
    for d in dates:
        food = all_states.get(d, {}).get("food", []) or []
        if food:
            t = daily_food_totals(food)
            daily.append((d, t["kcal"], t["protein_g"], t["carbs_g"], t["fat_g"], True))
        else:
            daily.append((d, 0, 0, 0, 0, False))
    logged = [x for x in daily if x[5]]
    n = len(logged)
    base = {
        "days_logged": n,
        "total_days": len(dates),
        "daily": daily,
        "kcal_target":    int(targets.get("calorie_target", 2200)),
        "protein_target": int(targets.get("protein_g_target", 130)),
        "carbs_target":   int(targets.get("carbs_g_target", 250)),
        "fat_target":     int(targets.get("fat_g_target", 70)),
    }
    if n == 0:
        return base
    base.update({
        "avg_kcal":    sum(x[1] for x in logged) // n,
        "avg_protein": sum(x[2] for x in logged) // n,
        "avg_carbs":   sum(x[3] for x in logged) // n,
        "avg_fat":     sum(x[4] for x in logged) // n,
        "best_day":    max(logged, key=lambda x: x[1]),
        "worst_day":   min(logged, key=lambda x: x[1]),
    })
    return base


def goal_dow_pattern(goal_id: str, all_states: dict, dates: list[str],
                     today_str: str, past_end_today: bool) -> list[float | None]:
    """Returns [Mon..Sun] = pct done on that weekday, None if no data."""
    by_dow = [[0, 0] for _ in range(7)]
    for d in dates:
        dow = datetime.strptime(d, "%Y-%m-%d").weekday()
        state = all_states.get(d, {})
        is_today = (d == today_str)
        status = _status_for_day(goal_id, state, is_today, past_end_today)
        by_dow[dow][1] += 1
        if status in ("done", "partial"):
            by_dow[dow][0] += 1
    return [(v[0] / v[1] * 100) if v[1] else None for v in by_dow]


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
                today: datetime, now: datetime,
                todos: list[dict] | None = None) -> str:
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
    # /api/todo lives on the same Vercel deployment as /api/mark
    todo_url = webhook_url.replace("/api/mark", "/api/todo") if webhook_url else ""
    webhook_url_js = json.dumps(webhook_url)
    webhook_secret_js = json.dumps(webhook_secret)
    todo_url_js = json.dumps(todo_url)

    todo_panel_html = render_todo_panel(todos or [])

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

  // ── to-do side panel ──────────────────────────────────────
  var todoPanel = document.querySelector('.todos');
  if (!todoPanel) return;
  var todoUrl    = window.LIFE_TODO_URL || '';
  var todoSecret = window.LIFE_SECRET || '';

  function setTodosOpen(open){
    todoPanel.dataset.todosOpen = open ? 'true' : 'false';
    try { localStorage.setItem('life.todos.open', open ? '1' : '0'); } catch(e){}
  }
  var savedTodos = '0';
  try { savedTodos = localStorage.getItem('life.todos.open') || '0'; } catch(e){}
  setTodosOpen(savedTodos === '1');
  document.querySelectorAll('[data-action=todos-toggle]').forEach(function(b){
    b.addEventListener('click', function(e){
      e.stopPropagation();
      setTodosOpen(todoPanel.dataset.todosOpen !== 'true');
    });
  });
  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape' && todoPanel.dataset.todosOpen === 'true'){
      setTodosOpen(false);
    }
  });

  function refreshTodoCount(){
    var openCount = todoPanel.querySelectorAll('.todos__list--open .todo--open').length;
    var badge = todoPanel.querySelector('.todos__handle-count');
    if (openCount > 0){
      if (!badge){
        badge = document.createElement('span');
        badge.className = 'todos__handle-count';
        todoPanel.querySelector('.todos__handle').appendChild(badge);
      }
      badge.textContent = openCount;
    } else if (badge){
      badge.remove();
    }
  }

  function todoFetch(qs){
    return fetch(todoUrl + '?' + qs, {
      method: 'GET', headers: { 'X-Secret': todoSecret }
    }).then(function(r){
      if (!r.ok) return r.text().then(function(t){ throw new Error(r.status + ' ' + t); });
      return r.text().then(function(t){
        try { return JSON.parse(t); } catch(e){ return {}; }
      });
    });
  }

  function toggleTodo(li){
    if (!li || li.classList.contains('is-busy')) return;
    var id = li.dataset.id;
    if (!id) return;
    if (!todoUrl || !todoSecret){ console.warn('todo api not configured'); return; }
    var isDone = li.classList.contains('todo--done');
    var action = isDone ? 'uncheck' : 'check';
    li.classList.add('is-busy');
    // Optimistic flip
    li.classList.toggle('todo--done');
    li.classList.toggle('todo--open');
    refreshTodoCount();
    todoFetch('action=' + action + '&id=' + encodeURIComponent(id))
      .catch(function(err){
        console.error('todo toggle failed', err);
        li.classList.toggle('todo--done');
        li.classList.toggle('todo--open');
        li.classList.add('todo--error');
        setTimeout(function(){ li.classList.remove('todo--error'); }, 2000);
        refreshTodoCount();
      })
      .finally(function(){ li.classList.remove('is-busy'); });
  }

  function bindCheck(li){
    var btn = li.querySelector('.todo__check');
    if (!btn) return;
    btn.addEventListener('click', function(e){
      e.stopPropagation();
      toggleTodo(li);
    });
  }
  todoPanel.querySelectorAll('.todo[data-id]').forEach(bindCheck);

  var addForm = todoPanel.querySelector('[data-form=todo-add]');
  if (addForm){
    addForm.addEventListener('submit', function(e){
      e.preventDefault();
      var input = addForm.querySelector('input');
      var text = (input.value || '').trim();
      if (!text) return;
      if (!todoUrl || !todoSecret){ console.warn('todo api not configured'); return; }
      input.disabled = true;
      todoFetch('action=add&text=' + encodeURIComponent(text))
        .then(function(r){
          var newId = (r && r.id) || ('t-' + Date.now());
          // Drop any empty placeholder
          var ul = todoPanel.querySelector('.todos__list--open');
          var empty = ul.querySelector('.todo--empty');
          if (empty) empty.remove();
          // Prepend the new item
          var li = document.createElement('li');
          li.className = 'todo todo--open';
          li.dataset.id = newId;
          li.innerHTML = '<button class="todo__check" type="button" aria-label="toggle done">' +
                         '<span class="todo__check-mark" aria-hidden="true"></span></button>' +
                         '<span class="todo__text"></span>';
          li.querySelector('.todo__text').textContent = text;
          bindCheck(li);
          ul.appendChild(li);
          input.value = '';
          refreshTodoCount();
        })
        .catch(function(err){
          console.error('todo add failed', err);
          input.classList.add('todos__input--error');
          setTimeout(function(){ input.classList.remove('todos__input--error'); }, 1500);
        })
        .finally(function(){
          input.disabled = false;
          input.focus();
        });
    });
  }
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
<script>window.LIFE_WEBHOOK_URL = {webhook_url_js}; window.LIFE_SECRET = {webhook_secret_js}; window.LIFE_TODO_URL = {todo_url_js};</script>
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
  {todo_panel_html}
  <script>{script}</script>
</body>
</html>
"""


# ---------- rendering (analytics — redesigned) ----------

def _fmt_short(date_str: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%-d %b")


def _period_label(dates: list[str]) -> str:
    if not dates:
        return "no data"
    if len(dates) == 1:
        return _fmt_short(dates[0])
    return f"{_fmt_short(dates[0])} — {_fmt_short(dates[-1])}"


def _intensity_step(pct: float) -> int:
    """0 (none) → 4 (full)."""
    if pct <= 0:
        return 0
    if pct < 25:
        return 1
    if pct < 50:
        return 2
    if pct < 75:
        return 3
    return 4


def render_hero(summary: dict, dates: list[str]) -> str:
    """Single-sentence period summary."""
    period = _period_label(dates)
    done = summary["done"]
    total = summary["total"]
    pct = int(round(summary["pct"]))
    strongest = summary.get("strongest")
    drifting = summary.get("drifting")

    parts = [
        f'<span class="ana-hero__period">{html.escape(period)}</span>',
        f'<span class="ana-hero__sep">·</span>',
        f'<span class="ana-hero__count"><b>{done}</b> / {total}</span>',
        f'<span class="ana-hero__pct">{pct}%</span>',
    ]
    if strongest:
        parts.append(
            f'<span class="ana-hero__sep">·</span>'
            f'<span class="ana-hero__cat">strongest <b class="cat cat--{strongest}">{strongest}</b></span>'
        )
    if drifting and drifting != strongest:
        parts.append(
            f'<span class="ana-hero__sep">·</span>'
            f'<span class="ana-hero__cat">drifting <b class="cat cat--{drifting}">{drifting}</b></span>'
        )
    return f'<p class="ana-hero__sentence">{"".join(parts)}</p>'


def render_cat_heatmap(heatmap: dict, dates: list[str]) -> str:
    """4-row × N-day grid. Cell intensity = pct done that day for that category."""
    rows = []
    for cat in ["health", "mind", "skills", "social"]:
        row_data = heatmap.get(cat, [])
        cells = []
        for d, done_n, total_n in row_data:
            pct = (done_n / total_n * 100) if total_n else 0
            step = _intensity_step(pct)
            cells.append(
                f'<span class="hcell hcell--cat-{cat} hcell--i{step}" '
                f'title="{html.escape(d)} · {cat}: {done_n}/{total_n}"></span>'
            )
        rows.append(
            f'<div class="ana-hm__row">'
            f'<span class="ana-hm__label cat--{cat}">{cat}</span>'
            f'<div class="ana-hm__cells" style="--cols: {len(row_data)}">'
            f'{"".join(cells)}'
            f'</div>'
            f'</div>'
        )
    return f'<div class="ana-hm">{"".join(rows)}</div>'


def render_callouts(picks: dict) -> str:
    """Wins + Drifts side-by-side."""
    def col(items: list[dict], kind: str, label: str, empty: str) -> str:
        if not items:
            inner = f'<li class="ana-callout ana-callout--empty">{empty}</li>'
        else:
            lis = []
            for it in items:
                stamp_html = (
                    f'<span class="ana-callout__stamp">{html.escape(it["stamp"])}</span>'
                    if it.get("stamp") else ''
                )
                lis.append(
                    f'<li class="ana-callout ana-callout--{it["kind"]}" data-cat="{it["category"]}">'
                    f'<span class="ana-callout__dot cat--{it["category"]}"></span>'
                    f'<span class="ana-callout__title">{html.escape(it["title"])}</span>'
                    f'<span class="ana-callout__label">{html.escape(it["label"])}</span>'
                    f'{stamp_html}'
                    f'</li>'
                )
            inner = "".join(lis)
        return (
            f'<div class="ana-co__col ana-co__col--{kind}">'
            f'<h3 class="ana-co__head">{label}</h3>'
            f'<ul class="ana-co__list">{inner}</ul>'
            f'</div>'
        )
    return (
        f'<div class="ana-co">'
        f'{col(picks["wins"], "wins", "Wins", "Nothing standout this period.")}'
        f'{col(picks["drifts"], "drifts", "Drifts", "Nothing slipping. Nice.")}'
        f'</div>'
    )


def _kcal_sparkline(food: dict) -> str:
    """SVG line of daily kcal vs target. Misses render as gaps."""
    daily = food.get("daily", [])
    if not daily:
        return ""
    target = food.get("kcal_target", 2200)
    values = [(x[1] if x[5] else None) for x in daily]
    valid = [v for v in values if v is not None]
    if not valid:
        return ""
    vmax = max(max(valid), target) * 1.15
    vmin = 0
    n = len(values)
    w, h = 280, 40
    # Target line
    ty = h - (target - vmin) / (vmax - vmin) * h
    # Build polyline segments split on None
    segments: list[list[str]] = [[]]
    for i, v in enumerate(values):
        if v is None:
            if segments[-1]:
                segments.append([])
            continue
        x = (i / max(n - 1, 1)) * w
        y = h - ((v - vmin) / (vmax - vmin)) * h
        segments[-1].append(f"{x:.1f},{y:.1f}")
    # Dots for actual logged days
    dots = []
    for i, v in enumerate(values):
        if v is None:
            continue
        x = (i / max(n - 1, 1)) * w
        y = h - ((v - vmin) / (vmax - vmin)) * h
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" />')
    polylines = "".join(
        f'<polyline points="{" ".join(s)}" fill="none" />' for s in segments if s
    )
    return (
        f'<svg class="kcal-spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
        f'<line class="kcal-spark__target" x1="0" y1="{ty:.1f}" x2="{w}" y2="{ty:.1f}" '
        f'stroke-dasharray="3 3" />'
        f'{polylines}'
        f'<g class="kcal-spark__dots">{"".join(dots)}</g>'
        f'</svg>'
    )


def render_food_block(food: dict) -> str:
    """Distinct full-width block: big number, sparkline, macro stack."""
    if food["days_logged"] == 0:
        return (
            f'<section class="ana-food">'
            f'<header class="ana-food__head">'
            f'<h3 class="ana-food__title">Food</h3>'
            f'<span class="ana-food__sub">no entries logged this period — log via Claude</span>'
            f'</header></section>'
        )

    kt = food["kcal_target"]
    avg = food["avg_kcal"]
    pt = food["protein_target"]; ct = food["carbs_target"]; ft = food["fat_target"]
    p = food["avg_protein"]; c = food["avg_carbs"]; f = food["avg_fat"]
    days = food["days_logged"]; total = food["total_days"]

    spark = _kcal_sparkline(food)

    def macro_bar(name: str, val: int, target: int, cls: str) -> str:
        pct = min(100, (val / target * 100) if target else 0)
        return (
            f'<div class="ana-food__macro">'
            f'<div class="ana-food__macro-head">'
            f'<span class="ana-food__macro-name">{name}</span>'
            f'<span class="ana-food__macro-val">{val}<span class="ana-food__macro-tgt"> / {target}g</span></span>'
            f'</div>'
            f'<div class="ana-food__macro-track">'
            f'<div class="ana-food__macro-fill ana-food__macro-fill--{cls}" style="width: {pct:.1f}%"></div>'
            f'</div></div>'
        )

    best = food.get("best_day"); worst = food.get("worst_day")
    extra = ""
    if best and worst and best != worst:
        extra = (
            f'<div class="ana-food__detail">'
            f'<span>highest <b>{best[1]}</b> kcal · {_fmt_short(best[0])}</span>'
            f'<span>lowest <b>{worst[1]}</b> kcal · {_fmt_short(worst[0])}</span>'
            f'</div>'
        )

    return f'''
        <section class="ana-food">
          <header class="ana-food__head">
            <h3 class="ana-food__title">Food</h3>
            <span class="ana-food__sub">{days} / {total} days logged</span>
          </header>
          <div class="ana-food__body">
            <div class="ana-food__big">
              <span class="ana-food__big-num">{avg}</span>
              <span class="ana-food__big-sep">/</span>
              <span class="ana-food__big-tgt">{kt}</span>
              <span class="ana-food__big-unit">kcal avg</span>
            </div>
            <div class="ana-food__chart">{spark}</div>
          </div>
          <div class="ana-food__macros">
            {macro_bar("protein", p, pt, "p")}
            {macro_bar("carbs", c, ct, "c")}
            {macro_bar("fat", f, ft, "f")}
          </div>
          {extra}
        </section>'''


def render_per_goal_table(active_goals: list[dict], all_states: dict,
                          dates: list[str], today_str: str,
                          past_end_today: bool) -> str:
    """Thin row per goal. Click row → expand to dow pattern."""
    rows = []
    for g in active_goals:
        gid = g["id"]
        cat = category_of(g)
        title = html.escape(g.get("title", gid))
        stats = goal_aggregate(gid, all_states, dates, today_str, past_end_today)
        pct = int(round(stats["pct"]))
        strip = render_strip(stats["history"], today_str, "period history")
        dow = goal_dow_pattern(gid, all_states, dates, today_str, past_end_today)
        dow_bars = []
        for i, v in enumerate(dow):
            if v is None:
                dow_bars.append(
                    f'<div class="dow__bar dow__bar--empty">'
                    f'<span class="dow__lbl">{DOW_LABELS[i]}</span></div>'
                )
            else:
                step = _intensity_step(v)
                dow_bars.append(
                    f'<div class="dow__bar dow__bar--cat-{cat} dow__bar--i{step}" '
                    f'title="{DOW_LABELS[i]}: {int(round(v))}%">'
                    f'<span class="dow__lbl">{DOW_LABELS[i]}</span></div>'
                )
        rows.append(f'''
          <li class="ana-row" data-cat="{cat}" data-id="{html.escape(gid)}">
            <button class="ana-row__main" type="button" aria-expanded="false">
              <span class="ana-row__cat cat--{cat}"></span>
              <span class="ana-row__title">{title}</span>
              <span class="ana-row__strip">{strip}</span>
              <span class="ana-row__streak">now <b>{stats['current_streak']}</b> · best <b>{stats['longest_streak']}</b></span>
              <span class="ana-row__pct">{pct}<span class="ana-row__pct-suf">%</span></span>
              <span class="ana-row__chev" aria-hidden="true">›</span>
            </button>
            <div class="ana-row__expand" hidden>
              <div class="dow">
                <span class="dow__title">by weekday</span>
                <div class="dow__row">{"".join(dow_bars)}</div>
              </div>
            </div>
          </li>''')
    return f'<ul class="ana-table">{"".join(rows)}</ul>'


def render_almanac(active_goals: list[dict], all_states: dict,
                   all_dates: list[str], today_str: str,
                   past_end_today: bool) -> str:
    """Range-independent: every day in state/, every active goal."""
    rows = []
    for g in active_goals:
        gid = g["id"]
        cat = category_of(g)
        title = html.escape(g.get("title", gid))
        cells = []
        for d in all_dates:
            state = all_states.get(d, {})
            is_today = (d == today_str)
            status = _status_for_day(gid, state, is_today, past_end_today)
            today_cls = " acell--today" if is_today else ""
            cells.append(
                f'<span class="acell acell--{status} acell--cat-{cat}{today_cls}" '
                f'title="{html.escape(d)}: {status}"></span>'
            )
        rows.append(
            f'<div class="alm-row" data-cat="{cat}">'
            f'<span class="alm-row__label">{title}</span>'
            f'<div class="alm-row__cells" style="--cols: {len(all_dates)}">'
            f'{"".join(cells)}'
            f'</div>'
            f'</div>'
        )
    span = f"{_fmt_short(all_dates[0])} → {_fmt_short(all_dates[-1])} · {len(all_dates)} days"
    return f'''
        <section class="ana-almanac">
          <header class="ana-almanac__head">
            <h3 class="ana-almanac__title">Almanac</h3>
            <span class="ana-almanac__sub">{span}</span>
          </header>
          <div class="alm">{"".join(rows)}</div>
        </section>'''


def render_range_bundle(range_key: str, active_goals: list[dict],
                        all_states: dict, all_dates: list[str],
                        today_str: str, past_end_today: bool,
                        nutrition: dict) -> str:
    """All range-dependent sections for one range. CSS shows one bundle at a time."""
    cur, prior = period_dates(all_dates, range_key, today_str)
    summary = period_summary(active_goals, all_states, cur, today_str, past_end_today)
    heatmap = category_heatmap(active_goals, all_states, cur, today_str, past_end_today)
    picks = wins_drifts(active_goals, all_states, cur, prior, today_str, past_end_today)
    food = food_period(all_states, cur, nutrition)
    table = render_per_goal_table(active_goals, all_states, cur, today_str, past_end_today)
    return f'''
      <div class="ana-bundle range-{range_key}" data-range="{range_key}">
        <section class="ana-hero">
          {render_hero(summary, cur)}
          {render_cat_heatmap(heatmap, cur)}
        </section>
        {render_callouts(picks)}
        {render_food_block(food)}
        {table}
      </div>'''


def render_range_toggle() -> str:
    btns = []
    for key, label, _ in RANGES:
        btns.append(
            f'<button class="range-btn" data-range="{key}" type="button">{label}</button>'
        )
    return f'<div class="range-toggle" role="tablist" aria-label="Time range">{"".join(btns)}</div>'


def render_analytics_html(*, settings: dict, goals_data: dict,
                          all_states: dict, all_dates: list[str],
                          today: datetime, now: datetime) -> str:
    today_str = today.strftime("%Y-%m-%d")

    all_goals = goals_data.get("goals", [])
    active = [g for g in all_goals if g.get("active", True)]

    day = settings.get("day", {})
    end_hour = day.get("end_hour", 23)
    past_end_today = is_past_end(now, end_hour)
    nutrition = settings.get("nutrition", {}) or {}

    bundles_html = "".join(
        render_range_bundle(key, active, all_states, all_dates,
                            today_str, past_end_today, nutrition)
        for key, _, _ in RANGES
    )

    almanac_html = render_almanac(active, all_states, all_dates, today_str, past_end_today)

    pills = filter_pills(active)
    range_toggle = render_range_toggle()
    title = "Analytics"
    span_label = f"{_fmt_short(all_dates[0])} → {_fmt_short(all_dates[-1])} · {len(all_dates)} days"

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
    document.querySelectorAll('[data-cat]').forEach(function(el){
      if (el.classList.contains('hcell') || el.classList.contains('alm-row__cells')) return;
      el.hidden = !(f === 'all' || el.dataset.cat === f);
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

  function setRange(r){
    body.dataset.range = r;
    try { localStorage.setItem('life.range', r); } catch(e){}
    document.querySelectorAll('.range-btn').forEach(function(b){
      b.classList.toggle('is-active', b.dataset.range === r);
    });
  }
  var savedRange = '7d';
  try { savedRange = localStorage.getItem('life.range') || '7d'; } catch(e){}
  setRange(savedRange);
  document.querySelectorAll('.range-btn').forEach(function(b){
    b.addEventListener('click', function(){ setRange(b.dataset.range); });
  });

  // Per-goal row expand
  document.querySelectorAll('.ana-row__main').forEach(function(btn){
    btn.addEventListener('click', function(){
      var row = btn.closest('.ana-row');
      var ex = row.querySelector('.ana-row__expand');
      var isOpen = !ex.hasAttribute('hidden');
      if (isOpen){ ex.setAttribute('hidden', ''); btn.setAttribute('aria-expanded', 'false'); row.classList.remove('is-open'); }
      else      { ex.removeAttribute('hidden');   btn.setAttribute('aria-expanded', 'true');  row.classList.add('is-open'); }
    });
  });
})();
"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Analytics — Life · {span_label}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,wght@0,400;0,500;1,400;1,500&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css" />
</head>
<body data-theme="light" data-filter="all" data-range="{DEFAULT_RANGE}" data-page="analytics">
  <div class="paper paper--ana">
    <header class="head">
      <div class="headline">
        <h1 class="date">{title}</h1>
        <span class="time">{html.escape(span_label)}</span>
        {range_toggle}
        <button class="theme-btn" data-action="theme" type="button" aria-label="Toggle theme">light</button>
      </div>
      {pills}
    </header>

    <main class="ana-main">
      {bundles_html}
      {almanac_html}
    </main>

    <footer class="foot">
      <span>{today_str}</span>
      <span class="foot__mid">paper-planner · weekly review · v0.6</span>
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
    todos = load_todos()
    dash_html = render_html(
        settings=settings,
        goals_data=goals,
        recent_states=recent_states,
        today=today,
        now=now,
        todos=todos,
    )
    OUT_INDEX.write_text(dash_html)
    print(f"wrote {OUT_INDEX} ({len(dash_html)} bytes) for {today.strftime('%Y-%m-%d')}")

    # Analytics (full history + range bundles)
    all_states = load_all_states()
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
