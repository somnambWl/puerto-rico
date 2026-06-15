/**
 * Catalog context — static building + good reference data from GET /catalog.
 *
 * Fetched once on app start (App.tsx) and provided here so Board / PlayerBoard /
 * ActionPrompt can render names, costs, VP, capacity, descriptions and good
 * base values without re-deriving any rules. /catalog is the single source of
 * truth for building metadata: when the fetch fails the context is null,
 * `useBuildingInfo` returns null for every id, and consumers degrade to a
 * generic "building N" label. Good names/values still have a thin local
 * fallback (`useGoodInfo`) since those are tiny, stable engine enums.
 */

import { createContext, useContext, useMemo } from "react";

import { GOOD_NAMES, ROLE_NAMES } from "./types";
import type {
  Catalog,
  CatalogBuilding,
  CatalogGood,
  CatalogRole,
} from "./types";

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

/**
 * Building meta lookup keyed by id. Returns the catalog entry, or null when the
 * catalog is unavailable / the id is unknown. /catalog is authoritative — we do
 * NOT synthesize a fallback entry (a fabricated capacity/cost would be wrong);
 * callers render a generic placeholder when this returns null.
 */
export function useBuildingInfo(): (id: number) => CatalogBuilding | null {
  const catalog = useContext(CatalogContext);
  return useMemo(() => {
    const byId = new Map<number, CatalogBuilding>();
    if (catalog) {
      for (const b of catalog.buildings) byId.set(b.id, b);
    }
    return (id: number): CatalogBuilding | null => byId.get(id) ?? null;
  }, [catalog]);
}

/**
 * Role reference lookup keyed by Role index. Returns the catalog entry, or a
 * thin fallback (name only) when the catalog is unavailable / role unknown.
 */
export function useRoleInfo(): (role: number) => CatalogRole {
  const catalog = useContext(CatalogContext);
  return useMemo(() => {
    const byRole = new Map<number, CatalogRole>();
    if (catalog?.roles) {
      for (const r of catalog.roles) byRole.set(r.role, r);
    }
    return (role: number): CatalogRole =>
      byRole.get(role) ?? {
        role,
        name: ROLE_NAMES[role] ?? `role ${role}`,
        description: "",
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
