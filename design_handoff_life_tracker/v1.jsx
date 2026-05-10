// V1 — Pleasant paper planner. Palette controlled at App level via window.__v1Bus.

const { useState, useMemo, useEffect, useSyncExternalStore } = React;

const V1_TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "mode": "light"
}/*EDITMODE-END*/;

// [pageBg, cardBg, ink, accent]
const THEMES = {
  light: ["#fafaf6", "#ededdf", "#171712", "#2d2d28"], // off-white minimal
  dark:  ["#1a1d22", "#252932", "#ece9e0", "#d9b366"], // cool slate dark
};
// Pastel category accents — locked
const PASTEL = ["#9ec1a8", "#b6a8d1", "#d9c07a", "#d9a0a0"];

// ── Palette bus: shared state across all V1 artboard instances ──
if (!window.__v1Bus) {
  const listeners = new Set();
  window.__v1Bus = {
    state: { mode: V1_TWEAK_DEFAULTS.mode },
    set(next) {
      window.__v1Bus.state = { ...window.__v1Bus.state, ...next };
      listeners.forEach(fn => fn());
    },
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    get() { return window.__v1Bus.state; },
  };
}
window.V1_THEMES = THEMES;
window.V1_TWEAK_DEFAULTS = V1_TWEAK_DEFAULTS;

function useV1Palette() {
  return useSyncExternalStore(
    window.__v1Bus.subscribe,
    window.__v1Bus.get
  );
}

function V1() {
  const palette = useV1Palette();
  const [filter, setFilter] = useState('all');
  const [done, setDone] = useState({});

  const habits = useMemo(() =>
    window.HABITS.filter(h => filter === 'all' || h.category === filter),
    [filter]
  );

  const groups = useMemo(() => {
    const g = { morning: [], afternoon: [], evening: [] };
    habits.forEach(h => g[h.time].push(h));
    return g;
  }, [habits]);

  const totalDone = Object.values(done).filter(Boolean).length;
  const total = habits.length;
  const progressPct = total ? Math.round((totalDone / total) * 100) : 0;
  const toggle = (id) => setDone(d => ({ ...d, [id]: !d[id] }));

  const [pageBg, cardBg, ink, accent] = THEMES[palette.mode] || THEMES.light;
  const styleVars = {
    '--paper-bg': pageBg, '--paper-card': cardBg, '--ink': ink, '--accent': accent,
    '--c-health': PASTEL[0], '--c-mind': PASTEL[1], '--c-skills': PASTEL[2], '--c-social': PASTEL[3],
  };

  return (
    <div className="v1-root" style={styleVars}>
      <header className="v1-header">
        <div className="v1-headline">
          <span className="v1-day">Wednesday</span>
          <h1 className="v1-date">may 6</h1>
          <span className="v1-time">14:44</span>
        </div>
        <div className="v1-progress-line">
          <div className="v1-progress-track">
            <div className="v1-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
          <span className="v1-progress-num">{progressPct}<span className="v1-progress-suf">%</span></span>
        </div>
        <nav className="v1-filters">
          {window.CATEGORIES.map(c => (
            <button key={c.id}
              className={`v1-filter v1-filter-${c.id} ${filter === c.id ? 'is-active' : ''}`}
              onClick={() => setFilter(c.id)}>
              <span className="v1-filter-dot" />
              <span>{c.label}</span>
              <span className="v1-filter-count">{c.count}</span>
            </button>
          ))}
        </nav>
      </header>

      <main className="v1-main">
        <Section slug="morning"   title="morning"   range="06 — 12" habits={groups.morning}   done={done} toggle={toggle} />
        <Section slug="afternoon" title="afternoon" range="12 — 18" habits={groups.afternoon} done={done} toggle={toggle} />
        <Section slug="evening"   title="evening"   range="18 — 24" habits={groups.evening}   done={done} toggle={toggle} />
      </main>

      <footer className="v1-footer">
        <span>2026 · 05 · 06</span>
        <span className="v1-foot-mid">no nudges sent today</span>
        <span>v.03</span>
      </footer>
    </div>
  );
}

// Mounted ONCE at App level — controls palette for all V1 artboards
function V1TweaksPanel() {
  const [t, setTweak] = window.useTweaks(V1_TWEAK_DEFAULTS);
  useEffect(() => {
    window.__v1Bus.set({ mode: t.mode });
  }, [t.mode]);

  return (
    <window.TweaksPanel title="V1 Theme">
      <window.TweakRadio
        label="Mode"
        value={t.mode}
        options={['light', 'dark']}
        onChange={(v) => setTweak('mode', v)}
      />
    </window.TweaksPanel>
  );
}

function Section({ slug, title, range, habits, done, toggle }) {
  if (habits.length === 0) return null;
  return (
    <section className={`v1-section v1-sec-${slug}`}>
      <div className="v1-sec-head">
        <h2 className="v1-sec-title">{title}</h2>
        <span className="v1-sec-range">{range}</span>
        <span className="v1-sec-rule" />
        <span className="v1-sec-count">{habits.length}</span>
      </div>
      <div className="v1-cards">
        {habits.map(h => (
          <Card key={h.id} habit={h} done={!!done[h.id]} toggle={() => toggle(h.id)} />
        ))}
      </div>
    </section>
  );
}

function Card({ habit, done, toggle }) {
  const currentStreak = (() => {
    let n = 0;
    for (let i = habit.streak.length - 1; i >= 0; i--) { if (habit.streak[i]) n++; else break; }
    return n;
  })();
  return (
    <article className={`v1-card v1-cat-${habit.category} ${done ? 'is-done' : ''}`} onClick={toggle}>
      <button className="v1-check" onClick={(e) => { e.stopPropagation(); toggle(); }}
        aria-label={done ? 'Mark incomplete' : 'Mark done'}>
        {done && (
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
            <path d="M2 5.5l2.2 2.2 4.8-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </button>
      <h3 className="v1-card-title">{habit.name}</h3>
      <div className="v1-card-streak">
        <div className="v1-streak-cells">
          {habit.streak.map((v, i) => (
            <span key={i} className={`v1-sc ${v ? 'on' : 'off'} ${i === habit.streak.length - 1 ? 'today' : ''}`} />
          ))}
        </div>
        {currentStreak >= 3 && <span className="v1-streak-flame">✦ {currentStreak}</span>}
      </div>
    </article>
  );
}

window.V1 = V1;
window.V1TweaksPanel = V1TweaksPanel;
