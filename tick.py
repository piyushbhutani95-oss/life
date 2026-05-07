#!/usr/bin/env python3
"""
tick.py — the escalation watcher.

Runs every 15 min (locally for testing, on GitHub Actions cron in prod).
For each active goal, decides whether to fire a nudge based on:
  - the goal's nudge_at time(s) having passed
  - the goal not already being marked done/partial/skipped
  - no nudge already sent today for this (goal, nudge_time) pair
  - now is not inside a quiet_hours window

Phase 1 (this file): prints the payload it WOULD send.
Phase 2: replace the print with an ntfy push (see TODO in emit_payload).

Usage:
  python3 tick.py              # normal: record nudges to today's state
  python3 tick.py --dry-run    # print only, don't modify state
  python3 tick.py --at 13:00   # fake the current time for testing
  python3 tick.py --schedule   # show today's full nudge schedule and exit
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent
GOALS_FILE = ROOT / "goals.yaml"
SETTINGS_FILE = ROOT / "settings.yaml"
STATE_DIR = ROOT / "state"


# ---------- I/O ----------

def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict) -> None:
    with path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)


def today_local(tz: ZoneInfo, rollover_hour: int, now: datetime | None = None) -> datetime:
    n = now or datetime.now(tz)
    if n.hour < rollover_hour:
        n = n - timedelta(days=1)
    return n


def state_path_for(date_str: str) -> Path:
    return STATE_DIR / f"{date_str}.yaml"


def load_state_for(date_str: str) -> dict:
    path = state_path_for(date_str)
    if path.exists():
        return load_yaml(path)
    return {
        "date": date_str,
        "completions": [],
        "notifications_sent": [],
        "scheduled_blocks": [],
    }


# ---------- time utils ----------

def parse_hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def parse_window(s: str) -> tuple[time, time]:
    a, b = s.split("-")
    return parse_hm(a.strip()), parse_hm(b.strip())


def in_window(now_t: time, start_t: time, end_t: time) -> bool:
    """True if now_t is in [start_t, end_t). Handles overnight wrap."""
    if start_t <= end_t:
        return start_t <= now_t < end_t
    return now_t >= start_t or now_t < end_t


def in_any_quiet_hours(now_t: time, quiet_windows: list[str]) -> bool:
    for w in quiet_windows or []:
        s, e = parse_window(w)
        if in_window(now_t, s, e):
            return True
    return False


def normalize_nudge_at(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def split_hour(hr: float) -> tuple[int, int]:
    h = int(hr)
    m = int(round((hr - h) * 60))
    return h, m


def day_fraction(now: datetime, start_hour: float, end_hour: float) -> float:
    sh, sm = split_hour(start_hour)
    eh, em = split_hour(end_hour)
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    if now <= start:
        return 0.0
    if now >= end:
        return 1.0
    return (now - start).total_seconds() / (end - start).total_seconds()


# ---------- core logic ----------

def goal_status(goal_id: str, completions: list[dict]) -> str:
    relevant = [c for c in completions if c.get("goal_id") == goal_id]
    if not relevant:
        return "open"
    return relevant[-1].get("status", "open")


def already_nudged(goal_id: str, nudge_time: str, notifications: list[dict]) -> bool:
    for n in notifications:
        if n.get("goal_id") == goal_id and n.get("nudge_time") == nudge_time:
            return True
    return False


def eligible_nudges(*, goals: list[dict], state: dict, now: datetime,
                    quiet_windows: list[str]) -> list[dict]:
    completions = state.get("completions", []) or []
    notifications = state.get("notifications_sent", []) or []
    now_t = now.time().replace(second=0, microsecond=0)

    if in_any_quiet_hours(now_t, quiet_windows):
        return []

    out = []
    for g in goals:
        if not g.get("active", True):
            continue
        if goal_status(g["id"], completions) in ("done", "partial", "skipped"):
            continue
        for nt_str in normalize_nudge_at(g.get("nudge_at")):
            nt = parse_hm(nt_str)
            if now_t < nt:
                continue
            if already_nudged(g["id"], nt_str, notifications):
                continue
            out.append({"goal": g, "nudge_time": nt_str})
    return out


def escalation_level(eligible_count: int, day_frac: float, settings: dict) -> str:
    if eligible_count == 0:
        return "calm"
    esc = settings.get("escalation", {}) or {}
    firm_after = esc.get("firm_after", 0.50)
    hard_after = esc.get("hard_after", 0.75)

    if day_frac >= hard_after and eligible_count >= 3:
        return "hard"
    if day_frac >= firm_after and eligible_count >= 2:
        return "firm"
    return "soft"


def build_payload(eligible: list[dict], level: str, now: datetime) -> dict:
    titles = [e["goal"].get("title", e["goal"]["id"]) for e in eligible]
    if len(titles) == 1:
        title = titles[0]
        body = "Did you do this yet?"
    else:
        title = f"{len(titles)} goals open"
        body = " · ".join(titles)
    return {
        "level": level,
        "title": title,
        "body": body,
        "goals": [
            {
                "id": e["goal"]["id"],
                "title": e["goal"].get("title", e["goal"]["id"]),
                "nudge_time": e["nudge_time"],
            }
            for e in eligible
        ],
        "sent_at": now.strftime("%H:%M"),
    }


def record_nudges(state: dict, eligible: list[dict], level: str, now: datetime) -> None:
    notifs = state.setdefault("notifications_sent", [])
    for e in eligible:
        notifs.append({
            "goal_id": e["goal"]["id"],
            "nudge_time": e["nudge_time"],
            "level": level,
            "at": now.strftime("%H:%M"),
        })


def emit_payload(payload: dict) -> None:
    """Phase 1: print. TODO: swap in ntfy push when topic is wired up."""
    bar = "─" * 60
    print(f"\n{bar}")
    print(f" nudge @ {payload['sent_at']} · level={payload['level'].upper()}")
    print(bar)
    print(f"  title: {payload['title']}")
    print(f"  body:  {payload['body']}")
    for g in payload["goals"]:
        print(f"    • [{g['nudge_time']}] {g['title']} ({g['id']})")
    print(bar)


# ---------- preview ----------

def show_schedule(goals: list[dict], quiet_windows: list[str]) -> None:
    """Print a compact daily schedule of all nudge_at times across active goals."""
    rows: list[tuple[str, str, str]] = []
    for g in goals:
        if not g.get("active", True):
            continue
        for nt_str in normalize_nudge_at(g.get("nudge_at")):
            silenced = in_any_quiet_hours(parse_hm(nt_str), quiet_windows)
            note = "  (silenced — quiet hours)" if silenced else ""
            rows.append((nt_str, g.get("title", g["id"]), note))
    rows.sort(key=lambda r: r[0])

    print("\nToday's nudge schedule:\n")
    for t, title, note in rows:
        print(f"  {t}   {title}{note}")
    print(f"\nQuiet hours: {', '.join(quiet_windows) if quiet_windows else 'none'}\n")


# ---------- entry point ----------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Life-OS watcher tick")
    p.add_argument("--dry-run", action="store_true",
                   help="Print but don't modify state")
    p.add_argument("--at", metavar="HH:MM",
                   help="Fake current time for testing")
    p.add_argument("--schedule", action="store_true",
                   help="Show today's full nudge schedule and exit")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not GOALS_FILE.exists():
        print(f"missing {GOALS_FILE}", file=sys.stderr)
        return 1
    if not SETTINGS_FILE.exists():
        print(f"missing {SETTINGS_FILE}", file=sys.stderr)
        return 1

    settings = load_yaml(SETTINGS_FILE)
    goals_data = load_yaml(GOALS_FILE)
    quiet = settings.get("quiet_hours", []) or []
    goals = goals_data.get("goals", []) or []

    if args.schedule:
        show_schedule(goals, quiet)
        return 0

    tz_name = settings.get("user", {}).get("timezone", "UTC")
    tz = ZoneInfo(tz_name)
    rollover = settings.get("day", {}).get("rollover_hour", 3)

    now_real = datetime.now(tz)
    if args.at:
        h = parse_hm(args.at).hour
        m = parse_hm(args.at).minute
        now = now_real.replace(hour=h, minute=m, second=0, microsecond=0)
    else:
        now = now_real

    today = today_local(tz, rollover, now)
    today_str = today.strftime("%Y-%m-%d")
    state = load_state_for(today_str)

    eligible = eligible_nudges(goals=goals, state=state, now=now, quiet_windows=quiet)

    day = settings.get("day", {})
    frac = day_fraction(now, day.get("start_hour", 7), day.get("end_hour", 23))
    level = escalation_level(len(eligible), frac, settings)

    if not eligible:
        if in_any_quiet_hours(now.time(), quiet):
            reason = "quiet hours"
        else:
            reason = "nothing to nudge"
        print(f"[tick @ {now.strftime('%H:%M')}] calm — {reason} "
              f"(day {int(frac*100)}% elapsed)")
        return 0

    payload = build_payload(eligible, level, now)
    emit_payload(payload)

    if args.dry_run:
        print("  (dry run — state file not modified)")
    else:
        record_nudges(state, eligible, level, now)
        save_yaml(state_path_for(today_str), state)
        print(f"  recorded {len(eligible)} nudges to {state_path_for(today_str).name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
