#!/usr/bin/env python3
"""
render.py — read goals.yaml + recent state files + settings, write index.html.

The page has two zones:
  1. Dashboard — date, one-line status, progress, next 3 things to do
  2. Habits — every goal with a 14-day tracker grid + current streak

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

HISTORY_DAYS = 14  # how many days of history to show in the tracker grid


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


def next_up_html(open_goals: list[dict]) -> str:
    if not open_goals:
        return ""
    top = open_goals[:3]
    rows = []
    for g in top:
        title = html.escape(g.get("title", g.get("id", "")))
        meta = html.escape(goal_meta(g))
        rows.append(f"""
        <li class="up">
          <span class="up__title">{title}</span>
          <span class="up__meta">{meta}</span>
        </li>""")
    return f"""
    <section class="block">
      <h2 class="block__label">Next up</h2>
      <ul class="up-list">{''.join(rows)}
      </ul>
    </section>"""


def tracker_row(goal: dict, history: list[tuple[str, str]], today_str: str) -> str:
    title = html.escape(goal.get("title", goal.get("id", "")))
    meta = html.escape(goal_meta(goal))

    cells = []
    for d, status in history:
        is_today = d == today_str
        title_attr = html.escape(d)
        cell_class = f"cell cell--{status}" + (" cell--today" if is_today else "")
        cells.append(f'<span class="{cell_class}" title="{title_attr}: {status}"></span>')

    streak = current_streak(history, today_str)
    streak_html = (
        f'<span class="streak streak--on">{streak}</span>'
        if streak > 0
        else '<span class="streak streak--off">—</span>'
    )

    return f"""
      <li class="row">
        <div class="row__name">
          <div class="row__title">{title}</div>
          {f'<div class="row__meta">{meta}</div>' if meta else ''}
        </div>
        <div class="row__grid">{''.join(cells)}</div>
        <div class="row__streak">{streak_html}</div>
      </li>"""


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

    date_label = now.strftime("%A, %B %-d")
    time_label = now.strftime("%-I:%M %p").lower()
    pct_day = int(frac * 100)

    last_notif = (
        f"Last nudge — {html.escape(notifications[-1].get('level', '?'))} at "
        f"{html.escape(notifications[-1].get('at', '?'))}"
        if notifications
        else "No nudges yet today."
    )

    next_up = next_up_html(open_goals)

    tracker_rows = []
    for g in active:
        history = history_for(g["id"], recent_states)
        tracker_rows.append(tracker_row(g, history, today_str))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(date_label)} — Life</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@400;500;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #faf7f2;
    --ink: #2c2418;
    --muted: #8b7e6b;
    --line: #e8e1d4;
    --line-strong: #d8cfbd;
    --sage: #6b7f5a;
    --sage-soft: #b3c0a3;
    --skip: #b8aa92;
    --today: #c8a05a;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--ink);
    font-family: 'Inter', -apple-system, system-ui, sans-serif;
    font-size: 16px;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }}
  .page {{
    max-width: 720px;
    margin: 0 auto;
    padding: 72px 32px 48px;
  }}

  /* ───── Dashboard zone ───── */
  header.dash {{
    border-bottom: 1px solid var(--line);
    padding-bottom: 28px;
    margin-bottom: 32px;
  }}
  .date {{
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 500;
    font-size: 44px;
    line-height: 1.1;
    letter-spacing: -0.01em;
    margin: 0 0 14px;
  }}
  .status-line {{
    font-size: 17px;
    color: var(--ink);
    margin: 0 0 22px;
  }}
  .progress {{
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 13px;
    color: var(--muted);
  }}
  .progress__bar {{
    flex: 1;
    height: 2px;
    background: var(--line);
    border-radius: 2px;
    overflow: hidden;
  }}
  .progress__fill {{
    height: 100%;
    background: var(--sage);
    width: {pct_done:.1f}%;
    transition: width 600ms ease;
  }}
  .progress__count {{
    font-feature-settings: "tnum";
    color: var(--ink);
  }}

  /* ───── Block / section ───── */
  .block {{ margin: 32px 0; }}
  .block__label {{
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: var(--muted);
    margin: 0 0 14px;
    font-weight: 600;
  }}

  /* ───── Next up list ───── */
  .up-list {{ list-style: none; padding: 0; margin: 0; }}
  .up {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 10px 0;
    border-bottom: 1px solid var(--line);
    gap: 16px;
  }}
  .up:last-child {{ border-bottom: none; }}
  .up__title {{
    font-family: 'Fraunces', Georgia, serif;
    font-size: 20px;
    font-weight: 500;
  }}
  .up__meta {{
    font-size: 12px;
    color: var(--muted);
    text-transform: lowercase;
    letter-spacing: 0.04em;
    flex-shrink: 0;
  }}

  /* ───── Habit list with tracker grid ───── */
  .tracker-head {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}
  .tracker-head .legend {{
    font-size: 11px;
    color: var(--muted);
    letter-spacing: 0.04em;
  }}
  .rows {{ list-style: none; padding: 0; margin: 0; }}
  .row {{
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 18px;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid var(--line);
  }}
  .row:last-child {{ border-bottom: none; }}
  .row__name {{ min-width: 0; }}
  .row__title {{
    font-family: 'Fraunces', Georgia, serif;
    font-size: 18px;
    font-weight: 500;
    line-height: 1.3;
  }}
  .row__meta {{
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
    text-transform: lowercase;
    letter-spacing: 0.04em;
  }}
  .row__grid {{
    display: flex;
    gap: 3px;
  }}
  .cell {{
    width: 12px;
    height: 12px;
    border-radius: 2px;
    background: transparent;
    border: 1px solid var(--line-strong);
    display: inline-block;
  }}
  .cell--done {{ background: var(--sage); border-color: var(--sage); }}
  .cell--partial {{
    background: linear-gradient(135deg, var(--sage) 0 50%, transparent 50% 100%);
    border-color: var(--sage);
  }}
  .cell--skipped {{ background: var(--skip); border-color: var(--skip); opacity: 0.5; }}
  .cell--open {{ background: transparent; }}
  .cell--today {{
    box-shadow: 0 0 0 1px var(--today);
  }}
  .row__streak {{
    width: 28px;
    text-align: right;
    font-feature-settings: "tnum";
    font-size: 13px;
  }}
  .streak--on {{ color: var(--sage); font-weight: 600; }}
  .streak--off {{ color: var(--muted); }}

  /* ───── Footer ───── */
  footer.foot {{
    border-top: 1px solid var(--line);
    padding-top: 22px;
    margin-top: 56px;
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--muted);
    font-feature-settings: "tnum";
  }}
  footer.foot .right {{ text-align: right; }}

  /* ───── Dark mode ───── */
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #1c1a16;
      --ink: #f0ebe0;
      --muted: #847b6b;
      --line: #2a2620;
      --line-strong: #3a352c;
      --sage: #8aa177;
      --sage-soft: #4a5a3e;
      --skip: #5e5749;
      --today: #c8a05a;
    }}
  }}
</style>
</head>
<body>
  <main class="page">

    <!-- Dashboard zone -->
    <header class="dash">
      <h1 class="date">{html.escape(date_label)}</h1>
      <p class="status-line">{html.escape(line)}</p>
      <div class="progress">
        <span class="progress__count">{n_done} of {n_total}</span>
        <span class="progress__bar"><span class="progress__fill"></span></span>
        <span>{pct_day}% of the day</span>
      </div>
    </header>
    {next_up}

    <!-- Habit tracker -->
    <section class="block">
      <div class="tracker-head">
        <h2 class="block__label">Habits</h2>
        <span class="legend">{HISTORY_DAYS} days · today →</span>
      </div>
      <ul class="rows">{''.join(tracker_rows)}
      </ul>
    </section>

    <footer class="foot">
      <div>{time_label}</div>
      <div class="right">{html.escape(last_notif)}</div>
    </footer>
  </main>
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
