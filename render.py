#!/usr/bin/env python3
"""
render.py — read goals.yaml + today's state + settings, write index.html.

Run any time the underlying data changes. The output is a single self-contained
HTML file you open in a browser.
"""

from __future__ import annotations

import html
import os
import sys
from datetime import datetime, time, timedelta
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


# ---------- loading ----------

def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def today_local(tz: ZoneInfo, rollover_hour: int) -> datetime:
    """Local 'today' respecting rollover_hour (a 2am check still belongs to yesterday
    if rollover_hour is 3)."""
    now = datetime.now(tz)
    if now.hour < rollover_hour:
        now -= timedelta(days=1)
    return now


def load_state_for(date_str: str) -> dict:
    path = STATE_DIR / f"{date_str}.yaml"
    if path.exists():
        return load_yaml(path)
    return {"date": date_str, "completions": [], "notifications_sent": [], "scheduled_blocks": []}


# ---------- computation ----------

def day_fraction_elapsed(now: datetime, start_hour: int, end_hour: int) -> float:
    """0.0 at the start of the waking day, 1.0 at the end. Clamped."""
    start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if now <= start:
        return 0.0
    if now >= end:
        return 1.0
    return (now - start).total_seconds() / (end - start).total_seconds()


def status_for(goal_id: str, completions: list[dict]) -> str:
    """Latest status for a goal today: done | partial | skipped | open."""
    relevant = [c for c in completions if c.get("goal_id") == goal_id]
    if not relevant:
        return "open"
    return relevant[-1].get("status", "open")


def status_line(active_goals: list[dict], completions: list[dict], frac: float) -> str:
    """Produce a one-line human status."""
    if not active_goals:
        return "No goals defined yet — tell Claude what you want to do today."

    statuses = {g["id"]: status_for(g["id"], completions) for g in active_goals}
    n_total = len(active_goals)
    n_done = sum(1 for s in statuses.values() if s == "done")
    n_skipped = sum(1 for s in statuses.values() if s == "skipped")
    n_open = n_total - n_done - n_skipped

    if n_open == 0:
        if n_done == n_total:
            return "All done. Take the win."
        return "Day closed out. " + (f"{n_done} done, {n_skipped} skipped.")

    expected_done = frac * n_total
    actual_done = n_done + n_skipped
    delta = expected_done - actual_done

    if frac < 0.30:
        return f"Just getting started. {n_open} to go."
    if delta < 0.5:
        return f"On track. {n_done} of {n_total} done."
    if delta < 1.5:
        return f"A bit behind. {n_open} still open with {(1-frac)*100:.0f}% of the day left."
    return f"Behind. {n_open} open and only {(1-frac)*100:.0f}% of the day remains."


def sort_open_goals(goals: list[dict]) -> list[dict]:
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
    if m % 60 == 0:
        return f"{m // 60}h"
    if m > 60:
        return f"{m // 60}h {m % 60}m"
    return f"{m}m"


def goal_row(goal: dict, status: str) -> str:
    title = html.escape(goal.get("title", goal.get("id", "")))
    desc = html.escape(goal.get("description", ""))
    priority = goal.get("priority", "medium")
    minutes = fmt_minutes(goal.get("target_minutes"))
    window = goal.get("window", "any")

    meta_bits = []
    if minutes:
        meta_bits.append(minutes)
    if window and window != "any":
        meta_bits.append(window)
    if priority == "high":
        meta_bits.append("high priority")
    meta = " · ".join(meta_bits)

    return f"""
      <li class="goal goal--{status}">
        <div class="goal__main">
          <div class="goal__title">{title}</div>
          {f'<div class="goal__desc">{desc}</div>' if desc else ''}
        </div>
        <div class="goal__meta">{html.escape(meta)}</div>
      </li>"""


def section(label: str, items_html: str) -> str:
    if not items_html.strip():
        return ""
    return f"""
    <section class="section">
      <h2 class="section__label">{label}</h2>
      <ul class="goals">{items_html}
      </ul>
    </section>"""


