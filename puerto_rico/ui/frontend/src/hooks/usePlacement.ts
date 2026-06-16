/**
 * usePlacement — the human's Mayor colonist-placement arrangement model.
 *
 * The engine lifts ALL of a player's colonists into San Juan at the start of
 * their Mayor turn and takes them one PLACE_COLONIST at a time. This hook holds
 * the human's PENDING arrangement (which board circles they have assigned a
 * colonist to) as a single source of truth shared by two views:
 *
 *   - PlayerBoard — the actual placement SURFACE: each island/city slot is a
 *     drop / click target, and assigned circles show a colonist dot.
 *   - PlacementEditor — a compact control bar (San Juan source + counts +
 *     Place all / Clear / Confirm).
 *
 * The arrangement is SEEDED from the human's PREVIOUS (pre-lift) board, so the
 * colonists appear where they were left. "Confirm" realizes the arrangement as
 * ONE batch of action ids (a PLACE_COLONIST per assigned circle, then a final
 * store) for a single-round-trip submit.
 *
 * Positions are cosmetic to the engine, but WHICH building / plantation a
 * colonist lands on matters — each circle maps to a real slot target via
 * findAction's structured colonist_target → action id mapping.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { useBuildingInfo } from "../catalog";
import { findAction } from "../findAction";
import type { LegalAction, PlayerView } from "../types";
import { LARGE_CONT } from "../types";

/** One colonist seat in the arrangement (a single circle within a slot). */
export interface PlacementCircle {
  /** "city" building slot or "island" plantation/quarry slot. */
  kind: "city" | "island";
  /** Engine slot index within the city or island. */
  slotIndex: number;
  /** Seat number within the slot (0 for islands; 0..cap-1 for buildings). */
  seat: number;
  /** Production chain priority for "Place all" (lower fills first). */
  fillRank: number;
}

/** Stable key for a circle (kind:slotIndex:seat). */
export const circleKey = (c: {
  kind: string;
  slotIndex: number;
  seat: number;
}): string => `${c.kind}:${c.slotIndex}:${c.seat}`;

export interface PlacementModel {
  /** Total colonists available this turn (== lifted total, all in San Juan). */
  total: number;
  /** How many circles currently hold a colonist in the pending arrangement. */
  placedCount: number;
  /** Colonists still unplaced (sitting in San Juan). */
  sanJuan: number;
  /** Empty circles still available across the board. */
  openCount: number;
  /** Whether a given board slot's seat is assigned a colonist (pending). */
  isFilled: (kind: "city" | "island", slotIndex: number, seat: number) => boolean;
  /** Number of pending colonists assigned to a city slot (0..capacity). */
  cityFilledCount: (slotIndex: number) => number;
  /** Place a colonist into the first free seat of a slot (no-op if San Juan empty
   *  or the slot is full). */
  placeOn: (kind: "city" | "island", slotIndex: number) => void;
  /** Remove one pending colonist from a slot back to San Juan. */
  removeFrom: (kind: "city" | "island", slotIndex: number) => void;
  /** Fill every empty circle in chain-priority order until colonists run out. */
  placeAll: () => void;
  /** Return every pending colonist to San Juan. */
  clearAll: () => void;
  /** Realize the pending arrangement as an ordered batch of action ids. */
  buildBatch: () => number[];
}

/**
 * Build the placement model for the human's current Mayor turn.
 *
 * @param playerView    live player view (authoritative slot layout)
 * @param prevPlayerView pre-lift player view (seed: colonists where they were)
 * @param legalActions  PLACE_COLONIST legal actions (target → id mapping)
 * @param total         colonists available this turn (lifted total)
 */
