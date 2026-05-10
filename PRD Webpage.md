# PRD — Life Webpage

| | |
|---|---|
| **Author** | Piyush |
| **Status** | v0.3 — webhook live, pre-cron |
| **Last updated** | 2026-05-10 |
| **Repo** | `/Users/piyushbhutani/Documents/2026 /Code/Life` (GitHub: `piyushbhutani95-oss/life`) |

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
3. *(planned — `tick.py` exists, cron wiring pending)* Every 15 minutes a tiny background watcher (GitHub Actions cron) looks at the current time and what I haven't done yet.
4. *(in progress)* If I'm fine, it does nothing. If I'm a bit behind → soft phone notification *with ✓ Done / ✗ Not yet buttons*. Meaningfully behind → louder notification + the unfinished goal gets dropped onto Google Calendar in the next free slot. Seriously behind → loud notification + my phone flips into a "no distractions" mode.
5. ✅ Tapping ✓ on a notification hits the **live Vercel webhook** that marks the goal done in today's state file — no need to open Claude. (Wiring tick.py → ntfy → buttons → webhook is the next milestone.)

---

## 4. The webpage — built

Open `index.html` in a browser, or visit the live URL `https://piyushbhutani95-oss.github.io/life/` (auto-deployed by GitHub Pages on every commit). **Paper-planner** aesthetic — flowing layout, scrolls naturally if content overflows, no fixed-viewport lock. Two themes (light / dark), switchable from a button in the header; choice persists in `localStorage`.

**Header**
- Date as one quiet italic line: `10 May 2026 | Sunday` (Newsreader italic, ~22–32px — small on purpose, not the focal point).
- Local time on the right (mono).
- A small `light` ↔ `dark` toggle button at the far right (mono, capsule shape).
- Below the headline: a 6px progress pill (filled in the theme accent) + an italic percentage + a mono `00 / 15` count.
- Below that: **filter pills** — `all 15 · health 5 · mind 4 · skills 4 · social 2`. Each pill has a colored dot in the category accent. Tap one and only that category's goals stay visible; sections that end up empty collapse. Active pill becomes ink-on-paper. Choice persists in `localStorage`.

**Sections — by time-of-day**
- `morning` (`06 — 12`), `afternoon` (`12 — 18`), `evening` (`18 — 23`), `anytime` (no range).
- Each section header is an italic title + mono hour-range eyebrow + a hairline rule filling the gap + a mono count (e.g. `06`).
- Sections with no goals don't render.

**Goal cards**
- Auto-fill grid (`minmax(170px, 1fr)`, 10px gap). Reflows by viewport width — 6-up on a wide monitor, 2-up on phones.
- Each card has:
  - A 3px **category color stripe** across the top (mint / lilac / butter / rose).
  - Italic title in Newsreader (~20px).
  - A **7-day streak strip** along the bottom — small dashed bars; days marked done fill in the goal's category color, partial = half-fill, skipped = solid rule, no-entry = soft rule. Today's bar gets an outline + extra height so it's always visible.
  - A **flame badge** (`✦ 09`) only when the current streak ≥ 3.
- Today's status quietly affects the whole card — done = 50% opacity + strikethrough on title; partial = 78% opacity; skipped = muted title + 50% opacity; open = default. No checkmarks, no toggle buttons. Marking goes through Claude or the live ntfy ✓/✗ buttons — the dashboard is read-only.

**Footer:** one thin mono line — `2026-05-10 · no nudges sent today · v1`.

**Design language**

- **Typography:** Newsreader (italic 400, the display + card titles) paired with JetBrains Mono (labels, eyebrows, counts, timestamps).
- **Background:** every theme has a real 28×28px ruled grid drawn from CSS variables (`--rule-soft`), so the page always feels like paper.
- **Light theme:** paper `#fafaf6` · cards `#ededdf` · ink `#171712` · accent `#2d2d28` (graphite progress fill, ink-on-paper active filter).
- **Dark theme:** paper `#1a1d22` · cards `#252932` · ink `#ece9e0` · accent `#d9b366` (warm gold).
- **Category accents — locked across both themes:** mint `#9ec1a8` (health) · lilac `#b6a8d1` (mind) · butter `#d9c07a` (skills) · rose `#d9a0a0` (social). All other tones are derived via `color-mix(in oklab, …)` so the whole UI re-tones from one var swap.
- **Motion:** sections and the header fade in once on load; cards lift 1px on hover. Nothing else.

