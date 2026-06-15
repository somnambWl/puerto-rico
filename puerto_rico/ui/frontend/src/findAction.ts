/**
 * findAction — map a clicked/dropped board element to a legal action id.
 *
 * The backend now decorates each LegalAction with structured target fields
 * (role/tile/building/good/ship/colonist_target). This module finds the legal
 * action whose target matches a board descriptor, so the UI can act by clicking
 * the thing itself rather than its button in the action list.
 *
 * Every lookup returns the matching action id or `null` (no legal action for
 * that target — the element is inert). Engine legality is never reimplemented:
 * we only ever return an id that is already in `legal_actions`.
 */

import type { LegalAction } from "./types";

/** A descriptor of the board element the player interacted with. */
export type BoardTarget =
  | { type: "role"; role: number }
  | { type: "tile"; tile: number }
  | { type: "build"; building: number }
  | { type: "sell"; good: number }
  | { type: "load"; good?: number; ship?: number }
  | { type: "colonist"; kind: "city" | "island" | "store"; index?: number };

/**
 * Find the legal action id matching `target`, or null if none is legal.
 *
 * For LOAD, an unspecified `good` matches any good targeting that ship — but
 * only when it is unambiguous (exactly one candidate); ambiguous cases return
 * null so the caller can fall back to the explicit action list.
 */
export function findAction(
  legalActions: LegalAction[],
  target: BoardTarget,
): number | null {
  switch (target.type) {
    case "role": {
      const a = legalActions.find(
        (x) => x.kind === "role" && x.role === target.role,
      );
      return a ? a.id : null;
    }
    case "tile": {
      const a = legalActions.find(
        (x) => x.kind === "tile" && x.tile === target.tile,
      );
      return a ? a.id : null;
    }
    case "build": {
      const a = legalActions.find(
        (x) => x.kind === "build" && x.building === target.building,
      );
      return a ? a.id : null;
    }
    case "sell": {
      const a = legalActions.find(
        (x) => x.kind === "sell" && x.good === target.good,
      );
      return a ? a.id : null;
    }
    case "load": {
      const cands = legalActions.filter((x) => {
        if (x.kind !== "ship") return false;
        // Only cargo-ship loads (have a `ship` index); skip wharf loads here.
        if (x.ship == null) return false;
        if (target.ship != null && x.ship !== target.ship) return false;
        if (target.good != null && x.good !== target.good) return false;
        return true;
      });
      // Only auto-send when unambiguous.
      return cands.length === 1 ? cands[0].id : null;
    }
    case "colonist": {
      const a = legalActions.find((x) => {
        const ct = x.colonist_target;
        if (x.kind !== "colonist" || !ct) return false;
        if (ct.kind !== target.kind) return false;
        if (target.kind === "store") return true;
        return ct.index === target.index;
      });
      return a ? a.id : null;
    }
    default:
      return null;
  }
}
