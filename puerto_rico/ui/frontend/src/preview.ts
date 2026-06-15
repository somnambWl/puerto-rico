/**
 * preview.ts — diff a preview StateMsg against the current StateMsg.
 *
 * The backend's POST /games/{id}/preview returns a hypothetical state (the real
 * game untouched, no AI run). We compute the human-perspective deltas here so
 * the player can weigh an option before committing: doubloons, goods, VP,
 * island, city, role taken, and a few notable shared-board changes.
 *
 * The diff is general — it compares the two `view`s field by field — so it works
 * for any action without hardcoding per-action logic. It also returns a best-
 * effort `Highlight` (ghost) for the board element that changed.
 */

import type { GameView, Highlight, StateMsg } from "./types";
import { GOOD_NAMES, LARGE_CONT, ROLE_NAMES, TILE_NAMES } from "./types";
import type { CatalogBuilding } from "./types";

export interface DiffLine {
  /** Short label, e.g. "Doubloons". */
  label: string;
  /** Formatted change, e.g. "6 → 0" or "+3 Corn". */
  change: string;
}

export interface PreviewDiff {
  lines: DiffLine[];
  /** Ghost highlight for the changed board element (best effort). */
  highlight: Highlight;
}

function countCity(view: GameView, seat: number): Map<number, number> {
  const m = new Map<number, number>();
  for (const slot of view.players[seat].city) {
    if (slot.building === null || slot.building === LARGE_CONT) continue;
    m.set(slot.building, (m.get(slot.building) ?? 0) + 1);
  }
  return m;
}

function countIsland(view: GameView, seat: number): Map<number, number> {
  const m = new Map<number, number>();
  for (const slot of view.players[seat].island) {
    if (slot.tile === 0) continue;
    m.set(slot.tile, (m.get(slot.tile) ?? 0) + 1);
  }
  return m;
}

/**
 * Compute the human-perspective diff between `before` and `after`.
 * `buildingInfo` resolves a building id to its catalog entry (for nice names).
 */
export function computePreviewDiff(
  before: StateMsg,
  after: StateMsg,
  humanSeat: number,
  buildingInfo: (id: number) => CatalogBuilding | null,
): PreviewDiff {
  const b = before.view;
  const a = after.view;
  const lines: DiffLine[] = [];
  let highlight: Highlight = null;

  const bp = b.players[humanSeat];
  const ap = a.players[humanSeat];

  // Doubloons.
  if (bp.doubloons !== ap.doubloons) {
    lines.push({
      label: "Doubloons",
      change: `${bp.doubloons} → ${ap.doubloons}`,
    });
  }

  // VP chips (human only — never null for the human seat).
  if (bp.vp_chips !== null && ap.vp_chips !== null && bp.vp_chips !== ap.vp_chips) {
    lines.push({ label: "VP", change: `${bp.vp_chips} → ${ap.vp_chips}` });
  }

  // Goods (per kind).
  for (let g = 0; g < ap.goods.length; g++) {
    const d = (ap.goods[g] ?? 0) - (bp.goods[g] ?? 0);
    if (d !== 0) {
      lines.push({
        label: "Goods",
        change: `${d > 0 ? "+" : ""}${d} ${GOOD_NAMES[g] ?? `good ${g}`}`,
      });
    }
  }

  // Buildings gained.
  const beforeCity = countCity(b, humanSeat);
  const afterCity = countCity(a, humanSeat);
  for (const [id, n] of afterCity) {
    const gained = n - (beforeCity.get(id) ?? 0);
    if (gained > 0) {
      const name = buildingInfo(id)?.name ?? `building ${id}`;
      lines.push({ label: "Build", change: name });
      highlight = { kind: "building", buildingId: id, ghost: true };
    }
  }

  // Plantations / quarries gained on the island.
  const beforeIsland = countIsland(b, humanSeat);
  const afterIsland = countIsland(a, humanSeat);
  for (const [tile, n] of afterIsland) {
    const gained = n - (beforeIsland.get(tile) ?? 0);
    if (gained > 0) {
      lines.push({
        label: "Settle",
        change: `+${gained} ${TILE_NAMES[tile] ?? `tile ${tile}`}`,
      });
    }
  }

  // Stored colonists.
  if (bp.stored_colonists !== ap.stored_colonists) {
    lines.push({
      label: "Colonists (San Juan)",
      change: `${bp.stored_colonists} → ${ap.stored_colonists}`,
    });
  }

  // Role taken (compare placards taken_by for the human seat).
  const beforeRoles = new Set(
    b.placards.filter((p) => p.taken_by === humanSeat).map((p) => p.role),
  );
  for (const p of a.placards) {
    if (p.taken_by === humanSeat && !beforeRoles.has(p.role)) {
      lines.push({
        label: "Role taken",
        change: ROLE_NAMES[p.role] ?? `role ${p.role}`,
      });
      if (!highlight) highlight = { kind: "role", role: p.role, ghost: true };
    }
  }

  // Notable shared change: trading house size.
  if (b.trading_house.length !== a.trading_house.length) {
    const d = a.trading_house.length - b.trading_house.length;
    lines.push({
      label: "Trading house",
      change: `${d > 0 ? "+" : ""}${d} good${Math.abs(d) === 1 ? "" : "s"}`,
    });
  }

  if (lines.length === 0) {
    lines.push({ label: "No visible change", change: "—" });
  }

  return { lines, highlight };
}
