// Accessors for the globals Wagtail exposes for Draftail plugins.
//
// Wagtail bundles Draftail, React and Draft.js and exposes them as globals:
//   - `window.React` / `window.DraftJS` — React and Draft.js
//   - `window.Draftail` — the Draftail library (`ToolbarButton`, `Icon`, ...)
//   - `window.draftail` — Wagtail's registration wrapper (`registerPlugin`)
//
// The production bundle is built with `react` and `draft-js` aliased to
// `window.React` / `window.DraftJS`, so it shares the exact instances the
// editor uses rather than shipping conflicting copies. In tests these globals
// are absent and the helpers fall back to the modules from node_modules.

export interface DraftailRegistry {
  registerPlugin?: (plugin: unknown, type?: string) => unknown;
}

export interface DraftailLib {
  ToolbarButton?: unknown;
  Icon?: unknown;
}

function getWindow(): Record<string, unknown> {
  return typeof window === "undefined"
    ? {}
    : (window as unknown as Record<string, unknown>);
}

// Wagtail's plugin registry (lowercase `draftail`).
export function getDraftailRegistry(): DraftailRegistry {
  return (getWindow().draftail as DraftailRegistry) || {};
}

// The Draftail UI library (capitalised `Draftail`).
export function getDraftailLib(): DraftailLib {
  return (getWindow().Draftail as DraftailLib) || {};
}
