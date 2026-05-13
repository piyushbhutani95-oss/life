# PRD — Life Webpage

| | |
|---|---|
| **Author** | Piyush |
| **Status** | v0.5 — food card, tap-to-mark, analytics |
| **Last updated** | 2026-05-13 |
| **Repo** | `/Users/piyushbhutani/Documents/2026 /Code/Life` (GitHub: `piyushbhutani95-oss/life`) |

---

## 1. What this is

A personal webpage that helps me actually do what I say I'll do each day.

I tell it my daily goals. It shows me, at any moment, what's done and what's left, and how I've been doing across the past week. As the day wears on and I haven't done things, it nudges me — gently first, then louder. Worst case, it flips my phone into a no-distractions mode so I stop scrolling and get back to work.

**This is not an app.** No login, no UI to click through, no buttons to design. It's a webpage I look at, and I talk to Claude (in the terminal *or on my phone via Claude Code on the web*) to update it. Claude is my keyboard. *(Update: there's now also a one-tap mark mechanism on the dashboard itself for the common "I did this" case — see §5.)*

Scope for now: **daily goals + a single food/calorie card**. Long-term goals, workouts as a separate module, and anything that auto-detects whether I did something — all later. I never want auto-detection of completion; the system can *ask* me whether something is done, but it shouldn't guess.

---

## 2. Why

I want a single tool that:
- holds my intent for the day
- shows me, honestly, where I am — both today and across recent days
- pushes me to do the thing
- removes distractions when I'm slacking

Existing tools each do one piece. None chain them together. A custom thing is justified because I want the chain, not the pieces.

---

## 3. The loop

