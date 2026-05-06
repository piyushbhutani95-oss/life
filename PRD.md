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

I tell it my daily goals. It shows me, at any moment, what's done and what's left, and how I've been doing across the past two weeks. As the day wears on and I haven't done things, it nudges me — gently first, then louder. Worst case, it flips my phone into a no-distractions mode so I stop scrolling and get back to work.

**This is not an app.** No login, no UI to click through, no buttons to design. It's a webpage I look at, and I talk to Claude (in this terminal) to update it. Claude is my keyboard.

Scope for now: **daily goals only.** Long-term goals, workouts as a separate module, and anything that auto-detects whether I did something — all later.

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
2. Through the day, I tell Claude *"done"*, *"skipped"*, *"what's left?"*. Claude appends to today's state file. The webpage reflects it on next refresh.
3. *(planned)* Every 15 minutes, on its own, a tiny background watcher looks at the current time and what I haven't done yet.
4. *(planned)* If I'm fine, it does nothing. If I'm a bit behind → soft phone notification. Meaningfully behind → louder notification + the unfinished goal gets dropped onto Google Calendar in the next free slot. Seriously behind → loud notification + my phone flips into a "no distractions" mode.

---

## 4. The webpage — built

Open `index.html` in a browser. Two zones:

**Dashboard (top)**
- Big serif date heading
- One-line italic status sentence ("On track. 5 of 18 done." / "A bit behind. 13 open with 40% of the day left.")
- Progress strip: `N of total` · coral fill line · `% of the day`
- "Next up" — top 3 open items, sorted by priority then time-of-day window

