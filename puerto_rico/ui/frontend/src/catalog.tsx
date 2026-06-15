/**
 * Catalog context — static building + good reference data from GET /catalog.
 *
 * Fetched once on app start (App.tsx) and provided here so Board / PlayerBoard /
 * ActionPrompt can render names, costs, VP, capacity, descriptions and good
 * base values without re-deriving any rules. When the fetch fails the context is
 * null and consumers fall back to the hardcoded BUILDINGS / GOOD_NAMES maps in
 * types.ts via the helper hooks below.
 */

import { createContext, useContext, useMemo } from "react";

import { BUILDINGS, GOOD_NAMES } from "./types";
import type { Catalog, CatalogBuilding, CatalogGood } from "./types";

const CatalogContext = createContext<Catalog | null>(null);

export function CatalogProvider({
  catalog,
  children,
}: {
  catalog: Catalog | null;
  children: React.ReactNode;
}) {
  return (
    <CatalogContext.Provider value={catalog}>
      {children}
    </CatalogContext.Provider>
  );
}

export function useCatalog(): Catalog | null {
  return useContext(CatalogContext);
}

/** Building meta lookup keyed by id, with a hardcoded fallback. */
export function useBuildingInfo(): (id: number) => CatalogBuilding | null {
  const catalog = useContext(CatalogContext);
  return useMemo(() => {
    const byId = new Map<number, CatalogBuilding>();
    if (catalog) {
      for (const b of catalog.buildings) byId.set(b.id, b);
    }
    return (id: number): CatalogBuilding | null => {
      const hit = byId.get(id);
      if (hit) return hit;
      const fb = BUILDINGS[id];
      if (!fb) return null;
      // Synthesize a minimal entry from the fallback map.
      return {
        id,
        name: fb.name,
        cost: fb.cost,
        column: 0,
        vp: fb.vp,
        capacity: fb.large ? 0 : 1,
        is_large: fb.large,
        is_production: false,
        produces: null,
        kind: fb.large ? "large" : "small",
        description: "",
      };
    };
  }, [catalog]);
}

/** Good base-value lookup keyed by Good index, with a sensible fallback. */
export function useGoodInfo(): (good: number) => CatalogGood {
  const catalog = useContext(CatalogContext);
  return useMemo(() => {
    const byGood = new Map<number, CatalogGood>();
    if (catalog) {
      for (const g of catalog.goods) byGood.set(g.good, g);
    }
    // Base sell values corn 0 .. coffee 4 (matches backend catalog.py).
    const FALLBACK: Record<number, number> = { 0: 0, 1: 1, 2: 2, 3: 3, 4: 4 };
    return (good: number): CatalogGood =>
      byGood.get(good) ?? {
        good,
        name: GOOD_NAMES[good] ?? `good ${good}`,
        base_value: FALLBACK[good] ?? 0,
      };
  }, [catalog]);
}
