# Handoff: Life Tracker (V1 — Editorial)

## Overview
A daily habit tracker that shows ~18 recurring habits grouped by time-of-day (morning / afternoon / evening), each with a 14-day streak strip and a one-tap completion toggle. This bundle contains a single direction — **V1, the paper / editorial look** — in light and dark themes.

## About the Design Files
The files in this bundle are **design references created in HTML** — an interactive prototype that shows intended look, layout, and behavior. They are **not production code to copy directly**.

The task is to **recreate this design in the target codebase's existing environment** (React, Vue, SwiftUI, native, etc.) using its established patterns, component library, and design tokens. If no environment exists yet, choose the most appropriate framework for the project and implement it there. Treat the JSX/CSS as a precise spec for visual output, not a drop-in.

## Fidelity
**High-fidelity (hifi).** Final colors, typography, spacing, and interactions are locked. Match pixel-for-pixel using the codebase's existing libraries.

- Exact hex values for light/dark themes are listed below — do not improvise.
- Type scale and weights are intentional — Newsreader italic for the date and habit titles is the design.
- Pastel category accents (mint / lilac / butter / rose) are locked across both themes.

---

## Screen — Today

**Layout**
- Single column, padding `32px 36px 80px` (mobile: `22px 18px 60px`).
- Header → main → footer, gap controlled per-section.
- Cards laid out in `grid-template-columns: repeat(auto-fill, minmax(170px, 1fr))` with 10px gap (mobile: 150px min, then 1fr 1fr at <540px).
- Page background carries a subtle 28×28px ruled grid (`linear-gradient` cross-pattern in `--rule-soft`).

**Header components (top to bottom)**
1. **Headline row** — flex, baseline:
   - Day-of-week eyebrow — JetBrains Mono 11px, 0.22em tracking, uppercase, color `--ink-soft`.
   - Date `may 6` — Newsreader italic 400, `clamp(48px, 7vw, 88px)`, line-height 0.9, letter-spacing -0.02em.
   - Time `14:44` — JetBrains Mono 14px, color `--muted`, pushed right via `margin-left: auto`.
2. **Progress line** — flex, 14px gap, max-width 460px:
   - 6px-tall pill track (color `--rule-soft`), inner fill `--accent`, transition `width .3s ease`.
   - Italic Newsreader percentage to the right (22px), with mono `%` suffix (13px, muted).
3. **Filter pills** — flex, 6px gap, wrap:
   - Capsule buttons, mono lowercase, 11px, 0.1em tracking.
   - 8px round dot in the category color, label, count (9px, opacity 0.7).
   - Active state: ink background, paper-bg text.

**Section (`morning` / `afternoon` / `evening`)**
- Eyebrow head: italic Newsreader 30px title, mono `06 — 12` range (10px, 0.18em tracking, uppercase, muted), 1px ruled line filling remaining width, then count (mono 10px).
- Cards grid below.

**Card**
- Background `--paper-card`, 1px border `--rule`, radius 6px, padding `12px 14px 10px`, min-height 92px.
- Top accent stripe — 3px tall, inset 14px left/right, `border-radius: 0 0 3px 3px`, color = category.
- Title — Newsreader italic 400, 20px, line-height 1.1, padded right 22px to clear the check button.
- Check button — top-right, 18px circle, 1.5px border `--rule`, paper-bg fill. On `is-done` it fills with the category accent color and shows a checkmark.
- Streak row at bottom — 14 dashed cells (`flex: 1`, 6px tall, 1.5px radius, 2px gap). On-cells turn the category color. Today's cell gets `outline: 1.5px solid var(--ink); height: 8px`.
- Streak flame badge (mono 10px, ✦ + number) only when current streak ≥ 3.
- Hover: lift 1px, slightly darker card bg, deeper shadow.
- `is-done`: opacity 0.5, title strikethrough, card bg matches paper-bg.

**Footer**
- Mono 10px, 0.12em tracking, muted, three-cell flex (date · status · version).

---

## Interactions & Behavior

- **Toggle complete** — clicking the check button (or any card body) flips `done[id]`. Instant — no animation other than CSS transitions.
- **Filter** — clicking a filter pill sets the active category (`'all' | 'health' | 'mind' | 'skills' | 'social'`). Filtering is client-side; an empty time-of-day section renders nothing.
- **Theme** — `light` ↔ `dark`. Persist to localStorage / user prefs. CSS vars on `.v1-root` swap; everything downstream rebuilds via `color-mix`.
- **Hover** — cards lift 1px and deepen shadow.
- **Streak rendering** — last index of `streak[]` is "today." Render outline on that index. `currentStreak` = trailing count of 1s.
- **Responsive** — collapses to 2-col cards <540px; filter row scrolls horizontally.

## State Management

Component-local is fine:
- `filter: 'all' | 'health' | 'mind' | 'skills' | 'social'`
- `done: Record<habitId, boolean>`
- `mode: 'light' | 'dark'` (persist)

App-wide:
- The habits collection (see Data Model).
- Current time (re-tick at minute boundaries if you want the header time live).

## Data Model