1. I tell Claude my daily goals once. They get saved to `goals.yaml`.
2. Through the day, I tell Claude *"done"*, *"skipped"*, *"what's left?"* — from the terminal on my Mac, from `claude.ai/code` on my phone browser, or by tapping a card on the dashboard itself. Claude (or the dashboard's JS) writes to today's state file.
3. ✅ Every 15 minutes a tiny background watcher (cron-job.org → Vercel `/api/tick`) looks at the current time and what I haven't done yet.
4. ✅ If I'm fine, it does nothing. If goals are overdue, it sends an ntfy push with Yes/No buttons.
5. *(planned)* Meaningfully behind → louder notification + the unfinished goal gets dropped onto Google Calendar in the next free slot. Seriously behind → loud notification + my phone flips into a "no distractions" mode.
6. ✅ Tapping ✓ on a notification — or tapping the card on the dashboard — hits the Vercel webhook that marks the goal done in today's state file.

---

## 4. The webpage — built

Open `index.html` in a browser, or visit the live URL `https://piyushbhutani95-oss.github.io/life/` (auto-deployed by GitHub Pages on every commit). **Paper-planner** aesthetic. Two themes (light / dark), switchable from a button in the header; choice persists in `localStorage`.

**Desktop is locked to 100vh — no scroll.** Card and gap sizes adapt to viewport height via `clamp(min, vh, max)` so the layout fills tall monitors and stays compact on short laptops. On phones, layout reflows to a 2-column scrollable grid.

**Header**
- Date as one quiet italic line: `13 May 2026 | Tuesday` (Newsreader italic).
- Local time on the right (mono).
- A small `light` ↔ `dark` toggle button at the far right.
- A 6px progress pill (filled in the theme accent) + an italic percentage + a mono `00 / 16` count.
- **Filter pills** — `all 16 · health 5 · mind 4 · skills 4 · social 2`. Each pill has a colored dot in the category accent. Choice persists in `localStorage`.

**Sections — by time-of-day**
- `morning` (`06 — 12`), `afternoon` (`12 — 18`), `evening` (`18 — 23`), `anytime` (no range).
- Sections with no goals don't render.

**Goal cards**
- Auto-fill grid (`minmax(180px, 1fr)`). Reflows by viewport width.
- Each card: category color stripe across the top, italic title, 7-day streak strip across the bottom, flame badge (`✦ 09`) only when streak ≥ 3.
- Today's status quietly affects the whole card — done = 50% opacity + strikethrough; partial = 78%; skipped = muted; open = default.
- **Tap-to-mark**: clicking an open card POSTs `done` to the webhook via in-page JS and optimistically flips the card to done immediately. The Food card is exempt (see §4c).

**Footer:** one thin mono line — `2026-05-13 · last nudge · soft @ 13:00 · v1` with a small `analytics` link to the analytics page (§4d).

---

## 4a. History — what's stored vs what's shown

**Storage (the source of truth):** every day gets its own file under `state/YYYY-MM-DD.yaml` and is kept forever — git is the database. Long-term analysis reads straight from this folder.

**Display (dashboard):** each card's strip shows only the last 7 days. The analytics page (§4d) reads all history.

---

## 4b. Categories + accents

Locked across both themes:
- mint (`#9ec1a8`) — **health**
- lilac (`#b6a8d1`) — **mind**
- butter (`#d9c07a`) — **skills**
- rose (`#d9a0a0`) — **social**

All other tones derived via `color-mix(in oklab, …)` so the whole UI re-tones from one var swap.

---

## 4c. Food card

The 16th goal (`food` in `goals.yaml`) gets a richer card variant. It sits in the **Anytime** section between Step out and Respond to people, with the health (mint) accent.

**What's different from a regular goal card**:
- A two-line readout sits between the title and the 7-day strip: `0/2200 KCAL` over `p 0 · c 0 · f 0` (both small mono so the card stays the standard height).
- Status is derived from the `food` list on the state YAML (not from completions). Card stays "open" all day; auto-strikes after `end_hour` (23:00 IST) if any entries were logged.
- Tap-to-mark is disabled on this card — food isn't a yes/no question.

**Logging meals**: ntfy fires meal-time pushes at 09:00 / 13:00 / 20:00. The user usually ignores the Yes/No buttons and instead opens `claude.ai/code` to type free text (*"100g dal and rice"*). Claude estimates kcal + protein/carbs/fat and appends an entry to `state/<today>.yaml` under `food`:

```yaml
food:
  - at: "13:15"
    item: "100g dal + 1 cup rice"
    kcal: 320
    protein_g: 11
    carbs_g: 60
    fat_g: 2
    meal: lunch
```

Targets live in `settings.yaml` → `nutrition` block (default 2200 kcal / 130p / 250c / 70f).

---

## 4d. Analytics page

A separate `analytics.html` at `/analytics.html` on GitHub Pages. Reads **all** `state/*.yaml` files (full history, not just 7 days) and shows per-goal aggregate stats:

- Total `X / Y` days done and percentage.
- Current streak + longest streak.
- A history strip covering every day in `state/` (auto-sizes — gets compressed as you accumulate weeks).
- **Food** has its own card showing days-logged, average daily kcal + macros, best/worst days.

Same paper-planner aesthetic as the main dashboard. Footer carries a `← dashboard` link.

Generated by the same `render.py` script as `index.html` — both rebuild on every commit via the render workflow.

---

## 5. How I talk to it

Three surfaces, same data:

**Mac terminal** — open Claude Code in the project folder, say things in plain English.
**Phone (`claude.ai/code`)** — connect to the GitHub repo, type plain English. Always say "commit directly to main" to avoid stranded branches.
**Dashboard tap-to-mark** — open the dashboard on any device, click any open card to mark it done. Webhook handles it.

Examples (Mac or phone):
- *"Add a goal: meditate 15 minutes, prefer mornings"*
- *"Mark workout done"*
- *"Skip reading today"*
- *"Logged 2 eggs and toast — commit to main"*  (food)
- *"What's left for today?"*
- *"Pause guitar for now"*
- *"Recategorize step-out as health"*

Claude edits the underlying YAML; `render.py` regenerates the dashboard + analytics; render workflow deploys to Pages within ~30s.

---

## 6. Push notifications — built

Three pieces work together:

**A. The mailbox (ntfy.sh)** ✅ — Private topic in gitignored `settings.yaml`. Subscribed via the ntfy Android app.

**B. The watcher (`/api/tick` + external cron)** ✅ — cron-job.org pings the Vercel endpoint every 15 minutes. GitHub Actions runs the same ping on a backup schedule. The endpoint reads `goals.yaml` + today's state + the clock, sends one ntfy push per eligible goal, and writes dedup state back to the repo.

**C. Action buttons** ✅ — Each push carries Yes / No buttons that POST to `/api/mark` with the shared-secret header. Tap Yes → goal marked done; render rebuilds; dashboard refreshes. For the Food card, the user ignores the buttons and instead opens Claude to log free text.

End-to-end verified 2026-05-10 via curl + real meal logs.

---

## 7. Escalation ladder — partially built

Each goal has an explicit `nudge_at` (single `"HH:MM"` or list for multi check-ins). Priority no longer drives nudge timing; it's per-goal.

| Level | When | What happens | Status |
|---|---|---|---|
| **Calm** | All goals done, or plenty of day left | Nothing | ✅ built |
| **Soft** | A few open, more than a third of the day left | Gentle ntfy push with Yes/No | ✅ built |
| **Firm** | Important goal undone, more than half the day gone | Louder push + Calendar block | ⌛ Calendar part planned |
| **Hard** | Multiple important goals undone, only a quarter left | Loud push + phone Focus mode | ⌛ Tasker part planned |
| **Lockdown** | Day almost over, criticals undone | Phone screen-locks | 🔮 v3 |

Thresholds in `settings.yaml` → `escalation`.

---

## 8. Calendar — planned

When the watcher decides a goal needs a calendar block, it:
- looks at my main Google Calendar to find the next genuinely free slot
- creates an event there with prefix `🎯 Life:` and a distinct color
- tags the event description with a hidden marker (`auto-scheduled-by:life-os`) so we can later find/clean up only events we created

If I mark the goal done before the event time, the event gets cancelled automatically.

---

## 9. Phone "no-distractions mode" — planned

One-time Android setup with Tasker (~$3.50) and the free ntfy app. When a "Hard" level message arrives, Tasker turns on Do Not Disturb and launches a Focus mode. Step-by-step instructions will live in `docs/phone-setup.md`.

---

## 10. File layout

```
/Users/piyushbhutani/Documents/2026 /Code/Life/
├── PRD Webpage.md                         ← this document
├── CLAUDE.md                              ⌛ planned (working notes for Claude)
├── README.md                              ✓ built
├── .gitignore                             ✓ built
├── .vercelignore                          ✓ built (scopes Vercel deploy to api/)
├── settings.example.yaml                  ✓ built (committed) — incl. nutrition block
├── settings.yaml                          ✓ built (gitignored — holds secrets)
├── goals.yaml                             ✓ built — 16 goals (15 normal + Food)
├── state/
│   ├── 2026-05-13.yaml                    ✓ today
│   └── …                                  ⌛ accumulates forever
├── render.py                              ✓ built — YAML → index.html + analytics.html
├── tick.py                                ✓ built (local fallback; cron uses api/)
├── style.css                              ✓ built — paper-planner tokens
├── index.html                             ✓ generated (dashboard)
├── analytics.html                         ✓ generated (analytics page)
├── api/
│   └── index.py                           ✓ deployed — /api/mark + /api/tick + CORS
├── requirements.txt                       ✓ Vercel function deps (PyYAML)
├── vercel.json                            ✓ rewrites /api/mark → /api/index
├── .github/workflows/
│   ├── render.yml                         ✓ re-render both HTML files + deploy
│   └── tick.yml                           ✓ fallback ping for the cron
├── schedule.py                            ⌛ planned — Google Calendar writes
└── docs/
    └── phone-setup.md                     ⌛ planned — Tasker setup
```

The git repo *is* the database. Every change is versioned. Nothing in `state/` is ever deleted.

---

## 11. Current goals (16)

Loaded in `goals.yaml`. Each goal has a `category`, `window`, and explicit `nudge_at`.

| Goal | Category | Window | Nudge at |
|---|---|---|---|
| Wake up early | health | morning | 06:00 |
| Meditate | mind | morning | 06:00 |
| Journal | mind | morning | 06:15 |
| Bath | health | morning | 06:45 |
| Skin care | health | morning | 06:45 |
| Multivitamins | health | morning | 08:00 |
| Workout | health | any | 13:00 |
| Step out | social | any | 18:00 |
| Food | health | any | 09:00 / 13:00 / 20:00 (multi) |
| Write | mind | evening | 17:00 |
| Code | skills | evening | 18:30 |
| Course | skills | evening | 19:00 |
| Practice guitar | skills | evening | 20:00 |
| Language | skills | evening | 20:30 |
| Read | mind | afternoon | 21:30 |
| Respond to people | social | any | 10:00 / 15:00 / 21:00 (multi) |

---

## 12. Setup — what I had to do once

1. ✅ Push the local repo to GitHub.
2. ✅ Generate a long random ntfy topic, store in `settings.yaml`.
3. ✅ Install **ntfy** Android app, subscribe to topic.
4. ⌛ Connect Google Calendar — deferred until `schedule.py` is built.
5. ✅ Deploy `api/index.py` to Vercel. Env vars: GITHUB_TOKEN, SHARED_SECRET, REPO, USER_TZ, ROLLOVER_HOUR, NTFY_TOPIC, WEBHOOK_URL.
6. ✅ Set up cron-job.org to ping `/api/tick` every 15 min.
7. ⌛ Install **Tasker** on Android — deferred until "Hard" escalation needs it.

---

## 13. Day-to-day usage

Three ways to update state, in order of friction:

| Path | Speed | Use case |
|---|---|---|
| **Tap a card on the dashboard** | <1s | "I did it" — single goal, default status = done |
| **Tap Yes/No on a phone notification** | <2s | When a nudge fires and you want to respond on the spot |
| **`claude.ai/code` on phone or Mac terminal** | ~30s | Anything nuanced — partial credit, custom time, food logging, adding/pausing goals |

The dashboard rebuilds within ~30s of any state change. Analytics page rebuilds at the same time.

---

## 14. Out of scope for v1

- Long-term goals (weekly/monthly cadence, progress trends across months) — **except** the analytics page covers a basic version of this
- Workout-specific module (sets/reps, plans)
- **Auto-detecting completion** — explicitly never doing this
- Multi-user / sharing
- Hard phone screen-lock — designed for, not built
- Native phone app
- Mobile-friendly dashboard *redesign* (current reflow is good enough)

---

## 15. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Phone gets spammed | Per-day dedup keyed `(goal_id, nudge_time)`. Quiet hours in settings. |
| Mailbox name guessed | Long random topic (gitignored). |
| Webhook abuse from public URL | `X-Secret` header required. Acceptable to leak via dashboard JS for personal use; rotate via Vercel + GitHub Actions secrets if needed. |
| Vercel deployment protection blocks ntfy callbacks | Disabled at project level — webhook does its own auth. |
| `state/` folder grows unbounded | Fine — text YAML stays tiny. |
| GitHub Actions cron unreliable | Migrated primary cron to cron-job.org. GH Actions runs as backup. |

---

## 16. Open questions — resolved

1. ~~Per-goal nudge eligibility~~ → explicit `nudge_at` per goal.
2. ~~Webhook host~~ → Vercel.
3. ~~tick.py state-write strategy~~ → Vercel function does it via GitHub Contents API directly.
4. ~~Multi-goal nudge format~~ → one push per goal (separately actionable Yes/No).
5. ~~Food card visual prominence~~ → compact mono, fits in standard card height.

New for next milestone:
6. **Calendar integration design** — exact OAuth flow, where to host secrets.
7. **Tasker phone-side setup** — vendor variations on Android.

---

## 17. Verification — how I know it works

1. ✅ **Webhook smoke test** — curl with secret returns 200; commit appears in repo.
2. ✅ **Full pipeline smoke test** — ntfy push fires on schedule; Yes button marks done; dashboard refreshes.
3. ✅ **Cron reliability** — cron-job.org dashboard shows 200 OK every 15 minutes.
4. ✅ **Tap-to-mark** — dashboard card click flips immediately and persists.
5. ⌛ **One real week** — using as daily driver from 2026-05-10. Day 3 of 7 today (2026-05-13). Review on 2026-05-17.

---

## 18. Where it goes after v1

- **v2:** calendar auto-block, Tasker no-distractions. Analytics improvements (monthly heatmap, weekly summaries).
- **v3:** Lockdown level — phone screen-lock when drastically off-track.
- **v4:** Claude proposes the day's plan in the morning based on calendar + goals.

---

## 19. Session log

- **2026-05-06** — concept locked, v0 skeleton (YAML schema, render.py, sample dashboard). 18 goals. Multi-day tracker. CSS extracted.
- **2026-05-06 (later)** — Dashboard window narrowed to 7 days; full history kept in `state/`. PRD updated with phone-update path via `claude.ai/code`, interactive ntfy buttons + Vercel webhook, "no auto-detection" stance.
- **2026-05-07** — Day window made fractional (`start_hour: 5.5`). All 18 goals got explicit `nudge_at` times after a one-by-one pass. `quiet_hours` migrated to a list of windows; added 07:00–08:00 meeting block.
- **2026-05-10** — Full design refresh per `design_handoff_life_tracker/`. Paper-planner aesthetic with Newsreader + JetBrains Mono. Goals grouped by time-of-day. Cards reflow via auto-fill grid; 100vh lock dropped temporarily. Added `category` field. Filter pills. Removed b12, creatine, talk-to-people — 15 goals.
- **2026-05-10 (later)** — Repo pushed to GitHub. `render.yml` workflow built; live on Pages. `tick.py` phase-1 built. ntfy topic + Android subscription verified. Vercel webhook deployed end-to-end at `life-sepia-psi.vercel.app/api/mark` after Python detection / cron-pricing / consolidation rabbit holes. cron-job.org wired up. Cron now firing reliably.
- **2026-05-11** — Added `food` as the 16th goal (3 meal-time nudges). Food card on dashboard shows running kcal + macros against targets from new `settings.yaml` → `nutrition` block. Food status derived from `food` list, not Yes/No completions — card stays "open" through the day, auto-strikes after `end_hour`. Compact mono styling so the food card fits the standard card height.
- **2026-05-12** — Desktop locked to 100vh, no scroll. Card + gap sizes use `clamp(min, vh, max)` to fill tall monitors without breaking on short laptops. Mobile reflow confirmed. **Tap-to-mark** wired up: dashboard JS POSTs to `/api/mark` with X-Secret on card click; CORS + OPTIONS handler added to `api/index.py`; webhook URL + secret injected into HTML head from env vars (CI) or settings.yaml (local).
- **2026-05-13** — PRD updated to v0.5 reflecting food + tap-to-mark + analytics. **Analytics page** (`analytics.html`) added: per-goal stats (X/Y days, current/longest streak), food averages, full-history strip. Generated by `render.py` alongside `index.html`; both rebuild on every push via the render workflow.
- **Next up:** one real week of use ending 2026-05-17, then sit down and review per §17.
