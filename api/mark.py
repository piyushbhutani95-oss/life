"""
api/mark.py — Vercel serverless function that records a goal completion
to today's state YAML in the life repo.

Triggered by tapping a Yes/No action button on a phone notification.

Auth: an `X-Secret` header (or `?secret=` query param) must match the
SHARED_SECRET env var. Anything else returns 403.

Updates state/YYYY-MM-DD.yaml via the GitHub Contents API:
  - GET the current file (or 404 → bootstrap an empty one)
  - append a completion entry
  - PUT it back (which creates a commit on main)

Env vars (configured in Vercel project settings):
  GITHUB_TOKEN    fine-grained PAT, scope: contents read+write on the repo
  SHARED_SECRET   any long random string; ntfy buttons send this back
  REPO            "piyushbhutani95-oss/life"
  USER_TZ         "Asia/Kolkata"
  ROLLOVER_HOUR   "3"
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import yaml

GITHUB_API = "https://api.github.com"

REPO = os.environ.get("REPO", "piyushbhutani95-oss/life")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
SHARED_SECRET = os.environ.get("SHARED_SECRET", "")
TZ_NAME = os.environ.get("USER_TZ", "Asia/Kolkata")
ROLLOVER = int(os.environ.get("ROLLOVER_HOUR", "3"))

VALID_STATUSES = {"done", "skipped", "partial"}


# ---------- time ----------

def today_local_str() -> str:
    n = datetime.now(ZoneInfo(TZ_NAME))
    if n.hour < ROLLOVER:
        n -= timedelta(days=1)
    return n.strftime("%Y-%m-%d")


def now_hm() -> str:
    return datetime.now(ZoneInfo(TZ_NAME)).strftime("%H:%M")


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
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get_file(path: str) -> tuple[str, str | None]:
    """Returns (decoded content, sha) or ('', None) if 404."""
    try:
        meta = _github("GET", f"/repos/{REPO}/contents/{path}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "", None
        raise
    return base64.b64decode(meta["content"]).decode(), meta["sha"]


def put_file(path: str, content: str, sha: str | None, message: str) -> dict:
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "committer": {"name": "life-mark-webhook", "email": "noreply@vercel.app"},
    }
    if sha:
        payload["sha"] = sha
    return _github("PUT", f"/repos/{REPO}/contents/{path}", payload)


# ---------- state ----------

def update_state(content: str, goal_id: str, status: str,
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
    new_content = update_state(content, goal_id, status, date_str, now_hm())
    return put_file(path, new_content, sha,
                    f"mark {goal_id} {status} via webhook")


# ---------- HTTP handler ----------

class handler(BaseHTTPRequestHandler):
    def _respond(self, code: int, body: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def _params(self) -> dict:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def _secret(self, params: dict) -> str:
        # Prefer header; fall back to query param.
        return self.headers.get("X-Secret", "") or params.get("secret", "")

    def _process(self) -> None:
        params = self._params()
        if not SHARED_SECRET or self._secret(params) != SHARED_SECRET:
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

    def do_GET(self) -> None:
        self._process()

    def do_POST(self) -> None:
        self._process()