def render_html(*, settings: dict, goals_data: dict, state: dict, now: datetime) -> str:
    active = [g for g in goals_data.get("goals", []) if g.get("active", True)]
    completions = state.get("completions", [])
    notifications = state.get("notifications_sent", [])

    statuses = {g["id"]: status_for(g["id"], completions) for g in active}
    open_goals = [g for g in active if statuses[g["id"]] == "open"]
    done_goals = [g for g in active if statuses[g["id"]] == "done"]
    partial_goals = [g for g in active if statuses[g["id"]] == "partial"]
    skipped_goals = [g for g in active if statuses[g["id"]] == "skipped"]

    open_goals = sort_open_goals(open_goals)

    n_total = len(active)
    n_done = len(done_goals) + len(partial_goals)
    pct_done = (n_done / n_total * 100) if n_total else 0

    day = settings.get("day", {})
    frac = day_fraction_elapsed(now, day.get("start_hour", 7), day.get("end_hour", 23))
    line = status_line(active, completions, frac)

    date_label = now.strftime("%A, %B %-d")
    time_label = now.strftime("%-I:%M %p").lower()
    pct_day = int(frac * 100)

    last_notif = ""
    if notifications:
        n = notifications[-1]
        last_notif = f"Last nudge — {html.escape(n.get('level', '?'))} at {html.escape(n.get('at', '?'))}"
    else:
        last_notif = "No nudges yet today."

    open_html = "".join(goal_row(g, "open") for g in open_goals)
    done_html = "".join(goal_row(g, "done") for g in done_goals + partial_goals)
    skipped_html = "".join(goal_row(g, "skipped") for g in skipped_goals)

    sections = (
        section("To do", open_html)
        + section("Done", done_html)
        + section("Skipped", skipped_html)
    )

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
    --sage: #6b7f5a;
    --done-bg: #f1ede3;
    --skip: #a89a83;
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
    max-width: 640px;
    margin: 0 auto;
    padding: 88px 32px 64px;
  }}

  header.head {{
    border-bottom: 1px solid var(--line);
    padding-bottom: 28px;
    margin-bottom: 36px;
  }}
  .date {{
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 500;
    font-size: 44px;
    line-height: 1.1;
    letter-spacing: -0.01em;
    margin: 0 0 16px;
  }}
  .status-line {{
    font-size: 17px;
    color: var(--ink);
    margin: 0 0 24px;
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

  .section {{
    margin: 36px 0;
  }}
  .section__label {{
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: var(--muted);
    margin: 0 0 16px;
    font-weight: 600;
  }}
  .goals {{ list-style: none; padding: 0; margin: 0; }}
  .goal {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 24px;
    padding: 16px 0;
    border-bottom: 1px solid var(--line);
  }}
  .goal:last-child {{ border-bottom: none; }}
  .goal__main {{ flex: 1; min-width: 0; }}
  .goal__title {{
    font-family: 'Fraunces', Georgia, serif;
    font-size: 22px;
    font-weight: 500;
    letter-spacing: -0.005em;
  }}
  .goal__desc {{
    color: var(--muted);
    font-size: 14px;
    margin-top: 4px;
  }}
  .goal__meta {{
    font-size: 12px;
    color: var(--muted);
    text-transform: lowercase;
    letter-spacing: 0.04em;
    white-space: nowrap;
    flex-shrink: 0;
  }}
  .goal--done .goal__title,
  .goal--done .goal__desc {{
    color: var(--muted);
    text-decoration: line-through;
    text-decoration-color: var(--line);
  }}
  .goal--skipped .goal__title,
  .goal--skipped .goal__desc {{
    color: var(--skip);
    font-style: italic;
  }}

  footer.foot {{
    border-top: 1px solid var(--line);
    padding-top: 24px;
    margin-top: 64px;
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--muted);
    font-feature-settings: "tnum";
  }}
  footer.foot .right {{ text-align: right; }}

  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #1c1a16;
      --ink: #f0ebe0;
      --muted: #847b6b;
      --line: #2e2a23;
      --sage: #8aa177;
      --done-bg: #25221c;
      --skip: #5e5749;
    }}
  }}
</style>
</head>
<body>
  <main class="page">
    <header class="head">
      <h1 class="date">{html.escape(date_label)}</h1>
      <p class="status-line">{html.escape(line)}</p>
      <div class="progress">
        <span class="progress__count">{n_done} of {n_total}</span>
        <span class="progress__bar"><span class="progress__fill"></span></span>
        <span>{pct_day}% of the day</span>
      </div>
    </header>
    {sections}
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
    date_str = today.strftime("%Y-%m-%d")
    state = load_state_for(date_str)

    now = datetime.now(tz)

    html_out = render_html(settings=settings, goals_data=goals, state=state, now=now)
    OUT_FILE.write_text(html_out)
    print(f"wrote {OUT_FILE} ({len(html_out)} bytes) for {date_str}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
