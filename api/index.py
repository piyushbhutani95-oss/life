"""
api/index.py — single Vercel serverless function that handles ALL routes:

  • /api/mark (or /api/index) → mark a goal as done/skipped/partial
       Triggered by the Yes/No action buttons on phone notifications.
       Updates today's state YAML via the GitHub Contents API.

  • /api/tick → run the watcher
       Triggered every 15 min by Vercel cron (configured in vercel.json).
       Computes which goals are nudge-eligible right now, sends one ntfy
       push per eligible goal (each with Yes/No buttons that hit /api/mark),
       writes notifications_sent records back to today's state YAML.

  • /api/todo → manage the running to-do list (state/todos.yaml)
       action=add (text=...), action=check|uncheck|delete (id=...).
       Called by the dashboard side-panel JS. Persists across days; Claude
       can also edit state/todos.yaml directly for nuanced changes.

Both routes are auth-gated. /api/mark uses X-Secret header or ?secret=
param (matching SHARED_SECRET). /api/tick uses Authorization: Bearer
(matching CRON_SECRET, auto-injected by Vercel cron) or the same X-Secret.

The two-routes-one-function shape is a workaround for Vercel's 2026
Python detector, which picks a single standard-named entrypoint (here
api/index.py) and routes ALL /api/* requests through it. Putting tick
into its own subdir didn't change the routing, so consolidating is the
cleanest path.

Env vars (Vercel project settings):
  GITHUB_TOKEN     fine-grained PAT, contents read+write on the repo
  SHARED_SECRET    /api/mark auth + manual /api/tick triggers
  REPO             "piyushbhutani95-oss/life"
  USER_TZ          "Asia/Kolkata"
  ROLLOVER_HOUR    "3"
  NTFY_SERVER      "https://ntfy.sh" (optional)
  NTFY_TOPIC       the ntfy topic to publish to
  WEBHOOK_URL      this project's /api/mark URL (passed into Yes/No buttons)
  CRON_SECRET      auto-injected by Vercel when cron is configured
"""

from __future__ import annotations

import base64
import concurrent.futures
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import yaml

# render.py lives one level up from api/. Make it importable so /api/render
# can reuse the exact same rendering code that GitHub Actions uses to build
# the static index.html at deploy time. Keeps one source of truth.
_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))
import render  # noqa: E402

GITHUB_API = "https://api.github.com"

REPO = os.environ.get("REPO", "piyushbhutani95-oss/life")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
SHARED_SECRET = os.environ.get("SHARED_SECRET", "")
CRON_SECRET = os.environ.get("CRON_SECRET", "")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
TZ_NAME = os.environ.get("USER_TZ", "Asia/Kolkata")
ROLLOVER = int(os.environ.get("ROLLOVER_HOUR", "3"))

VALID_STATUSES = {"done", "skipped", "partial"}
PRIORITY_FOR_LEVEL = {"calm": 2, "soft": 3, "firm": 4, "hard": 5}


# ---------- time + helpers ----------

def now_local() -> datetime:
    return datetime.now(ZoneInfo(TZ_NAME))


def today_local_str(now: datetime | None = None) -> str:
    n = now or now_local()
    if n.hour < ROLLOVER:
        n = n - timedelta(days=1)
    return n.strftime("%Y-%m-%d")


def now_hm() -> str:
    return now_local().strftime("%H:%M")


def parse_hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def parse_window(s: str) -> tuple[time, time]:
    a, b = s.split("-")
    return parse_hm(a.strip()), parse_hm(b.strip())


def in_window(now_t: time, start_t: time, end_t: time) -> bool:
    if start_t <= end_t:
        return start_t <= now_t < end_t
    return now_t >= start_t or now_t < end_t


def in_any_quiet_hours(now_t: time, quiet_windows: list) -> bool:
    for w in (quiet_windows or []):
        s, e = parse_window(w)
        if in_window(now_t, s, e):
            return True
    return False


def normalize_nudge_at(value) -> list:
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


# ---------- GitHub API ----------

