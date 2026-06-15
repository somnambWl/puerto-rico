/**
 * ActionPrompt — the legal actions as buttons, grouped by `kind`.
 *
 * Only meaningful on the human's turn (the backend sends an empty
 * legal_actions list otherwise). Clicking sends {action_id} via `onAction`.
 * Buttons are disabled while animating / on AI turns. When the prompt is
 * disabled because it is an AI seat's turn, a clear "AI is thinking…" indicator
 * is shown instead.
 *
 * Hover highlighting is best-effort: the backend only gives us `label` + `kind`
 * (no structured detail), so we parse the human-readable label for a tile /
 * building / ship / role / good reference and emit a `Highlight` for the Board.
 */

import type { Highlight, LegalAction } from "../types";
import { BUILDINGS, GOOD_NAMES, ROLE_NAMES } from "../types";

interface ActionPromptProps {
  legalActions: LegalAction[];
  onAction: (id: number) => void;
  /** True while animating or on an AI turn or terminal. */
  disabled: boolean;
  /** True specifically because it is an AI seat's turn (shows "thinking"). */
  aiThinking: boolean;
  onHighlight: (h: Highlight) => void;
}

// Group order + friendly headers for the coarse `kind` categories
// (schemas.py: role/tile/build/colonist/sell/ship/choose/pass).
const KIND_LABELS: Record<string, string> = {
  role: "Choose a role",
  tile: "Choose a tile",
  build: "Build",
  colonist: "Place a colonist",
  sell: "Sell a good",
  ship: "Ship goods",
  choose: "Choose",
  pass: "Pass",
};
const KIND_ORDER = [
  "role",
  "tile",
  "build",
  "colonist",
  "sell",
  "ship",
  "choose",
  "pass",
];

/** Best-effort: parse a label into a board highlight. */
function highlightFor(action: LegalAction): Highlight {
  const label = action.label.toLowerCase();

  // Building reference (build kind, or any label naming a building).
  for (const [id, meta] of Object.entries(BUILDINGS)) {
    if (label.includes(meta.name.toLowerCase())) {
      return { kind: "building", buildingId: Number(id) };
    }
  }
  // Role reference.
  for (const [r, name] of Object.entries(ROLE_NAMES)) {
    if (label.includes(name.toLowerCase())) {
      return { kind: "role", role: Number(r) };
    }
  }
  // Ship reference, e.g. "... ship #2" / "ship 2".
  const shipMatch = label.match(/ship\s*#?\s*(\d+)/);
  if (shipMatch) {
    const n = Number(shipMatch[1]);
    return { kind: "ship", index: n - 1 };
  }
  // Good reference (corn / indigo / sugar / tobacco / coffee).
  for (const [g, name] of Object.entries(GOOD_NAMES)) {
    if (label.includes(name)) {
      return { kind: "good", good: Number(g) };
    }
  }
  return null;
}

export function ActionPrompt({
  legalActions,
  onAction,
  disabled,
  aiThinking,
  onHighlight,
}: ActionPromptProps) {
  if (aiThinking) {
    return (
      <div className="action-prompt">
        <div className="ai-thinking">
          <span className="spinner" /> AI is thinking…
        </div>
      </div>
    );
  }

  if (legalActions.length === 0) {
    return (
      <div className="action-prompt">
        <div className="muted">Waiting…</div>
      </div>
    );
  }

  // Group by kind, preserving the configured order.
  const groups = new Map<string, LegalAction[]>();
  for (const a of legalActions) {
    const arr = groups.get(a.kind) ?? [];
    arr.push(a);
    groups.set(a.kind, arr);
  }
  const orderedKinds = [
    ...KIND_ORDER.filter((k) => groups.has(k)),
    ...[...groups.keys()].filter((k) => !KIND_ORDER.includes(k)),
  ];

  return (
    <div className="action-prompt">
      <h3>Your move</h3>
      {orderedKinds.map((kind) => (
        <div key={kind} className="action-group">
          <div className="action-group-label">
            {KIND_LABELS[kind] ?? kind}
          </div>
          <div className="action-buttons">
            {groups.get(kind)!.map((a) => (
              <button
                key={a.id}
                className="action-btn"
                disabled={disabled}
                onClick={() => {
                  onHighlight(null);
                  onAction(a.id);
                }}
                onMouseEnter={() => onHighlight(highlightFor(a))}
                onMouseLeave={() => onHighlight(null)}
              >
                {a.label}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
