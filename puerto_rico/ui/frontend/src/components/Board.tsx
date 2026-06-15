/**
 * Board — the shared table state rendered from `view`.
 *
 * Role placards (with accumulated doubloons; available roles highlighted during
 * role selection), the colonist ship, cargo ships, the trading house (with each
 * good's base sell value + a value legend), supplies, the face-up plantation
 * row, and the buildings-available shelf grouped into VP rows (deluxe 1897
 * layout). Buildings (shelf + occupied city slots elsewhere) carry hover
 * tooltips so players don't memorize effects.
 *
 * `highlight` is a best-effort signal from a hovered action (ActionPrompt) used
 * to outline the referenced element; a `ghost` highlight (from action preview)
 * renders dashed.
 */

import { useMemo } from "react";

import { useBuildingInfo, useGoodInfo } from "../catalog";
import type { GameView, Highlight } from "../types";
import {
  GOOD_COLORS,
  GOOD_NAMES,
  PHASE_NAMES,
  ROLE_NAMES,
  TILE_COLORS,
  TILE_NAMES,
} from "../types";
import { BuildingTooltipBody, InfoTooltip } from "./Tooltip";

interface BoardProps {
  view: GameView;
  highlight?: Highlight;
  onPlantationClick?: (index: number) => void;
}

const PHASE_ROLE_SELECTION = 0;

function hlClass(
  active: boolean | null | undefined,
  ghost: boolean | undefined,
): string {
  if (!active) return "";
  return ghost ? " hl hl-ghost" : " hl";
}