This is a redesign of the earlier "drafting / engineering ledger" look. Implementation reference: `design_handoff_life_tracker/` (V1 — Editorial).

---

## 4a. History — what's stored vs what's shown

**Storage (the source of truth):** every day gets its own file under `state/YYYY-MM-DD.yaml` and is **kept forever** — git is the database, every change is a commit, nothing is ever truncated or rolled up. Long-term analysis ("how often did I meditate in May?") will read straight from this folder.

**Display (the dashboard):** each card's strip shows only the **last 7 days** (`HISTORY_DAYS = 7` in `render.py`). The page itself is no longer locked to 100vh — it flows and scrolls if needed, but with 15 cards across 3–4 sections it usually fits a laptop screen on first paint.

This split means I can change the dashboard window any time (e.g. show the last 30 days during a review week) without losing data, and any future analytics module gets the full history for free.

---

## 5. How I talk to it

Two surfaces, same Claude:

**On my Mac** — open Claude Code in the project folder and say things in plain English.
**On my phone** — open `claude.ai/code` in the browser, connect to the GitHub repo `piyushbhutani95-oss/life`, and say the same things. Claude commits to the repo; the GitHub Action re-renders `index.html` and publishes it to Pages within ~30s.

Examples either place:

- *"Add a goal: meditate 15 minutes, prefer mornings"*
- *"Mark workout done"*
- *"Skip reading today"*
- *"Mark multivitamins and skin care done"*
- *"What's left for today?"*
- *"Pause guitar for now"* (sets `active: false`)
- *"Move code to the afternoon window"*
- *"Recategorize step-out as health"*
- *"Schedule the rest into my calendar"* (planned)
- *"Tone down the nagging today, I'm sick"* (planned)

Claude edits the underlying YAML files; `render.py` regenerates the page. No forms, no UI to build.

For day-to-day marking I shouldn't even need to open Claude — see §6 (notifications carry ✓ / ✗ buttons that mark goals directly via the live webhook).

---

## 6. Push notifications — built (cron pending)

Three pieces work together:

**A. The mailbox (ntfy.sh)** ✅ — A free service. Topic is a long random string in `settings.yaml` (gitignored). Phone subscribed via the free **ntfy** Android app. Test pushes confirmed delivery on 2026-05-10.

**B. The robot (`tick.py` → GitHub Actions cron)** ⌛ — Phase 1 of `tick.py` is built: reads `goals.yaml` + today's state + the clock, computes which goals are nudge-eligible (per `nudge_at`, dedup, quiet hours), buckets them into a payload, and **prints** what it would send. Phase 2 (next) swaps the print for a real ntfy POST. Phase 3 is the GitHub Actions cron file (`.github/workflows/tick.yml`) that runs `tick.py` every 15 min and commits dedup state back to the repo.

**C. Action buttons → live Vercel webhook** ✅ — `https://life-sepia-psi.vercel.app/api/mark` is deployed. ntfy supports per-notification action buttons; each nudge will look like:

> **Workout** (45m)
> Did you do this yet?
> [ Yes ] [ No ]

Tapping **Yes** hits the webhook (with the shared-secret header), which validates auth and calls the GitHub Contents API to append `{goal_id, status: done, at: HH:MM}` to today's `state/YYYY-MM-DD.yaml`. The render workflow then re-renders the dashboard. Tapping **No** dismisses the notification; the next tick may re-prompt later if the goal is still open.

End-to-end was verified on 2026-05-10 by curling the webhook with a test goal and seeing the commit + dashboard update appear within seconds.

Net effect: 95% of daily marking happens with one tap, no Claude conversation. Claude is only needed for richer edits (new goals, pausing, weekly review, etc.).

I don't run anything. The robot is hosted free (GitHub Actions). The mailbox is free (ntfy.sh). The webhook is free (Vercel hobby tier). The phone app is free.