```ts
type Category = 'health' | 'mind' | 'skills' | 'social';
type TimeOfDay = 'morning' | 'afternoon' | 'evening';

interface Habit {
  id: string;            // 'wake', 'bath', 'code'…
  name: string;          // display title
  time: TimeOfDay;       // grouping
  hour: number;          // 0–23 (used by V2; harmless to keep on V1)
  duration: number | null; // minutes, optional
  durLabel: string;      // display string e.g. '15m', '1h 30m', or ''
  priority: 'high' | null;
  category: Category;
  streak: (0 | 1)[];     // length 14, last item = today
  done: boolean;         // initial state
}
```

The seed data in `data.jsx` has 18 habits (8 morning · 6 afternoon · 4 evening). Use it verbatim for design QA, then swap to your real source.

---

## Design Tokens

### Light theme
| Token        | Value      | Use |
|---           |---         |---  |
| `--paper-bg`   | `#fafaf6` | Page background |
| `--paper-card` | `#ededdf` | Card background |
| `--ink`        | `#171712` | Primary text |
| `--accent`     | `#2d2d28` | Progress fill, active filter |

### Dark theme (cool slate)
| Token        | Value      | Use |
|---           |---         |---  |
| `--paper-bg`   | `#1a1d22` | Page background |
| `--paper-card` | `#252932` | Card background |
| `--ink`        | `#ece9e0` | Primary text |
| `--accent`     | `#d9b366` | Progress fill, active filter |

### Category accents (pastel — locked across both themes)
| Token        | Value      |
|---           |---         |
| `--c-health` | `#9ec1a8` (mint) |
| `--c-mind`   | `#b6a8d1` (lilac) |
| `--c-skills` | `#d9c07a` (butter) |
| `--c-social` | `#d9a0a0` (rose) |

### Derived (compute via `color-mix(in oklab, ...)`)
- `--ink-soft       = mix(ink, paper-bg, 70/30)`
- `--muted          = mix(ink, paper-bg, 45/55)`
- `--rule           = mix(ink, paper-bg, 18/82)`
- `--rule-soft      = mix(ink, paper-bg, 10/90)`
- `--paper-card-hover = mix(paper-card, ink, 88/12)`

### Typography
- **Newsreader** (Google Fonts) — italic display + card titles. Weights used: 400 italic.
- **JetBrains Mono** — numerics, eyebrows, time, counts. Weights used: 400, 500, 600.
- **Inter Tight** is loaded for fallback / chrome but the V1 surface itself only uses Newsreader + JetBrains Mono.

Add to `<head>`:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,wght@0,400;1,400&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
```

### Spacing
- Page padding: `32px 36px 80px` desktop · `22px 18px 60px` mobile.
- Card padding: `12px 14px 10px`.
- Card gap (grid): 10px.
- Section gap: 28px.
- Cards minimum width: 170px desktop · 150px tablet · `1fr 1fr` <540px.

### Radii
- 6px — cards.
- 999px — pills (filters, progress track, streak flame badge).
- 50% — check circle, filter dot.

### Shadows
- Card rest: `0 1px 0 rgba(0,0,0,0.03), 0 4px 12px -8px rgba(0,0,0,0.18)`
- Card hover: `0 1px 0 rgba(0,0,0,0.04), 0 8px 18px -8px rgba(0,0,0,0.25)`

### Background grid
```css
background-image:
  linear-gradient(to right, var(--rule-soft) 1px, transparent 1px),
  linear-gradient(to bottom, var(--rule-soft) 1px, transparent 1px);
background-size: 28px 28px;
```

### Animations
- Card hover: `all .18s ease`.
- Filter hover: `all .15s ease`.
- Progress fill: `width .3s ease`.

## Assets
No images, no icon library. All glyphs are inline SVG paths or text:
- Check icon — 11×11 viewBox check path.
- Streak flame — text glyph `✦`.

If your codebase has a Lucide / Phosphor / SF Symbols equivalent, swap to that. Stroke weight in the prototype is 1.6.

## Files in this bundle

- `Life Tracker V1.html` — runnable demo. Loads React 18 + Babel standalone, mounts `<V1 />` and wires a small theme-toggle button (top-right) to flip light/dark. The toggle is **demo-only** — your app's real UI controls the `mode` state.
- `v1.jsx` — V1 React component. Contains:
  - `THEMES` (light/dark CSS-var sets)
  - `PASTEL` (locked category accents)
  - `__v1Bus` (mini pub/sub for the demo theme toggle — drop in your own state lib)
  - `V1` component (`<header>` + 3 `<Section>`s + `<footer>`)
  - `V1TweaksPanel` — only used by the original prototype scaffolding; safe to delete on your end.
- `v1.css` — V1 styles. All CSS-var-driven so themes swap via a single root class/inline-style change.
- `data.jsx` — shared `HABITS` array + `CATEGORIES` derived counts. Mirror this shape on your end.

## Implementation order suggestion
1. Set up the data layer matching the `Habit` interface above.
2. Drop `v1.css` into your stylesheet pipeline (or convert to your CSS-modules / styled-components / Tailwind layer).
3. Build the layout shell (`.v1-root`) with light theme; verify the grid + card spec.
4. Add the dark theme — should be a single CSS-var swap on a root class.
5. Hook completion + filter to your real state store.
6. Replace inline SVG icons with your icon system.