export function Board({ view, highlight, onPlantationClick }: BoardProps) {
  const roleSelection = view.phase === PHASE_ROLE_SELECTION;
  const buildingInfo = useBuildingInfo();
  const goodInfo = useGoodInfo();

  // Group the available buildings by VP, sorted by cost ascending within a row.
  const vpRows = useMemo(() => {
    const rows = new Map<number, { id: number; n: number; cost: number; large: boolean }[]>();
    for (const [idStr, n] of Object.entries(view.buildings_supply)) {
      if (n <= 0) continue;
      const id = Number(idStr);
      const meta = buildingInfo(id);
      const vp = meta?.vp ?? 0;
      const arr = rows.get(vp) ?? [];
      arr.push({ id, n, cost: meta?.cost ?? 0, large: meta?.is_large ?? false });
      rows.set(vp, arr);
    }
    for (const arr of rows.values()) arr.sort((a, b) => a.cost - b.cost);
    return [...rows.entries()].sort((a, b) => a[0] - b[0]);
  }, [view.buildings_supply, buildingInfo]);

  return (
    <div className="board">
      <div className="board-header">
        <span className="phase-tag">{PHASE_NAMES[view.phase] ?? "?"}</span>
        <span className="muted">governor: P{view.governor}</span>
        {view.end_triggered && <span className="end-flag">END TRIGGERED</span>}
      </div>

      {/* Role placards */}
      <section className="board-section">
        <h3>Roles</h3>
        <div className="placard-row">
          {view.placards.map((p, i) => {
            const available = p.taken_by === null;
            const hl =
              highlight && highlight.kind === "role" && highlight.role === p.role;
            return (
              <div
                key={i}
                className={
                  "placard" +
                  (roleSelection && available ? " placard-available" : "") +
                  (p.taken_by !== null ? " placard-taken" : "") +
                  hlClass(hl, highlight?.ghost)
                }
              >
                <div className="placard-name">{ROLE_NAMES[p.role] ?? "?"}</div>
                <div className="placard-doubloons">
                  {p.doubloons > 0 ? `$${p.doubloons}` : " "}
                </div>
                {p.taken_by !== null && (
                  <div className="placard-by">P{p.taken_by}</div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <div className="board-grid">
        {/* Ships */}
        <section className="board-section">
          <h3>Ships</h3>
          <div className="ship colonist-ship">
            <span className="ship-label">Colonist ship</span>
            <span className="ship-fill">{view.colonist_ship} colonists</span>
          </div>
          {view.cargo_ships.map((s, i) => {
            const hl =
              highlight && highlight.kind === "ship" && highlight.index === i;
            const color = s.good !== null ? GOOD_COLORS[s.good] : "#444";
            return (
              <div
                key={i}
                className={"ship cargo-ship" + hlClass(hl, highlight?.ghost)}
              >
                <span className="ship-label">Ship {i + 1}</span>
                <span className="ship-cap">cap {s.capacity}</span>
                <span className="ship-fill">
                  <span
                    className="good-dot"
                    style={{ background: color }}
                    title={s.good !== null ? GOOD_NAMES[s.good] : "empty"}
                  />
                  {s.count}/{s.capacity}{" "}
                  {s.good !== null ? GOOD_NAMES[s.good] : ""}
                </span>
              </div>
            );
          })}
        </section>

        {/* Trading house */}
        <section className="board-section">
          <h3>Trading house</h3>
          <div className="trading-house">
            {view.trading_house.length === 0 && (
              <span className="muted">empty</span>
            )}
            {view.trading_house.map((g, i) => {
              const gi = goodInfo(g);
              const hl =
                highlight && highlight.kind === "good" && highlight.good === g;
              return (
                <span
                  key={i}
                  className={"good-chip" + hlClass(hl, highlight?.ghost)}
                  style={{ background: GOOD_COLORS[g] }}
                  title={`${gi.name}: base ${gi.base_value}`}
                >
                  {gi.name} <strong>${gi.base_value}</strong>
                </span>
              );
            })}
          </div>
          {/* Always-visible base-value legend. */}
          <div className="goods-legend">
            <span className="goods-legend-label">base values:</span>
            {view.goods_supply.map((_, g) => {
              const gi = goodInfo(g);
              return (
                <span key={g} className="goods-legend-item" title={gi.name}>
                  <span
                    className="good-dot"
                    style={{ background: GOOD_COLORS[g] }}
                  />
                  {gi.name} ${gi.base_value}
                </span>
              );
            })}
          </div>
        </section>

        {/* Supplies */}
        <section className="board-section">
          <h3>Supplies</h3>
          <div className="supply-row">
            <div className="supply">
              <span className="supply-num">{view.colonist_supply}</span>
              <span className="supply-label">colonists left</span>
            </div>
            <div className="supply">
              <span className="supply-num">{view.vp_chips_remaining}</span>
              <span className="supply-label">VP chips left</span>
            </div>
            <div className="supply">
              <span className="supply-num">{view.quarry_supply}</span>
              <span className="supply-label">quarries</span>
            </div>
            <div className="supply">
              <span className="supply-num">
                {view.plantation_facedown_count}
              </span>
              <span className="supply-label">deck</span>
            </div>
          </div>
          <div className="goods-supply">
            {view.goods_supply.map((n, g) => (
              <span key={g} className="good-supply" title={GOOD_NAMES[g]}>
                <span
                  className="good-dot"
                  style={{ background: GOOD_COLORS[g] }}
                />
                {n}
              </span>
            ))}
          </div>
        </section>
      </div>

      {/* Face-up plantation row */}
      <section className="board-section">
        <h3>Face-up plantations</h3>
        <div className="plantation-row">
          {view.plantation_faceup.map((t, i) => {
            const hl =
              highlight &&
              highlight.kind === "plantation" &&
              highlight.index === i;
            return (
              <button
                key={i}
                className={"plantation-tile" + hlClass(hl, highlight?.ghost)}
                style={{ background: TILE_COLORS[t] }}
                onClick={() => onPlantationClick?.(i)}
                title={TILE_NAMES[t]}
              >
                {TILE_NAMES[t]}
              </button>
            );
          })}
          {view.plantation_faceup.length === 0 && (
            <span className="muted">none</span>
          )}
        </div>
      </section>

      {/* Buildings shelf, grouped into VP rows (deluxe layout) */}
      <section className="board-section">
        <h3>Buildings available</h3>
        <div className="building-shelf-rows">
          {vpRows.map(([vp, items]) => (
            <div key={vp} className="vp-row">
              <div className="vp-row-label">{vp} VP</div>
              <div className="vp-row-buildings">
                {items.map(({ id, n, large }) => {
                  const meta = buildingInfo(id);
                  const hl =
                    highlight &&
                    highlight.kind === "building" &&
                    highlight.buildingId === id;
                  return (
                    <InfoTooltip
                      key={id}
                      content={
                        meta ? (
                          <BuildingTooltipBody
                            name={meta.name}
                            cost={meta.cost}
                            vp={meta.vp}
                            capacity={meta.capacity}
                            description={meta.description}
                            produces={meta.produces}
                          />
                        ) : (
                          <div className="tt-title">building {id}</div>
                        )
                      }
                    >
                      <div
                        className={
                          "shelf-building" +
                          (large ? " shelf-large" : "") +
                          (meta?.is_production ? " shelf-production" : "") +
                          hlClass(hl, highlight?.ghost)
                        }
                      >
                        <span className="shelf-name">
                          {meta?.name ?? `#${id}`}
                        </span>
                        <span className="shelf-meta">
                          ${meta?.cost} · x{n}
                        </span>
                      </div>
                    </InfoTooltip>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