export function usePlacement(
  playerView: PlayerView | null,
  prevPlayerView: PlayerView | null,
  legalActions: LegalAction[],
  total: number,
): PlacementModel {
  const buildingInfo = useBuildingInfo();

  // Enumerate every colonist circle the board offers (from the LIVE layout).
  const circles = useMemo<PlacementCircle[]>(() => {
    const out: PlacementCircle[] = [];
    if (!playerView) return out;
    playerView.city.forEach((slot, slotIndex) => {
      if (slot.building === null || slot.building === LARGE_CONT) return;
      const meta = buildingInfo(slot.building);
      const cap = meta?.capacity ?? 1;
      // Production buildings fill first (rank 0); other buildings next (rank 1);
      // plantations/quarries last (rank 2) so chains complete first.
      const rank = meta?.is_production ? 0 : 1;
      for (let seat = 0; seat < cap; seat++) {
        out.push({ kind: "city", slotIndex, seat, fillRank: rank });
      }
    });
    playerView.island.forEach((slot, slotIndex) => {
      if (slot.tile === 0) return; // empty island slot: no circle
      out.push({ kind: "island", slotIndex, seat: 0, fillRank: 2 });
    });
    return out;
  }, [playerView, buildingInfo]);

  // Seed: which circles were filled in the PREVIOUS (pre-lift) arrangement.
  const seedFilled = useMemo<Set<string>>(() => {
    const filled = new Set<string>();
    if (!prevPlayerView) return filled;
    let placed = 0;
    prevPlayerView.city.forEach((slot, slotIndex) => {
      for (let seat = 0; seat < slot.colonists; seat++) {
        filled.add(circleKey({ kind: "city", slotIndex, seat }));
        placed++;
      }
    });
    prevPlayerView.island.forEach((slot, slotIndex) => {
      if (slot.colonist) {
        filled.add(circleKey({ kind: "island", slotIndex, seat: 0 }));
        placed++;
      }
    });
    // Defensive: never seed more colonists than we have this turn.
    if (placed > total) {
      const arr = [...filled];
      return new Set(arr.slice(0, total));
    }
    return filled;
  }, [prevPlayerView, total]);

  const [filled, setFilled] = useState<Set<string>>(seedFilled);
  // Re-seed whenever a new placement turn begins (seed identity changes).
  useEffect(() => {
    setFilled(new Set(seedFilled));
  }, [seedFilled]);

  const validKeys = useMemo(
    () => new Set(circles.map((c) => circleKey(c))),
    [circles],
  );
  // Only keep filled markers that still correspond to a real circle.
  const filledValid = useMemo(() => {
    const s = new Set<string>();
    for (const k of filled) if (validKeys.has(k)) s.add(k);
    return s;
  }, [filled, validKeys]);

  const placedCount = filledValid.size;
  const sanJuan = Math.max(0, total - placedCount);
  const openCount = circles.length - placedCount;

  const isFilled = useCallback(
    (kind: "city" | "island", slotIndex: number, seat: number) =>
      filledValid.has(circleKey({ kind, slotIndex, seat })),
    [filledValid],
  );

  const cityFilledCount = useCallback(
    (slotIndex: number) => {
      let n = 0;
      for (const c of circles) {
        if (c.kind !== "city" || c.slotIndex !== slotIndex) continue;
        if (filledValid.has(circleKey(c))) n++;
      }
      return n;
    },
    [circles, filledValid],
  );

  // Place into the first free seat of a slot (respects per-slot capacity and the
  // global San Juan count).
  const placeOn = useCallback(
    (kind: "city" | "island", slotIndex: number) => {
      setFilled((prev) => {
        const validFilled = [...prev].filter((k) => validKeys.has(k)).length;
        if (validFilled >= total) return prev; // none left in San Juan
        const seats = circles.filter(
          (c) => c.kind === kind && c.slotIndex === slotIndex,
        );
        const free = seats.find((c) => !prev.has(circleKey(c)));
        if (!free) return prev; // slot already full
        const next = new Set(prev);
        next.add(circleKey(free));
        return next;
      });
    },
    [circles, validKeys, total],
  );

  // Remove the highest-seat pending colonist from a slot (LIFO within the slot).
  const removeFrom = useCallback(
    (kind: "city" | "island", slotIndex: number) => {
      setFilled((prev) => {
        const seats = circles
          .filter((c) => c.kind === kind && c.slotIndex === slotIndex)
          .filter((c) => prev.has(circleKey(c)));
        if (seats.length === 0) return prev;
        const last = seats[seats.length - 1];
        const next = new Set(prev);
        next.delete(circleKey(last));
        return next;
      });
    },
    [circles],
  );

  const placeAll = useCallback(() => {
    const order = [...circles].sort((a, b) => a.fillRank - b.fillRank);
    setFilled((prev) => {
      const next = new Set<string>();
      for (const c of circles) {
        const k = circleKey(c);
        if (prev.has(k) && validKeys.has(k)) next.add(k);
      }
      for (const c of order) {
        if (next.size >= total) break;
        next.add(circleKey(c));
      }
      return next;
    });
  }, [circles, validKeys, total]);

  const clearAll = useCallback(() => setFilled(new Set()), []);

  // Realize the arrangement: one PLACE_COLONIST per filled circle (skipping any
  // whose target is not currently legal), then a final store.
  const buildBatch = useCallback((): number[] => {
    const ids: number[] = [];
    for (const c of circles) {
      if (!filledValid.has(circleKey(c))) continue;
      const id = findAction(legalActions, {
        type: "colonist",
        kind: c.kind,
        index: c.slotIndex,
      });
      if (id != null) ids.push(id);
    }
    const storeId = findAction(legalActions, {
      type: "colonist",
      kind: "store",
    });
    if (storeId != null) ids.push(storeId);
    return ids;
  }, [circles, filledValid, legalActions]);

  return {
    total,
    placedCount,
    sanJuan,
    openCount,
    isFilled,
    cityFilledCount,
    placeOn,
    removeFrom,
    placeAll,
    clearAll,
    buildBatch,
  };
}
