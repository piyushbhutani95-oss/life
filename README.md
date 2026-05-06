# Life Webpage

A personal page that helps me actually do what I say I'll do each day.

I tell Claude my daily goals. Through the day I tell Claude what I've done. The page reflects it. Every 15 minutes, a free background timer checks if I'm slacking — if I am, my phone buzzes, and at the worst level it flips into a no-distractions mode.

This is not an app. It's a folder of plain files plus a webpage I open in a browser.

See `PRD.md` (or `~/.claude/plans/ok-so-this-is-rosy-quail.md`) for the full product write-up.

## Files

| File | What it is |
|---|---|
| `goals.yaml` | My recurring daily goals. Edited by Claude when I say "add a goal" / "remove a goal". |
| `state/<date>.yaml` | Today's status — what's done, skipped, etc. One file per day, archive of the past. |
| `settings.yaml` | My settings: ntfy mailbox, calendar info, escalation thresholds. **Not committed** (in `.gitignore`). |
| `settings.example.yaml` | Committed template. Copy to `settings.yaml` and fill in. |
| `render.py` | Reads the above and generates `index.html`. Run any time state changes. |
| `index.html` | The dashboard. Open in a browser. |
| `tick.py` | (later) The 15-min watcher. Computes escalation level, fires phone push if behind. |
| `schedule.py` | (later) Writes calendar blocks for undone goals. |
| `.github/workflows/tick.yml` | (later) The free GitHub-hosted timer that runs `tick.py` every 15 min. |
| `docs/phone-setup.md` | (later) One-time Tasker setup on Android. |

## Day-to-day usage

Open Claude Code in this folder and talk in plain English:

- "Add a goal: meditate 15 minutes, prefer mornings"
- "Mark workout done"
- "Skip reading today"
- "What's left for today?"
- "Schedule the rest into my calendar"

Claude edits the underlying files. Refresh `index.html` to see the change.

## First-time setup (under an hour)

1. Generate a long random ntfy topic name and put it in `settings.yaml` (copy from `settings.example.yaml`)
2. Install the **ntfy** app on Android, subscribe to that topic
3. (Later) Connect Google Calendar — instructions in `docs/google-setup.md`
4. (Later) Install **Tasker** on Android, follow `docs/phone-setup.md`

## How to view the dashboard

```
python3 render.py && open index.html
```