---

## 7. Escalation ladder — planned

The watcher decides nudge level by **how overdue I am, weighted by priority** — not by auto-detection. The system never assumes I did or didn't do something; it only knows what I've explicitly marked (in Claude or via Yes/No buttons).

| Level | When | What happens |
|---|---|---|
| **Calm** | All goals done, or plenty of day left | Nothing |
| **Soft** | A few things left, more than a third of the day remaining | One gentle phone notification *with Yes/No buttons* asking "did you do X?" |
| **Firm** | An important goal undone and more than half the day is gone | Louder notification *with Yes/No* + the goal gets dropped onto my Google Calendar in the next open slot |
| **Hard** | Multiple important goals undone and only a quarter of the day left | Loud notification *with Yes/No* + my phone flips into a no-distractions mode |
| **Lockdown** *(future, not in v1)* | Day is almost over, criticals undone | Phone screen-locks for a cool-down period |

Thresholds live in `settings.yaml` under `escalation:` (currently `soft_after: 0.30 · firm_after: 0.50 · hard_after: 0.75` of waking-day fraction).

**Per-goal nudge eligibility** is encoded directly on each goal via `nudge_at` (single `"HH:MM"` or list for multi check-ins). Priority no longer drives nudge timing — every active goal carries an explicit time.

---

## 8. Calendar — planned

When the watcher decides a goal needs a calendar block, it:
- looks at my main Google Calendar to find the next genuinely free slot
- creates an event there with prefix `🎯 Life:` and a distinct color
- tags the event description with a hidden marker (`auto-scheduled-by:life-os`) so we can later find/clean up only events we created — never touching anything I made

If I mark the goal done before the event time (via Claude or Yes button), the event gets cancelled automatically.

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
├── PRD Webpage.md                         ← this document
├── README.md                              ✓ built
├── .gitignore                             ✓ built
├── .vercelignore                          ✓ built (scopes Vercel deploy to api/)
├── settings.example.yaml                  ✓ built (committed)
├── settings.yaml                          ✓ built (gitignored — holds secrets)
├── goals.yaml                             ✓ built — 15 goals with category + nudge_at
├── state/
│   ├── 2026-05-10.yaml                    ✓ today
│   ├── 2026-05-06.yaml                    ✓ earlier
│   └── …                                  ⌛ accumulates forever, one file per day
├── render.py                              ✓ built — YAML → HTML (window = 7d)
├── tick.py                                ✓ built (phase 1: print only)
├── style.css                              ✓ built — paper-planner tokens
├── index.html                             ✓ generated
├── design_handoff_life_tracker/           ✓ design reference (V1 — Editorial)
├── api/
│   └── index.py                           ✓ deployed to Vercel — webhook for Yes/No buttons
├── requirements.txt                       ✓ Vercel function deps (PyYAML)
├── vercel.json                            ✓ rewrites /api/mark → /api/index
├── .github/workflows/
│   ├── render.yml                         ✓ built — re-render + deploy Pages on every push
│   └── tick.yml                           ⌛ planned — 15-min watcher cron
├── schedule.py                            ⌛ planned — Google Calendar writes
└── docs/
    └── phone-setup.md                     ⌛ planned — Tasker setup
