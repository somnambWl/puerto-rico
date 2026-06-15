/**
 * roleHints.ts — dynamic, quantitative hints for a role tooltip.
 *
 * The catalog supplies a static `description` per role; here we add the bits
 * that depend on the live `view` (e.g. how many colonists are on the ship right
 * now, the privilege effect). These are display-only — the engine remains the
 * source of truth for legality. Role indices mirror enums.py :: Role.
 */

import type { GameView } from "./types";

const SETTLER = 0;
const MAYOR = 1;
const BUILDER = 2;
const CRAFTSMAN = 3;
const TRADER = 4;
const CAPTAIN = 5;
const PROSPECTOR = 6;

/** Compute the dynamic quantitative hint lines for `role` given `view`. */
export function roleHints(role: number, view: GameView): string[] {
  switch (role) {
    case MAYOR:
      return [
        `Colonists on the ship now: ${view.colonist_ship}`,
        "You take 1 from supply (privilege)",
      ];
    case BUILDER:
      return ["Build at −1 doubloon (privilege)"];
    case TRADER:
      return ["+1 doubloon on your sale (privilege)"];
    case CAPTAIN:
      return ["+1 VP on your first shipment"];
    case CRAFTSMAN:
      return ["+1 extra good you produced"];
    case SETTLER:
      return ["Chooser may take a quarry"];
    case PROSPECTOR:
      return ["+1 doubloon"];
    default:
      return [];
  }
}

/** Accumulated doubloons sitting on `role`'s placard (0 if none / not found). */
export function placardDoubloons(role: number, view: GameView): number {
  const p = view.placards.find((pl) => pl.role === role);
  return p ? p.doubloons : 0;
}
