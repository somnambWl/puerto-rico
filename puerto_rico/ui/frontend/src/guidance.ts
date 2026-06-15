/**
 * guidance — plain-language instruction for the human's current decision.
 *
 * New players don't know what each role's action expects. Given the current
 * view + the legal actions on offer, we return one short, friendly sentence
 * explaining what to do. The text is derived from the kinds of legal actions
 * present (role/tile/build/colonist/sell/ship/choose/pass) and falls back to
 * the phase name, so it stays accurate even if a phase exposes an unusual mix.
 */

import type { GameView, LegalAction } from "./types";
import { PHASE_NAMES } from "./types";

/**
 * Returns a one-sentence instruction for the human, or null when there is
 * nothing actionable (no legal actions). Caller only renders this on the
 * human's turn.
 */
export function guidanceFor(
  view: GameView,
  legalActions: LegalAction[],
): string | null {
  if (legalActions.length === 0) return null;

  const kinds = new Set(legalActions.map((a) => a.kind));
  const onlyPass = kinds.size === 1 && kinds.has("pass");

  if (kinds.has("role")) {
    return "Pick a role — hover any role to see what it does and the bonus you'd get.";
  }
  if (kinds.has("tile")) {
    return "Choose a plantation (or quarry) to add to your island — click it on the board or a button below.";
  }
  if (kinds.has("colonist")) {
    return "Place your colonists — drag them onto buildings and plantations, then click Done to store the rest.";
  }
  if (kinds.has("build")) {
    return "Build one building — click it in the Buildings shelf (cost shown). Or pass.";
  }
  if (kinds.has("sell")) {
    return "Sell one good to the trading house, or pass.";
  }
  if (kinds.has("ship")) {
    return "Ship goods for victory points — click a cargo ship, or use your wharf. You must ship if able.";
  }
  if (kinds.has("choose")) {
    return "Pick the extra good you want to take, or pass.";
  }
  if (onlyPass) {
    return "No move available here — click Pass to continue.";
  }

  // Fall back to the phase name so we always say *something* useful.
  const phaseName = PHASE_NAMES[view.phase] ?? "this";
  return `${phaseName}: choose one of the options below.`;
}