```

The git repo *is* the database. Every change is versioned. Nothing in `state/` is ever deleted.

---

## 11. The 15 daily goals (current)

Loaded in `goals.yaml`. Each goal carries a `category` (drives the dashboard color stripe + filter pill), a `window` (drives section grouping), and an explicit `nudge_at` (drives the watcher).

| Goal | Category | Window | Nudge at | Time |
|---|---|---|---|---|
| Wake up early | health | morning | 06:00 | — |
| Meditate | mind | morning | 06:00 | 15m |
| Journal | mind | morning | 06:15 | 15m |
| Bath | health | morning | 06:45 | 10m |
| Skin care | health | morning | 06:45 | 5m |
| Multivitamins | health | morning | 08:00 | 1m |
| Workout | health | any | 13:00 | 45m |
| Step out | social | afternoon | 18:00 | 15m |
| Write | mind | morning | 17:00 | 1h |
| Code | skills | any | 18:30 | 1h 30m |
| Course | skills | evening | 19:00 | 30m |
| Practice guitar | skills | any | 20:00 | 30m |
| Language | skills | any | 20:30 | 20m |
| Read | mind | evening | 21:30 | 30m |
| Respond to people | social | any | 10:00 / 15:00 / 21:00 | — |

**Distribution:** health 5 · mind 4 · skills 4 · social 2 · morning 6 · afternoon 1 · evening 5 · anytime 3.

Edit by talking to Claude.

---

## 12. Setup — what I have to do once

1. ✅ Push the local repo to GitHub (`piyushbhutani95-oss/life`, public).
2. ✅ Generate a long random ntfy topic, store in `settings.yaml` (gitignored).
3. ✅ Install **ntfy** Android app, subscribe to the topic — verified with test pushes.
4. ⌛ Connect Google Calendar — *(deferred until `schedule.py` is built)*
5. ✅ Deploy `api/index.py` to Vercel; webhook live at `https://life-sepia-psi.vercel.app/api/mark`. Env vars set: `GITHUB_TOKEN`, `SHARED_SECRET`, `REPO`, `USER_TZ`, `ROLLOVER_HOUR`. Vercel deployment protection disabled (the function authenticates itself via shared secret).
6. ⌛ Install **Tasker** on Android, follow `docs/phone-setup.md` — *(deferred until "Hard" level escalation needs it)*

---

## 13. Day-to-day usage

- **Mac:** open Claude Code in the project folder, talk to it in plain English. Optionally open `index.html` (or the live Pages URL) in a browser tab.
- **Phone:** tap Yes/No on the nudge notifications (once `tick.py` is wired to ntfy + cron). For richer edits ("add goal", "pause this", "what's left this week?"), open `claude.ai/code`, point it at the GitHub repo, and chat.

To regenerate the page after editing files manually:
```
python3 render.py
```

Or just push — `render.yml` regenerates and redeploys to Pages on every commit to `main`.

---

## 14. Out of scope for v1

- Long-term goals (weekly/monthly cadence, progress trends across months)
- Workout-specific module (sets/reps, plans)
- **Auto-detecting completion** (e.g., GitHub commits = "coded", fitness data = "worked out") — explicitly *never* doing this; the system asks instead
- Multi-user / sharing
- Hard phone screen-lock — designed for, not built (the Lockdown level)
- Native phone app
- Click-to-mark on the dashboard itself — the page is read-only by design; marking happens via Claude or the ntfy Yes/No buttons
- Mobile-friendly redesign of the dashboard layout — the current grid reflows to 2-up on phones (good enough), but phone-first usage stays via buttons + `claude.ai/code`

---

## 15. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Watcher accidentally messes up real Calendar events | Only ever touches events with our hidden marker |
| Phone gets spammed during testing | tick.py dedupes per `(goal_id, nudge_time)` per day — won't repeat |
| Pushes arrive while asleep | `quiet_hours` is a list of windows in `settings.yaml`; current value silences `23:00–05:30` (overnight) and `07:00–08:00` (daily 7am meeting) |
| Mailbox name guessed | Long random topic (in gitignored settings); self-host ntfy later if paranoid |
| Webhook abused by anyone who finds the URL | Webhook requires `X-Secret` header (or `?secret=`) matching `SHARED_SECRET` in Vercel env. 40 random chars. Anything else returns 403. |
| Vercel deployment protection blocks ntfy callbacks | Disabled at the project level — webhook auth covers it. |
| Tasker setup finicky on this Android version | Documented for stock Android first; degrade to "loud notification only" if Focus mode flip fails |
| `state/` folder grows unbounded | Fine — text YAML stays tiny; even 10 years ≈ a few MB |

---

## 16. Open questions — resolved

1. ~~**Per-goal nudge eligibility.**~~ Resolved: every active goal has an explicit `nudge_at` field (single `"HH:MM"` or list for multi check-ins). Priority no longer drives nudge timing.
2. ~~**Webhook host.**~~ Resolved: Vercel. Function lives at `api/index.py`, public URL `/api/mark` via rewrite. Free hobby tier covers our load comfortably.