**Habits (below)**
- All 18 goals as rows
- Each row: title + meta (duration · window · priority) on the left
- 14-day tracker grid: filled coral cell = done, half-fill = partial, faded cell = skipped, outlined cell = no entry
- Today's column wears a coral ring
- Current streak count on the right (consecutive done days ending today; an open today doesn't break the streak)

**Footer:** local time · last nudge sent today

Design language: the Claude warm-paper palette (`#F0EEE6` background, `#CC785C` coral accent, `#191814` ink), Source Serif 4 for display and body, Inter for small UI labels. Document-like. Dark mode supported via `prefers-color-scheme`.

---

## 5. How I talk to it

Open Claude Code in the project folder and say things in plain English. Examples:

- *"Add a goal: meditate 15 minutes, prefer mornings"*
- *"Mark workout done"*
- *"Skip reading today"*
- *"Mark vitamins, b12, creatine done"*
- *"What's left for today?"*
- *"Pause guitar for now"* (sets `active: false`)
- *"Schedule the rest into my calendar"* (planned)
- *"Tone down the nagging today, I'm sick"* (planned)

Claude edits the underlying YAML files and runs `render.py`. No forms, no UI to build.

---

## 6. Push notifications — planned

Two pieces work together:

**A. The mailbox (ntfy.sh)** — A free service. I get a private mailbox with a long secret name. Anything dropped in shows up as a notification on my phone. I install one free Android app that listens to my mailbox.

**B. The robot (GitHub Actions cron)** — Every 15 minutes, a tiny job hosted free by GitHub wakes up, looks at my goals + the time, and decides if I'm slacking. If I am, it drops a message in my mailbox → my phone buzzes.

I don't run anything. The robot is hosted for free. The mailbox is free. The phone app is free.

---

## 7. Escalation ladder — planned

| Level | When | What happens |
|---|---|---|
| **Calm** | All goals done, or plenty of day left | Nothing |
| **Soft** | A few things left, more than a third of the day remaining | One gentle phone notification with a summary |
| **Firm** | An important goal undone and more than half the day is gone | Louder notification + the goal gets dropped onto my Google Calendar in the next open slot |
| **Hard** | Multiple important goals undone and only a quarter of the day left | Loud notification + my phone flips into a no-distractions mode |
| **Lockdown** *(future, not in v1)* | Day is almost over, criticals undone | Phone screen-locks for a cool-down period |

Thresholds live in `settings.yaml` under `escalation:`.

---

## 8. Calendar — planned

When the watcher decides a goal needs a calendar block, it:
- looks at my main Google Calendar to find the next genuinely free slot
- creates an event there with prefix `🎯 Life:` and a distinct color
- tags the event description with a hidden marker (`auto-scheduled-by:life-os`) so we can later find/clean up only events we created — never touching anything I made

If I mark the goal done before the event time, the event gets cancelled automatically.

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
│   └── 2026-05-06.yaml                 ✓ built — empty today state
├── render.py                           ✓ built — YAML → HTML
├── style.css                           ✓ built — Claude design tokens
├── index.html                          ✓ generated
├── tick.py                             ⌛ planned — 15-min watcher
├── schedule.py                         ⌛ planned — Google Calendar writes
├── .github/workflows/tick.yml          ⌛ planned — GitHub Actions cron
└── docs/
    └── phone-setup.md                  ⌛ planned — Tasker setup
```

The git repo *is* the database. Every change is versioned.

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

1. ~~Make a private GitHub repo~~ — local repo initialized; push to GitHub when ready
2. Generate a long random ntfy topic name and put it in `settings.yaml` — ~5 min *(deferred until tick.py is built)*
3. Install the **ntfy** app on Android, subscribe to that topic — ~5 min *(deferred)*
4. Connect Google Calendar — ~10 min *(deferred until schedule.py is built)*
5. Install **Tasker** on Android, follow `docs/phone-setup.md` — ~20 min *(deferred)*

Total: under an hour. Not all of it is needed today.

---

## 13. Day-to-day usage

Open Claude Code in the project folder, talk to it in plain English. Optionally open `index.html` in a browser tab to see the dashboard.

To regenerate the page after editing files manually:
```
python3 render.py
```

---

## 14. Out of scope for v1

- Long-term goals (weekly/monthly cadence, progress trends across months)
- Workout-specific module (sets/reps, plans)
- Auto-detecting completion (e.g., GitHub commits = "coded", fitness data = "worked out")
- Multi-user / sharing
- Hard phone screen-lock — designed for, not built (the Lockdown level)
- Native phone app
- Mobile-friendly version of the dashboard view (phone gets pushes, Mac gets the dashboard)

---

## 15. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Watcher accidentally messes up real Calendar events | Only ever touches events with our hidden marker |
| Phone gets spammed during testing | Watcher dedupes — won't repeat itself within 15 min |
| Pushes arrive while asleep | Quiet hours configurable in `settings.yaml` |
| Mailbox name guessed | Use a long random string. Self-host ntfy later if paranoid |
| Tasker setup finicky on this Android version | Documented for stock Android first; degrade to "loud notification only" if Focus mode flip fails |

---

## 16. Verification — how I know it works

1. **Smoke test** — add 3 goals, manually trigger the robot with the clock pretending it's late afternoon, confirm phone buzzes and a calendar block appears
2. **One real week** — use it as the daily driver for a full week, then review:
   - Did the dashboard reflect reality?
   - Did pushes arrive at the right times without annoying me?
   - Did I actually do more of my goals than the week before?
   - What felt missing or wrong?

That review decides what v2 looks like.

---

## 17. Where it goes after v1

- **v2:** medium-term goals (weeks/months), workout module, auto-detection (GitHub commits, fitness data, calendar attendance)
- **v3:** the Lockdown level — actual phone screen-lock when drastically off-track
- **v4:** Claude proposes the day's plan in the morning based on calendar gaps + my goals

---

## 18. Session log

- **2026-05-06** — concept locked, PRD written. v0 skeleton built (YAML schema, render.py, sample dashboard). Goals expanded to actual 18-item list. Multi-day tracker added (14-day grid + streaks). CSS extracted to `style.css`. Claude design pass applied (warm paper bg, coral accent, Source Serif 4 typography).
- **Next up:** `tick.py` (escalation logic + ntfy push) and the GitHub Actions workflow.
