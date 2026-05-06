# PRD — Life Webpage

| | |
|---|---|
| **Author** | Piyush |
| **Status** | v0 built, pre-watcher |
| **Last updated** | 2026-05-06 |
| **Repo** | `/Users/piyushbhutani/Documents/2026 /Code/Life` |

---

## 1. What this is

A personal webpage that helps me actually do what I say I'll do each day.

I tell it my daily goals. It shows me, at any moment, what's done and what's left, and how I've been doing across the past week. As the day wears on and I haven't done things, it nudges me — gently first, then louder. Worst case, it flips my phone into a no-distractions mode so I stop scrolling and get back to work.

**This is not an app.** No login, no UI to click through, no buttons to design. It's a webpage I look at, and I talk to Claude (in the terminal *or on my phone via Claude Code on the web*) to update it. Claude is my keyboard.

Scope for now: **daily goals only.** Long-term goals, workouts as a separate module, and anything that auto-detects whether I did something — all later. I never want auto-detection of completion; the system can *ask* me whether something is done, but it shouldn't guess.

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
2. Through the day, I tell Claude *"done"*, *"skipped"*, *"what's left?"* — from the terminal on my Mac, or from `claude.ai/code` on my phone browser. Claude appends to today's state file. The webpage reflects it on next refresh.
3. *(planned)* Every 15 minutes, on its own, a tiny background watcher (GitHub Actions cron) looks at the current time and what I haven't done yet.
4. *(planned)* If I'm fine, it does nothing. If I'm a bit behind → soft phone notification *with ✓ Done / ✗ Not yet buttons*. Meaningfully behind → louder notification + the unfinished goal gets dropped onto Google Calendar in the next free slot. Seriously behind → loud notification + my phone flips into a "no distractions" mode.
5. *(planned)* Tapping ✓ on a notification hits a webhook that marks the goal done in today's state file — no need to open Claude.

---

## 4. The webpage — built

Open `index.html` in a browser. The whole thing is locked to one viewport (100vh, no scrolling) — everything I need to see, no hunting. Top → bottom:

**Masthead (top)**
- Date in italic serif (`WEDNESDAY` / `may 6`)
- Three metric numerals across: `00/18` goals done · `0%` progress · `46%` of day elapsed. Each labeled in small-caps mono (`done` · `progress` · `day`)
- Local time, right-aligned, mono

**Status line**
- One italic serif sentence: "On track. 5 of 18 done." / "A bit behind. 13 open with 40% of the day left."

**Goal grid**
- 6 columns × 3 rows = all 18 goals in one glance, no scrolling
- Each cell: title in serif, meta line in mono small caps (`45m · morning · high`), a 7-day micro-strip across the bottom, current streak number tucked at the right
- Strip cells: filled cobalt = done, half-fill = partial, outlined-only = skipped, empty = no entry. Today's cell always has a thicker cobalt outline.
- Today's status quietly tints the cell title — cobalt for done, dust-tan for skipped, default for open. No badges, no big checkmarks.

**Footer:** one thin mono line — `2026-05-06   ·   no nudges sent today`

**Design language:** grid-notebook aesthetic. Cream paper (`#F4ECD6`) with a real two-layer slate-blue graph grid (24px minor + 120px major lines). Near-black ink (`#1A1A1A`), warm-tan dust for secondary text (`#8C8369`), cobalt blue accent (`#2F58A6`) for done states and today markers. Typography pairs **Instrument Serif** (italic for the date and big numerals) with **IBM Plex Mono** for all labels and meta. Light theme only — no dark mode override; the page should always read like a paper notebook page regardless of OS preference.

---

## 4a. History — what's stored vs what's shown

**Storage (the source of truth):** every day gets its own file under `state/YYYY-MM-DD.yaml` and is **kept forever** — git is the database, every change is a commit, nothing is ever truncated or rolled up. Long-term analysis ("how often did I meditate in May?") will read straight from this folder.

**Display (the dashboard):** the goal grid shows only the **last 7 days** (`HISTORY_DAYS = 7` in `render.py`). One viewport, current week, no fishing through history.

This split means I can change the dashboard window any time (e.g. show the last 30 days during a review week) without losing data, and any future analytics module gets the full history for free.

---

## 5. How I talk to it

Two surfaces, same Claude:

**On my Mac** — open Claude Code in the project folder and say things in plain English.
**On my phone** — open `claude.ai/code` in the browser, connect to the GitHub repo, and say the same things. Claude commits to the repo; the GitHub Action re-renders `index.html` and publishes it.

Examples either place:

- *"Add a goal: meditate 15 minutes, prefer mornings"*
- *"Mark workout done"*
- *"Skip reading today"*
- *"Mark vitamins, b12, creatine done"*
- *"What's left for today?"*
- *"Pause guitar for now"* (sets `active: false`)
- *"Schedule the rest into my calendar"* (planned)
- *"Tone down the nagging today, I'm sick"* (planned)

Claude edits the underlying YAML files; `render.py` regenerates the page. No forms, no UI to build.

For day-to-day marking, I shouldn't even need to open Claude — see §6 (notifications carry ✓ / ✗ buttons that mark goals directly).