New open questions for the next milestone:

3. **tick.py state-write strategy in cron.** When the GitHub Action runs `tick.py` every 15 min, it needs to commit the updated `notifications_sent` back to today's state file so dedup persists across runs. Options: (a) Action commits state directly via `git push` in the workflow, (b) tick.py uses the same Vercel webhook to record nudges (via a new endpoint or action), (c) tick.py uses the GitHub Contents API directly. Leaning (a) — simplest, tick.py stays a pure script.
4. **Multi-goal nudge format.** When multiple goals fire at once (e.g. 8:00 AM has multivitamins + skin-care), do they go as one combined push with a list, or N separate pushes (one per goal, each with its own Yes/No)? Separate is more actionable but spammy. Decide after first real day of pushes.

---

## 17. Verification — how I know it works

1. ✅ **Webhook smoke test** — curled `/api/mark?goal=test-webhook&status=done` with the secret header, got `200 ok`, saw the commit appear, watched the dashboard re-render. Done 2026-05-10.
2. ⌛ **Full pipeline smoke test** — once `tick.py` is wired to ntfy + cron: trigger a tick at a fake time, confirm phone buzzes with a real notification, tap Yes, see the commit appear and the dashboard tile go to "done".
3. ⌛ **One real week** — use it as the daily driver for a full week, then review:
   - Did the dashboard reflect reality?
   - Did pushes arrive at the right times without annoying me?
   - Did the Yes/No buttons feel faster than opening Claude?
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

- **2026-05-06** — concept locked, PRD written. v0 skeleton built (YAML schema, render.py, sample dashboard). Goals expanded to actual 18-item list. Multi-day tracker added (grid + streaks). CSS extracted to `style.css`. First Claude design pass (warm paper bg, cobalt accent, Instrument Serif typography).
- **2026-05-06 (later)** — Dashboard window narrowed from 14 days to 7 days. Full history continues to be stored unbounded in `state/`. PRD updated with: phone-update path via `claude.ai/code`, interactive ntfy notifications with Yes/No buttons + Vercel webhook, explicit "no auto-detection" stance, storage-vs-display split (§4a).
- **2026-05-07** — Day window made fractional (`start_hour: 5.5` to support 05:30 wake). All 18 goals got explicit `nudge_at` times after a one-by-one pass. Priority dropped as the basis for nudge timing. `quiet_hours` migrated from a single start/end to a list of windows; added the `07:00–08:00` daily-meeting block.
- **2026-05-10** — Full design refresh per `design_handoff_life_tracker/` (V1 — Editorial / paper-planner). Dropped the cobalt-blue grid-notebook look. New aesthetic: cream paper + 28px ruled grid, Newsreader italic + JetBrains Mono, pastel category accents, light + dark themes switchable via header toggle. Goals re-grouped into time-of-day sections instead of one flat grid. Cards reflow via auto-fill grid; 100vh lock dropped. Added `category` field to schema. Filter pills (functional, persisted) collapse empty sections. Removed `b12`, `creatine`, `talk-to-people` — 15 goals total.
- **2026-05-10 (later)** — Repo pushed to GitHub (`piyushbhutani95-oss/life`, public). `render.yml` workflow built — re-renders + deploys to GitHub Pages on every push; live at `https://piyushbhutani95-oss.github.io/life/`. `tick.py` built (phase 1: print-only). ntfy topic generated, phone subscribed, test pushes verified. **Vercel webhook deployed end-to-end** at `https://life-sepia-psi.vercel.app/api/mark` — `api/mark.py` renamed to `api/index.py` for Vercel auto-detect, with `vercel.json` rewrite preserving the `/api/mark` URL; `.vercelignore` scopes the deploy; 5 env vars set; Deployment Protection disabled (webhook does its own shared-secret auth). Verified by curling the webhook with a test goal and watching the commit + dashboard update appear within seconds.
- **Next up:** wire `tick.py`'s `emit_payload()` to actually POST to ntfy (with Yes/No action buttons pointing at the webhook + secret), then add `.github/workflows/tick.yml` to run it every 15 min.