def _github(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{GITHUB_API}{path}"
    body = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if payload:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def get_file(path: str) -> tuple[str | None, str | None]:
    try:
        meta = _github("GET", f"/repos/{REPO}/contents/{path}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise
    return base64.b64decode(meta["content"]).decode(), meta["sha"]


def put_file(path: str, content: str, sha: str | None, message: str,
             author_name: str = "life-webhook") -> dict:
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "committer": {"name": author_name, "email": "noreply@vercel.app"},
    }
    if sha:
        payload["sha"] = sha
    return _github("PUT", f"/repos/{REPO}/contents/{path}", payload)


# ---------- /api/todo — running to-do list ----------

TODOS_PATH = "state/todos.yaml"


def _now_stamp() -> str:
    return now_local().strftime("%Y-%m-%dT%H:%M")


def _load_todos() -> tuple[dict, str | None]:
    content, sha = get_file(TODOS_PATH)
    data = yaml.safe_load(content) if (content and content.strip()) else {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("todos", [])
    return data, sha


def _save_todos(data: dict, sha: str | None, message: str) -> None:
    new_content = yaml.safe_dump(data, sort_keys=False, default_flow_style=False,
                                 allow_unicode=True)
    put_file(TODOS_PATH, new_content, sha, message, author_name="life-webhook")


def add_todo(text: str) -> str:
    data, sha = _load_todos()
    existing = {t.get("id") for t in data["todos"]}
    base = f"t-{int(now_local().timestamp())}"
    new_id, n = base, 0
    while new_id in existing:
        n += 1
        new_id = f"{base}-{n}"
    data["todos"].append({
        "id": new_id,
        "text": text,
        "added_at": _now_stamp(),
        "done_at": None,
    })
    _save_todos(data, sha, f"add todo: {text[:48]}")
    return new_id


def set_todo_done(todo_id: str, done: bool) -> None:
    data, sha = _load_todos()
    target = next((t for t in data["todos"] if t.get("id") == todo_id), None)
    if not target:
        raise ValueError(f"todo id not found: {todo_id}")
    target["done_at"] = _now_stamp() if done else None
    word = "check" if done else "uncheck"
    _save_todos(data, sha, f"{word} todo {todo_id}")


def delete_todo(todo_id: str) -> None:
    data, sha = _load_todos()
    before = len(data["todos"])
    data["todos"] = [t for t in data["todos"] if t.get("id") != todo_id]
    if len(data["todos"]) == before:
        raise ValueError(f"todo id not found: {todo_id}")
    _save_todos(data, sha, f"delete todo {todo_id}")


# ---------- /api/mark — record a completion ----------

def update_state_completion(content: str, goal_id: str, status: str,
                            date_str: str, at: str) -> str:
    state = yaml.safe_load(content) if content and content.strip() else None
    if not state:
        state = {
            "date": date_str,
            "completions": [],
            "notifications_sent": [],
            "scheduled_blocks": [],
        }
    state.setdefault("completions", []).append({
        "goal_id": goal_id,
        "status": status,
        "at": at,
    })
    return yaml.safe_dump(state, sort_keys=False, default_flow_style=False)


def mark_goal(goal_id: str, status: str) -> dict:
    date_str = today_local_str()
    path = f"state/{date_str}.yaml"
    content, sha = get_file(path)
    new_content = update_state_completion(content, goal_id, status, date_str, now_hm())
    return put_file(path, new_content, sha,
                    f"mark {goal_id} {status} via webhook")


# ---------- /api/tick — run the watcher ----------

def status_for(goal_id: str, completions: list) -> str:
    relevant = [c for c in completions if c.get("goal_id") == goal_id]
    if not relevant:
        return "open"
    return relevant[-1].get("status", "open")


def already_nudged(goal_id: str, nudge_time: str, notifications: list) -> bool:
    return any(
        n.get("goal_id") == goal_id and n.get("nudge_time") == nudge_time
        for n in notifications
    )


def eligible_nudges(goals: list, state: dict, now: datetime,
                    quiet_windows: list) -> list:
    completions = state.get("completions", []) or []
    notifications = state.get("notifications_sent", []) or []
    now_t = now.time().replace(second=0, microsecond=0)
    if in_any_quiet_hours(now_t, quiet_windows):
        return []
    out = []
    for g in goals:
        if not g.get("active", True):
            continue
        if status_for(g["id"], completions) in ("done", "partial", "skipped"):
            continue
        for nt_str in normalize_nudge_at(g.get("nudge_at")):
            nt = parse_hm(nt_str)
            if now_t < nt:
                continue
            if already_nudged(g["id"], nt_str, notifications):
                continue
            out.append({"goal": g, "nudge_time": nt_str})
    return out


def escalation_level(count: int, frac: float, settings: dict) -> str:
    if count == 0:
        return "calm"
    esc = settings.get("escalation", {}) or {}
    if frac >= esc.get("hard_after", 0.75) and count >= 3:
        return "hard"
    if frac >= esc.get("firm_after", 0.50) and count >= 2:
        return "firm"
    return "soft"


def send_ntfy(goal: dict, level: str) -> int:
    title = goal.get("title", goal["id"])
    body = "did you do this yet?"
    if goal.get("target_minutes"):
        m = goal["target_minutes"]
        meta = f"{m // 60}h {m % 60}m" if m > 60 else f"{m}m"
        body = f"{meta} — did you do this yet?"

    msg: dict = {
        "topic": NTFY_TOPIC,
        "title": title,
        "message": body,
        "priority": PRIORITY_FOR_LEVEL.get(level, 3),
    }
    if WEBHOOK_URL and SHARED_SECRET:
        actions = []
        for label, status in [("Yes", "done"), ("No", "skipped")]:
            url = f"{WEBHOOK_URL}?goal={urllib.parse.quote(goal['id'])}&status={status}"
            actions.append({
                "action": "http",
                "label": label,
                "url": url,
                "headers": {"X-Secret": SHARED_SECRET},
                "clear": True,
            })
        msg["actions"] = actions

    body_bytes = json.dumps(msg).encode()
    req = urllib.request.Request(NTFY_SERVER, data=body_bytes, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=8) as resp:
        return resp.status


def run_tick() -> dict:
    now = now_local()

    goals_content, _ = get_file("goals.yaml")
    settings_content, _ = get_file("settings.example.yaml")
    if not goals_content or not settings_content:
        return {"error": "failed to fetch goals.yaml or settings.example.yaml"}

    goals = (yaml.safe_load(goals_content) or {}).get("goals", []) or []
    settings = yaml.safe_load(settings_content) or {}
    quiet = settings.get("quiet_hours", []) or []

    today_str = today_local_str(now)
    state_path = f"state/{today_str}.yaml"
    state_content, state_sha = get_file(state_path)
    if state_content:
        state = yaml.safe_load(state_content) or {}
    else:
        state = {
            "date": today_str,
            "completions": [],
            "notifications_sent": [],
            "scheduled_blocks": [],
        }

    eligible = eligible_nudges(goals, state, now, quiet)

    if not eligible:
        reason = "quiet hours" if in_any_quiet_hours(now.time(), quiet) else "nothing to nudge"
        return {"status": "calm", "reason": reason, "at": now.strftime("%H:%M IST")}

    day = settings.get("day", {})
    frac = day_fraction(now, day.get("start_hour", 7), day.get("end_hour", 23))
    level = escalation_level(len(eligible), frac, settings)

    sent_results = []
    for e in eligible:
        try:
            code = send_ntfy(e["goal"], level)
            sent_results.append({"goal": e["goal"]["id"], "nudge_time": e["nudge_time"], "code": code})
        except Exception as ex:
            sent_results.append({"goal": e["goal"]["id"], "error": f"{type(ex).__name__}: {ex}"})

    notifs = state.setdefault("notifications_sent", [])
    for e in eligible:
        notifs.append({
            "goal_id": e["goal"]["id"],
            "nudge_time": e["nudge_time"],
            "level": level,
            "at": now.strftime("%H:%M"),
        })

    new_yaml = yaml.safe_dump(state, sort_keys=False, default_flow_style=False)
    put_file(state_path, new_yaml, state_sha,
             f"tick: {len(eligible)} nudges at {now.strftime('%H:%M IST')}",
             author_name="tick-cron")

    return {
        "status": "sent",
        "level": level,
        "count": len(eligible),
        "at": now.strftime("%H:%M IST"),
        "goals": sent_results,
    }


# ---------- HTTP handler ----------

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "X-Secret, Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
}


# ---------- live dashboard render (used by /api/render) ----------

# 7 days of state matches render.HISTORY_DAYS — the dashboard's history strip.
_RENDER_HISTORY_DAYS = 7


def _fetch_yaml_file(path: str) -> dict:
    """Fetch + parse a YAML file from the repo. Returns {} on 404 or empty."""
    try:
        content, _ = get_file(path)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise
    if not content or not content.strip():
        return {}
    data = yaml.safe_load(content)
    if data is None:
        return {}
    return data if isinstance(data, dict) else {"_raw": data}


def _gather_dashboard_data() -> tuple[dict, dict, dict, list, datetime, datetime]:
    """Parallel-fetch every file the dashboard render needs.

    Returns (settings, goals_data, recent_states, todos, today, now).
    Each state file is fetched concurrently to keep p50 latency under ~500ms
    even with ~10 GitHub Contents API calls.
    """
    tz = ZoneInfo(TZ_NAME)
    now = datetime.now(tz)
    today_dt = now - timedelta(days=1) if now.hour < ROLLOVER else now

    # Build the list of state dates the dashboard's history strip needs.
    state_dates: list[str] = []
    for i in range(_RENDER_HISTORY_DAYS - 1, -1, -1):
        d = (today_dt - timedelta(days=i)).strftime("%Y-%m-%d")
        state_dates.append(d)

    paths: dict[str, str] = {
        "goals":    "goals.yaml",
        "settings": "settings.yaml",
        "todos":    "state/todos.yaml",
    }
    for d in state_dates:
        paths[f"state_{d}"] = f"state/{d}.yaml"

    results: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        fut_to_key = {pool.submit(_fetch_yaml_file, p): k for k, p in paths.items()}
        for fut in concurrent.futures.as_completed(fut_to_key):
            results[fut_to_key[fut]] = fut.result()

    goals_data = results.get("goals") or {}
    settings = results.get("settings") or {}
    todos_data = results.get("todos") or {}
    todos = (todos_data.get("todos") if isinstance(todos_data, dict) else []) or []

    recent_states: dict[str, dict] = {}
    for d in state_dates:
        recent_states[d] = results.get(f"state_{d}") or {
            "date": d,
            "completions": [],
            "notifications_sent": [],
            "scheduled_blocks": [],
        }

    return settings, goals_data, recent_states, todos, today_dt, now


class handler(BaseHTTPRequestHandler):
    def _send_cors(self) -> None:
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)

    def _respond(self, code: int, body) -> None:
        self.send_response(code)
        self.send_header("Content-Type",
                         "application/json" if isinstance(body, (dict, list)) else "text/plain; charset=utf-8")
        self._send_cors()
        self.end_headers()
        if isinstance(body, (dict, list)):
            self.wfile.write(json.dumps(body).encode())
        else:
            self.wfile.write(str(body).encode())

    def do_OPTIONS(self) -> None:
        # CORS preflight from the dashboard's tap-to-mark JS
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def _params(self) -> dict:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def _path(self) -> str:
        return urlparse(self.path).path

    def _shared_secret(self, params: dict) -> str:
        return self.headers.get("X-Secret", "") or params.get("secret", "")

    def _bearer_authorized(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return bool(CRON_SECRET) and auth == f"Bearer {CRON_SECRET}"

    # ---- /api/tick ----

    def _handle_tick(self) -> None:
        if not (self._bearer_authorized()
                or (SHARED_SECRET and self._shared_secret(self._params()) == SHARED_SECRET)):
            self._respond(403, {"error": "forbidden"})
            return
        try:
            result = run_tick()
            self._respond(200, result)
        except urllib.error.HTTPError as e:
            self._respond(502, {"error": f"upstream {e.code}: {e.read().decode()[:200]}"})
        except Exception as e:
            self._respond(500, {"error": f"{type(e).__name__}: {e}"})

    # ---- /api/mark ----

    def _handle_mark(self) -> None:
        params = self._params()
        if not SHARED_SECRET or self._shared_secret(params) != SHARED_SECRET:
            self._respond(403, "forbidden")
            return
        goal_id = params.get("goal", "").strip()
        status = params.get("status", "").strip()
        if not goal_id:
            self._respond(400, "missing 'goal'")
            return
        if status not in VALID_STATUSES:
            self._respond(400, f"status must be one of {sorted(VALID_STATUSES)}")
            return
        try:
            mark_goal(goal_id, status)
            self._respond(200, f"ok: marked {goal_id}={status}\n")
        except urllib.error.HTTPError as e:
            self._respond(502, f"github error {e.code}: {e.read().decode()[:200]}")
        except Exception as e:
            self._respond(500, f"error: {type(e).__name__}: {e}")

    # ---- /api/todo ----

    def _handle_todo(self) -> None:
        params = self._params()
        if not SHARED_SECRET or self._shared_secret(params) != SHARED_SECRET:
            self._respond(403, "forbidden")
            return
        action = params.get("action", "").strip()
        try:
            if action == "add":
                text = params.get("text", "").strip()
                if not text:
                    self._respond(400, "missing 'text'")
                    return
                new_id = add_todo(text)
                self._respond(200, {"ok": True, "id": new_id})
                return
            if action in ("check", "uncheck"):
                tid = params.get("id", "").strip()
                if not tid:
                    self._respond(400, "missing 'id'")
                    return
                set_todo_done(tid, done=(action == "check"))
                self._respond(200, {"ok": True})
                return
            if action == "delete":
                tid = params.get("id", "").strip()
                if not tid:
                    self._respond(400, "missing 'id'")
                    return
                delete_todo(tid)
                self._respond(200, {"ok": True})
                return
            self._respond(400, "action must be add|check|uncheck|delete")
        except ValueError as e:
            self._respond(404, str(e))
        except urllib.error.HTTPError as e:
            self._respond(502, f"github error {e.code}: {e.read().decode()[:200]}")
        except Exception as e:
            self._respond(500, f"error: {type(e).__name__}: {e}")

    # ---- /api/render ----
    #
    # Live-rendered dashboard. Called by the dashboard's JS on page load and
    # after every successful mark/todo mutation. Reads goals.yaml, settings.yaml,
    # todos.yaml, and the last HISTORY_DAYS state files in parallel from the
    # GitHub Contents API, then runs the exact same render code that GH Actions
    # uses for the static deploy. Net effect: refreshes show fresh state with no
    # GH Pages rebuild lag.

    def _handle_render(self) -> None:
        params = self._params()
        if not SHARED_SECRET or self._shared_secret(params) != SHARED_SECRET:
            self._respond(403, "forbidden")
            return
        try:
            (settings, goals_data, recent_states,
             todos, today, now) = _gather_dashboard_data()
            html_str = render.render_html(
                settings=settings,
                goals_data=goals_data,
                recent_states=recent_states,
                today=today,
                now=now,
                todos=todos,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self._send_cors()
            self.end_headers()
            self.wfile.write(html_str.encode())
        except urllib.error.HTTPError as e:
            self._respond(502, f"github error {e.code}: {e.read().decode()[:200]}")
        except Exception as e:
            import traceback
            self._respond(500, f"error: {type(e).__name__}: {e}\n"
                               f"{traceback.format_exc()[:500]}")

    # ---- routing ----

    def _route(self) -> None:
        path = self._path()
        if "tick" in path:
            self._handle_tick()
        elif "todo" in path:
            self._handle_todo()
        elif "render" in path:
            self._handle_render()
        else:
            self._handle_mark()

    def do_GET(self) -> None:
        self._route()

    def do_POST(self) -> None:
        self._route()
