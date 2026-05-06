#!/usr/bin/env python3
"""
render.py — read goals.yaml + recent state files + settings, write index.html.

The page has two zones:
  1. Dashboard — date, one-line status, progress, next 3 things to do
  2. Habits — every goal with a 7-day tracker grid + current streak

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

HISTORY_DAYS = 7  # how many days of history to show in the tracker grid


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

def day_fraction_elapsed(now: datetime, start_hour: int, end_hour: int) -> float:
    start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if now <= start:
        return 0.0
    if now >= end:
        return 1.0
    return (now - start).total_seconds() / (end - start).total_seconds()


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
    # Skip today if it's still open — streak shouldn't reset just because it's morning
    if days and days[0][0] == today_str and days[0][1] == "open":
        days = days[1:]
    streak = 0
    for d, status in days:
        if status in ("done", "partial"):
            streak += 1
        else:
            break
    return streak


def status_line(active_goals: list[dict], completions: list[dict], frac: float) -> str:
    if not active_goals:
        return "No goals defined yet — tell Claude what you want to do today."
    statuses = {g["id"]: status_for(g["id"], completions) for g in active_goals}
    n_total = len(active_goals)
    n_done = sum(1 for s in statuses.values() if s in ("done", "partial"))
    n_skipped = sum(1 for s in statuses.values() if s == "skipped")
    n_open = n_total - n_done - n_skipped

    if n_open == 0:
        if n_done == n_total:
            return "All done. Take the win."
        return f"Day closed out — {n_done} done, {n_skipped} skipped."

    if frac < 0.20:
        return f"Just getting started. {n_open} to go."

    expected = frac * n_total
    actual = n_done + n_skipped
    delta = expected - actual

    pct_left = int((1 - frac) * 100)
    if delta < 1.0:
        return f"On track. {n_done} of {n_total} done."
    if delta < 3.0:
        return f"A bit behind. {n_open} open with {pct_left}% of the day left."
    return f"Behind. {n_open} open and only {pct_left}% of the day remains."


def sort_open(goals: list[dict]) -> list[dict]:
    return sorted(
        goals,
        key=lambda g: (
            PRIORITY_ORDER.get(g.get("priority", "medium"), 1),
            WINDOW_ORDER.get(g.get("window", "any"), 3),
            g.get("title", ""),
        ),
    )


# ---------- rendering ----------

def fmt_minutes(m: int | None) -> str:
    if not m:
        return ""
    if m % 60 == 0 and m >= 60:
        return f"{m // 60}h"
    if m > 60:
        return f"{m // 60}h {m % 60}m"
    return f"{m}m"


def goal_meta(goal: dict) -> str:
    bits = []
    minutes = fmt_minutes(goal.get("target_minutes"))
    if minutes:
        bits.append(minutes)
    window = goal.get("window", "any")
    if window and window != "any":
        bits.append(window)
    priority = goal.get("priority", "medium")
    if priority == "high":
        bits.append("high")
    return " · ".join(bits)


def tracker_cell(goal: dict, history: list[tuple[str, str]], today_str: str, index: int) -> str:
    title = html.escape(goal.get("title", goal.get("id", "")))
    meta = html.escape(goal_meta(goal))

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
    streak_html = (
        f'<span class="streak streak--on">{streak:02d}</span>'
        if streak > 0
        else '<span class="streak streak--off">··</span>'
    )

    idx = f"{index:02d}"

    return f"""
      <article class="goal goal--{today_status}">
        <h3 class="goal__title">{title}</h3>
        {f'<p class="goal__meta">{meta}</p>' if meta else '<p class="goal__meta">&nbsp;</p>'}
        <div class="goal__foot">
          <div class="goal__strip" aria-label="7-day history">{''.join(cells)}</div>
          <span class="goal__streak">{streak_html}</span>
        </div>
      </article>"""


def render_html(*, settings: dict, goals_data: dict, recent_states: dict[str, dict],
                today: datetime, now: datetime) -> str:
    today_str = today.strftime("%Y-%m-%d")
    state = recent_states[today_str]
    completions = state.get("completions", [])
    notifications = state.get("notifications_sent", [])

    all_goals = goals_data.get("goals", [])
    active = [g for g in all_goals if g.get("active", True)]

    statuses = {g["id"]: status_for(g["id"], completions) for g in active}
    open_goals = sort_open([g for g in active if statuses[g["id"]] == "open"])

    n_total = len(active)
    n_done = sum(1 for s in statuses.values() if s in ("done", "partial"))
    pct_done = (n_done / n_total * 100) if n_total else 0

    day = settings.get("day", {})
    frac = day_fraction_elapsed(now, day.get("start_hour", 7), day.get("end_hour", 23))
    line = status_line(active, completions, frac)

    weekday_label = now.strftime("%A").upper()
    monthday_label = now.strftime("%B %-d").upper()
    year_label = now.strftime("%Y")
    folio_label = today.strftime("%Y-%m-%d")
    title_date = now.strftime("%A, %B %-d")
    time_label = now.strftime("%H:%M")
    tz_label = settings.get("user", {}).get("timezone", "LOCAL").upper()
    pct_day = int(frac * 100)
    pct_done_int = int(round(pct_done))

    last_notif = (
        f"LAST NUDGE · {html.escape(notifications[-1].get('level', '?')).upper()} AT "
        f"{html.escape(notifications[-1].get('at', '?'))}"
        if notifications
        else "NO NUDGES SENT TODAY"
    )

    cells_html = []
    for i, g in enumerate(active, start=1):
        history = history_for(g["id"], recent_states)
        cells_html.append(tracker_cell(g, history, today_str, i))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title_date)} — Life · Folio {folio_label}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Mono:ital,wght@0,300;0,400;0,500;0,600;1,400&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css" />
</head>
<body>
  <div class="paper">
    <main class="sheet">

      <header class="masthead">
        <div class="masthead__date">
          <span class="masthead__weekday">{weekday_label}</span>
          <span class="masthead__monthday">{monthday_label}</span>
        </div>

        <div class="metric">
          <span class="metric__label">done</span>
          <span class="metric__value"><em class="metric__num">{n_done:02d}</em><span class="metric__slash">/</span><span class="metric__total">{n_total:02d}</span></span>
        </div>

        <div class="metric">
          <span class="metric__label">progress</span>
          <span class="metric__value"><em class="metric__num">{pct_done_int}</em><span class="metric__unit">%</span></span>
        </div>

        <div class="metric">
          <span class="metric__label">day</span>
          <span class="metric__value"><em class="metric__num">{pct_day}</em><span class="metric__unit">%</span></span>
        </div>

        <div class="masthead__time">{time_label}</div>
      </header>

      <p class="status">{html.escape(line)}</p>

      <section class="grid" aria-label="Daily goals">
        {''.join(cells_html)}
      </section>

      <footer class="foot">
        <span>{folio_label}</span>
        <span class="foot__nudge">{html.escape(last_notif.lower())}</span>
      </footer>

    </main>
  </div>
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