---

## 6. Push notifications — planned

Three pieces work together:

**A. The mailbox (ntfy.sh)** — A free service. I get a private mailbox with a long secret name. Anything dropped in shows up as a notification on my phone. I install one free Android app that listens to my mailbox.

**B. The robot (GitHub Actions cron)** — Every 15 minutes, a tiny job hosted free by GitHub wakes up, reads `goals.yaml` + today's state + the time, and decides if I'm slacking. If I am, it drops a message in my mailbox → my phone buzzes.

**C. Action buttons** — Notifications aren't just text. ntfy supports per-notification action buttons, so each nudge looks like:

> **Workout** (45m · high)
> Did you do this yet?
> [ ✓ Done ] [ ✗ Not yet ]

Tapping **✓ Done** hits a webhook (a small Vercel function) that authenticates the request and commits a `done` completion to today's `state/YYYY-MM-DD.yaml`. Tapping **✗ Not yet** dismisses the notification; the next tick may re-prompt later if the goal is still open and time has moved on.

Net effect: 95% of daily marking happens with one tap, no Claude conversation. Claude is only needed for richer edits (new goals, pausing, weekly review, etc.).

I don't run anything. The robot is hosted for free (GitHub Actions). The mailbox is free (ntfy). The webhook is free (Vercel free tier). The phone app is free.

---

## 7. Escalation ladder — planned

The watcher decides nudge level by **how overdue I am, weighted by priority** — not by auto-detection. The system never assumes I did or didn't do something; it only knows what I've explicitly marked (in Claude or via ✓/✗ buttons).

| Level | When | What happens |
|---|---|---|
| **Calm** | All goals done, or plenty of day left | Nothing |
| **Soft** | A few things left, more than a third of the day remaining | One gentle phone notification *with ✓/✗ buttons* asking "did you do X?" |
| **Firm** | An important goal undone and more than half the day is gone | Louder notification *with ✓/✗* + the goal gets dropped onto my Google Calendar in the next open slot |
| **Hard** | Multiple important goals undone and only a quarter of the day left | Loud notification *with ✓/✗* + my phone flips into a no-distractions mode |
| **Lockdown** *(future, not in v1)* | Day is almost over, criticals undone | Phone screen-locks for a cool-down period |

Thresholds live in `settings.yaml` under `escalation:`.

Per-goal nudge eligibility (which goals get to nudge, when in their window) is a separate setting — open question for first build, see §16.

---

## 8. Calendar — planned

When the watcher decides a goal needs a calendar block, it:
- looks at my main Google Calendar to find the next genuinely free slot
- creates an event there with prefix `🎯 Life:` and a distinct color
- tags the event description with a hidden marker (`auto-scheduled-by:life-os`) so we can later find/clean up only events we created — never touching anything I made

If I mark the goal done before the event time (via Claude or ✓ button), the event gets cancelled automatically.

---

## 9. Phone "no-distractions mode" — planned

One-time Android setup with Tasker (~$3.50) and the free ntfy app:

- Tasker listens to my mailbox.
- When a "Hard" level message arrives, Tasker turns on Do Not Disturb and launches a Focus mode that hides social apps, games, etc.
- When all goals are eventually marked done (or end of day), Tasker turns it back off.

Step-by-step instructions will live in `docs/phone-setup.md`.

---

## 10. File layout

```
/Users/piyushbhutani/Documents/2026 /Code/Life/
├── PRD.md                              ← this document
├── README.md                           ✓ built
├── .gitignore                          ✓ built
├── settings.example.yaml               ✓ built (committed)
├── settings.yaml                       ✓ built (gitignored)
├── goals.yaml                          ✓ built — 18 goals
├── state/
│   ├── 2026-05-06.yaml                 ✓ built — today
│   └── …                               ⌛ accumulates forever, one file per day
├── render.py                           ✓ built — YAML → HTML (window = 7d)
├── style.css                           ✓ built — design tokens
├── index.html                          ✓ generated
├── tick.py                             ⌛ planned — 15-min watcher
├── schedule.py                         ⌛ planned — Google Calendar writes
├── api/
│   └── mark.py                         ⌛ planned — Vercel webhook for ✓/✗ buttons
├── .github/workflows/
│   ├── render.yml                      ⌛ planned — re-render on every push
│   └── tick.yml                        ⌛ planned — 15-min watcher cron
└── docs/
    └── phone-setup.md                  ⌛ planned — Tasker setup
```

The git repo *is* the database. Every change is versioned. Nothing in `state/` is ever deleted.

---

## 11. The 18 daily goals (current)

Loaded in `goals.yaml`:

| Goal | Window | Priority | Time |
|---|---|---|---|
| Wake up early | morning | high | — |
| Bath | morning | low | 10m |
| Skin care | morning | low | 5m |
| Multivitamins | morning | low | 1m |
| B12 | morning | low | 1m |
| Creatine | any | low | 1m |
| Workout | any | high | 45m |
| Step out | afternoon | medium | 15m |
| Meditate | morning | medium | 15m |
| Journal | evening | medium | 15m |
| Read | evening | high | 30m |
| Write | morning | high | 1h |
| Code | any | high | 1h 30m |
| Practice guitar | any | medium | 30m |
| Language | any | medium | 20m |
| Course | any | medium | 30m |
| Talk to people | any | medium | — |
| Respond to people | any | medium | — |

