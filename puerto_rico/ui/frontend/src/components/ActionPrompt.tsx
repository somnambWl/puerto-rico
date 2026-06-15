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
 * building / role / good reference and emit a `Highlight` for the Board. Ship
 * (LOAD) labels carry only a quantity (e.g. "Ship 3 Tobacco"), not a ship id,
 * so the `ship` kind highlights the cargo-ships area generically.
 */

import { useCatalog, useRoleInfo } from "../catalog";
import { guidanceFor } from "../guidance";
import { placardDoubloons, roleHints } from "../roleHints";
import type { Catalog, GameView, Highlight, LegalAction } from "../types";
import { GOOD_NAMES, ROLE_NAMES } from "../types";
import { InfoTooltip, RoleTooltipBody } from "./Tooltip";

interface ActionPromptProps {
  legalActions: LegalAction[];
  onAction: (id: number) => void;
  /** True while animating or on an AI turn or terminal. */
  disabled: boolean;
  /** True specifically because it is an AI seat's turn (shows "thinking"). */
  aiThinking: boolean;
  onHighlight: (h: Highlight) => void;
  /** Request a state preview for the hovered/focused action (null = clear). */
  onPreview?: (action: LegalAction | null) => void;
  /** Current view, for computing dynamic role-tooltip hints. */
  view?: GameView;
}

/** Parse the Role enum index a "Take role: X" label refers to (or null). */
function roleOf(action: LegalAction): number | null {
  if (action.kind !== "role") return null;
  const label = action.label.toLowerCase();
  for (const [r, name] of Object.entries(ROLE_NAMES)) {
    if (label.includes(name.toLowerCase())) return Number(r);
  }
  return null;
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

/**
 * Best-effort: parse a label into a board highlight. Building names come from
 * the /catalog (so they stay correct if the engine renames a building); the
 * shipping (LOAD) label has no ship id, so a `ship`-kind action highlights all
 * cargo ships generically (index < 0).
 */
function highlightFor(action: LegalAction, catalog: Catalog | null): Highlight {
  const label = action.label.toLowerCase();

  // Building reference (build kind, or any label naming a building). Match the
  // longest catalog name first so "Small Indigo Plant" beats "Indigo Plant".
  if (catalog) {
    const byLen = [...catalog.buildings].sort(
      (a, b) => b.name.length - a.name.length,
    );
    for (const b of byLen) {
      if (label.includes(b.name.toLowerCase())) {
        return { kind: "building", buildingId: b.id };
      }
    }
  }
  // Role reference.
  for (const [r, name] of Object.entries(ROLE_NAMES)) {
    if (label.includes(name.toLowerCase())) {
      return { kind: "role", role: Number(r) };
    }
  }
  // Shipping: LOAD labels are "Ship <qty> <Good>" — the number is a quantity,
  // not a ship id, so highlight the cargo-ships area as a whole.
  if (action.kind === "ship") {
    return { kind: "ship", index: -1 };
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
  onPreview,
  view,
}: ActionPromptProps) {
  const catalog = useCatalog();
  const roleInfo = useRoleInfo();
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

  // Plain-language instruction for the current decision (only meaningful on the
  // human's turn — when `disabled`, the buttons aren't actionable anyway).
  const guidance = !disabled && view ? guidanceFor(view, legalActions) : null;

  return (
    <div className="action-prompt">
      <h3>Your move</h3>
      {guidance && <div className="guidance-banner">{guidance}</div>}
      {orderedKinds.map((kind) => (
        <div key={kind} className="action-group">
          <div className="action-group-label">
            {KIND_LABELS[kind] ?? kind}
          </div>
          <div className="action-buttons">
            {groups.get(kind)!.map((a) => {
              const role = roleOf(a);
              const btn = (
                <button
                  key={a.id}
                  className="action-btn"
                  disabled={disabled}
                  onClick={() => {
                    onHighlight(null);
                    onPreview?.(null);
                    onAction(a.id);
                  }}
                  onMouseEnter={() => {
                    onHighlight(highlightFor(a, catalog));
                    if (!disabled) onPreview?.(a);
                  }}
                  onFocus={() => {
                    onHighlight(highlightFor(a, catalog));
                    if (!disabled) onPreview?.(a);
                  }}
                  onMouseLeave={() => {
                    onHighlight(null);
                    onPreview?.(null);
                  }}
                  onBlur={() => {
                    onHighlight(null);
                    onPreview?.(null);
                  }}
                >
                  {a.label}
                </button>
              );
              if (role !== null && view) {
                const ri = roleInfo(role);
                return (
                  <InfoTooltip
                    key={a.id}
                    content={
                      <RoleTooltipBody
                        name={ri.name}
                        description={ri.description}
                        hints={roleHints(role, view)}
                        placardDoubloons={placardDoubloons(role, view)}
                      />
                    }
                  >
                    {btn}
                  </InfoTooltip>
                );
              }
              return btn;
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