Edit by talking to Claude.

---

## 12. Setup — what I have to do once

1. Push the local repo to a private GitHub repo — so Claude on the web and GitHub Actions can read/write it. *~5 min, not yet done*
2. Generate a long random ntfy topic name and put it in `settings.yaml` — ~5 min *(deferred until tick.py is built)*
3. Install the **ntfy** app on Android, subscribe to that topic — ~5 min *(deferred)*
4. Connect Google Calendar — ~10 min *(deferred until schedule.py is built)*
5. Deploy the `api/mark.py` webhook on Vercel and put its URL in `settings.yaml` — ~10 min *(deferred until ✓/✗ buttons are built)*
6. Install **Tasker** on Android, follow `docs/phone-setup.md` — ~20 min *(deferred)*

Total: under an hour. Not all of it is needed today.

---

## 13. Day-to-day usage

- **Mac:** open Claude Code in the project folder, talk to it in plain English. Optionally open `index.html` in a browser tab.
- **Phone:** tap ✓/✗ on the nudge notifications. For richer edits ("add goal", "pause this", "what's left this week?"), open `claude.ai/code`, point it at the GitHub repo, and chat.

To regenerate the page after editing files manually:
```
python3 render.py
```

(GitHub Actions does this automatically on every push once `render.yml` is wired up.)

---

## 14. Out of scope for v1

- Long-term goals (weekly/monthly cadence, progress trends across months)
- Workout-specific module (sets/reps, plans)
- **Auto-detecting completion** (e.g., GitHub commits = "coded", fitness data = "worked out") — explicitly *never* doing this; the system asks instead
- Multi-user / sharing
- Hard phone screen-lock — designed for, not built (the Lockdown level)
- Native phone app
- Mobile-friendly redesign of the dashboard (phone marks via buttons + chats via `claude.ai/code`; the dashboard view itself is desktop-first)

---

## 15. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Watcher accidentally messes up real Calendar events | Only ever touches events with our hidden marker |
| Phone gets spammed during testing | Watcher dedupes — won't repeat itself within 15 min |
| Pushes arrive while asleep | Quiet hours configurable in `settings.yaml` |
| Mailbox name guessed | Use a long random string. Self-host ntfy later if paranoid |
| ✓/✗ webhook abused by anyone who finds the URL | Webhook requires a shared secret in the URL/header, set in `settings.yaml` |
| Tasker setup finicky on this Android version | Documented for stock Android first; degrade to "loud notification only" if Focus mode flip fails |
| `state/` folder grows unbounded | Fine — text YAML stays tiny; even 10 years ≈ a few MB |

---

## 16. Open questions for next build

1. **Per-goal nudge eligibility.** Which goals are allowed to nudge me, and when in their window? Default proposal: every active `high` goal nudges once it's past the midpoint of its window; `medium` only nudges in the back half of the day; `low` never nudges (you can mark them whenever).
2. **Webhook host.** Vercel function feels right (free, near-zero setup, repo-aware). Confirming before building.

---

## 17. Verification — how I know it works

1. **Smoke test** — add 3 goals, manually trigger the robot with the clock pretending it's late afternoon, confirm phone buzzes, ✓ button writes a completion, and a calendar block appears for the unchecked one.
2. **One real week** — use it as the daily driver for a full week, then review:
   - Did the dashboard reflect reality?
   - Did pushes arrive at the right times without annoying me?
   - Did the ✓/✗ buttons feel faster than opening Claude?
   - Did I actually do more of my goals than the week before?
   - What felt missing or wrong?

That review decides what v2 looks like.

---

## 18. Where it goes after v1

- **v2:** medium-term goals (weeks/months), workout module. Long-history analytics (since `state/` already has every day going back to v1) — e.g. "how often did I meditate this month?", "longest streak ever per goal".
- **v3:** the Lockdown level — actual phone screen-lock when drastically off-track
- **v4:** Claude proposes the day's plan in the morning based on calendar gaps + my goals

---

## 19. Session log

- **2026-05-06** — concept locked, PRD written. v0 skeleton built (YAML schema, render.py, sample dashboard). Goals expanded to actual 18-item list. Multi-day tracker added (grid + streaks). CSS extracted to `style.css`. Claude design pass applied (warm paper bg, cobalt accent, Instrument Serif typography).
- **2026-05-06 (later)** — Dashboard window narrowed from 14 days to 7 days (`HISTORY_DAYS = 7`); full history continues to be stored unbounded in `state/`. PRD updated with: (a) phone-update path via `claude.ai/code` against the GitHub repo, (b) interactive ntfy notifications with ✓/✗ action buttons + Vercel webhook, (c) explicit "no auto-detection" stance, (d) storage-vs-display split (§4a).
- **Next up:** push repo to GitHub, then build `tick.py` + `.github/workflows/tick.yml` + `api/mark.py`.
