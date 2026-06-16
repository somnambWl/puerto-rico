/**
 * Board — the shared table state rendered from `view`.
 *
 * Role placards (with accumulated doubloons; available roles highlighted during
 * role selection), the colonist ship, cargo ships, the trading house (a narrow
 * vertical stack of good chips with each good's base sell value + a stacked
 * base-value legend), supplies, the face-up plantation
 * row, and the buildings-available shelf grouped into VP rows (deluxe 1897
 * layout). Buildings (shelf + occupied city slots elsewhere) carry hover
 * tooltips so players don't memorize effects.
 *
 * `highlight` is a best-effort signal from a hovered action (ActionPrompt) used
 * to outline the referenced element; a `ghost` highlight (from action preview)
 * renders dashed.
 */

import { useMemo } from "react";

import { useBuildingInfo, useGoodInfo, useRoleInfo } from "../catalog";
import { findAction } from "../findAction";
import { roleHints } from "../roleHints";
import type {
  BuildingId,
  GameView,
  Highlight,
  LegalAction,
} from "../types";
import {
  buildingColor,
  GOOD_COLORS,
  GOOD_NAMES,
  PHASE_NAMES,
  ROLE_NAMES,
  TILE_COLORS,
  TILE_NAMES,
} from "../types";
import {
  BuildingTooltipBody,
  InfoTooltip,
  RoleTooltipBody,
} from "./Tooltip";

interface BoardProps {
  view: GameView;
  highlight?: Highlight;
  governorName?: string;
  toMoveName?: string;
  /** Hover a shelf building to highlight every copy across player boards. */
  onBuildingHover?: (id: BuildingId | null) => void;
  /** Legal actions for the human's current turn (empty otherwise). When a board
   * element matches a legal action it becomes clickable. */
  legalActions?: LegalAction[];
  /** Take the action with this id (click-to-act). No-op if undefined. */
  onBoardAction?: (id: number) => void;
  /** Preview-on-hover for a board element's matching action (null = clear). */
  onBoardHover?: (action: LegalAction | null) => void;
}

const PHASE_ROLE_SELECTION = 0;

function hlClass(
  active: boolean | null | undefined,
  ghost: boolean | undefined,
): string {
  if (!active) return "";
  return ghost ? " hl hl-ghost" : " hl";
}

export function Board({
  view,
  highlight,
  governorName,
  toMoveName,
  onBuildingHover,
  legalActions = [],
  onBoardAction,
  onBoardHover,
}: BoardProps) {
  const roleSelection = view.phase === PHASE_ROLE_SELECTION;
  const buildingInfo = useBuildingInfo();
  const goodInfo = useGoodInfo();
  const roleInfo = useRoleInfo();

  // Resolve a board element to its matching legal action id (or null = inert).
  const actionFor = (target: Parameters<typeof findAction>[1]): number | null =>
    findAction(legalActions, target);
  const legalById = (id: number | null): LegalAction | null =>
    id == null ? null : legalActions.find((a) => a.id === id) ?? null;
  const takeBoardAction = (id: number | null) => {
    if (id != null && onBoardAction) onBoardAction(id);
  };

  // Group ALL buildings by VP, sorted by cost ascending within a row. Sold-out
  // buildings (n == 0) are kept in place (rendered faded) rather than removed.
  const vpRows = useMemo(() => {
    const rows = new Map<number, { id: number; n: number; cost: number; large: boolean }[]>();
    for (const [idStr, n] of Object.entries(view.buildings_supply)) {
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
        <span className="muted">
          Governor: {governorName ?? `P${view.governor}`}
        </span>
        <span className="board-tomove">
          To move: {toMoveName ?? `P${view.current_player}`}
        </span>
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
            const ri = roleInfo(p.role);
            const roleActionId = actionFor({ type: "role", role: p.role });
            const clickable = roleActionId != null;
            return (
              <InfoTooltip
                key={i}
                content={
                  <RoleTooltipBody
                    name={ri.name}
                    description={ri.description}
                    hints={roleHints(p.role, view)}
                    placardDoubloons={p.doubloons}
                  />
                }
              >
                <div
                  className={
                    "placard" +
                    (roleSelection && available ? " placard-available" : "") +
                    (p.taken_by !== null ? " placard-taken" : "") +
                    (clickable ? " board-clickable" : "") +
                    hlClass(hl, highlight?.ghost)
                  }
                  onClick={
                    clickable ? () => takeBoardAction(roleActionId) : undefined
                  }
                  onMouseEnter={
                    clickable
                      ? () => onBoardHover?.(legalById(roleActionId))
                      : undefined
                  }
                  onMouseLeave={clickable ? () => onBoardHover?.(null) : undefined}
                >
                  <div className="placard-name">{ROLE_NAMES[p.role] ?? "?"}</div>
                  <div className="placard-doubloons">
                    {p.doubloons > 0 ? `$${p.doubloons}` : " "}
                  </div>
                  {p.taken_by !== null && (
                    <div className="placard-by">P{p.taken_by}</div>
                  )}
                </div>
              </InfoTooltip>
            );
          })}
        </div>
      </section>

      {/* Ships — compact horizontal row (colonist + cargo ships) */}
      <section className="board-section">
        <h3>Ships</h3>
        <div className="ship-row">
          <div className="ship ship-card colonist-ship">
            <span className="ship-label">Colonist</span>
            <span className="ship-fill">{view.colonist_ship}</span>
          </div>
          {view.cargo_ships.map((s, i) => {
            // index < 0 is a generic "all cargo ships" highlight (LOAD labels
            // carry only a quantity, no ship id), otherwise a specific ship.
            const hl =
              highlight &&
              highlight.kind === "ship" &&
              (highlight.index < 0 || highlight.index === i);
            const color = s.good !== null ? GOOD_COLORS[s.good] : "#444";
            // Auto-send only when exactly one good can load onto this ship.
            const loadId = actionFor({ type: "load", ship: i });
            const clickable = loadId != null;
            return (
              <div
                key={i}
                className={
                  "ship ship-card cargo-ship" +
                  (clickable ? " board-clickable" : "") +
                  hlClass(hl, highlight?.ghost)
                }
                onClick={clickable ? () => takeBoardAction(loadId) : undefined}
                onMouseEnter={
                  clickable ? () => onBoardHover?.(legalById(loadId)) : undefined
                }
                onMouseLeave={clickable ? () => onBoardHover?.(null) : undefined}
              >
                <span className="ship-label">
                  Ship {i + 1} <span className="ship-cap">cap {s.capacity}</span>
                </span>
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
        </div>
      </section>

      {/* Trading house — compact: chips and base-value legend in a row */}
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

      {/* Face-up plantation row (+ quarry take) */}
      <section className="board-section">
        <h3>Face-up plantations</h3>
        <div className="plantation-row">
          {(() => {
            // Settler quarry take is a single action (TileType.QUARRY == 1),
            // not tied to a face-up tile, so render a dedicated quarry chip.
            const quarryId = actionFor({ type: "tile", tile: 1 });
            if (quarryId == null) return null;
            return (
              <button
                key="quarry"
                className="plantation-tile board-clickable"
                style={{ background: TILE_COLORS[1] }}
                onClick={() => takeBoardAction(quarryId)}
                onMouseEnter={() => onBoardHover?.(legalById(quarryId))}
                onMouseLeave={() => onBoardHover?.(null)}
                title={TILE_NAMES[1]}
              >
                {TILE_NAMES[1]}
              </button>
            );
          })()}
          {view.plantation_faceup.map((t, i) => {
            const hl =
              highlight &&
              highlight.kind === "plantation" &&
              highlight.index === i;
            // A face-up tile of kind K maps to TAKE_TILE(tile=K). TileType is
            // the same enum the engine uses (face-up values are TileType).
            const tileId = actionFor({ type: "tile", tile: t });
            const clickable = tileId != null;
            return (
              <button
                key={i}
                className={
                  "plantation-tile" +
                  (clickable ? " board-clickable" : "") +
                  hlClass(hl, highlight?.ghost)
                }
                style={{ background: TILE_COLORS[t] }}
                onClick={clickable ? () => takeBoardAction(tileId) : undefined}
                onMouseEnter={
                  clickable ? () => onBoardHover?.(legalById(tileId)) : undefined
                }
                onMouseLeave={clickable ? () => onBoardHover?.(null) : undefined}
                disabled={!clickable}
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
                  const max = meta?.supply ?? n;
                  const soldOut = n <= 0;
                  const hl =
                    highlight &&
                    highlight.kind === "building" &&
                    highlight.buildingId === id;
                  const buildId = actionFor({ type: "build", building: id });
                  const clickable = buildId != null && !soldOut;
                  const accent = buildingColor(meta?.produces, large);
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
                            available={n}
                            max={max}
                            isLarge={meta.is_large}
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
                          (soldOut ? " shelf-soldout" : "") +
                          (clickable ? " board-clickable" : "") +
                          hlClass(hl, highlight?.ghost)
                        }
                        style={{ borderLeft: `5px solid ${accent}` }}
                        onClick={
                          clickable
                            ? () => takeBoardAction(buildId)
                            : undefined
                        }
                        onMouseEnter={() => {
                          onBuildingHover?.(id);
                          if (clickable) onBoardHover?.(legalById(buildId));
                        }}
                        onMouseLeave={() => {
                          onBuildingHover?.(null);
                          if (clickable) onBoardHover?.(null);
                        }}
                      >
                        <span className="shelf-name">
                          {meta?.name ?? `#${id}`}
                        </span>
                        <span className="shelf-meta">
                          ${meta?.cost} · {vp} VP · {n}/{max} left
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

/**
 * SuppliesStrip — the persistent "game clock" shown in the header.
 *
 * Compact, always-visible view of the end-game triggers (VP chips left +
 * colonists left) plus quarry / plantation-deck counts and the per-good supply
 * dots. Lives in the pinned header so the player always sees how close the game
 * is to ending. Updates live with `view`.
 */
export function SuppliesStrip({ view }: { view: GameView }) {
  return (
    <div className="supplies-strip" title="Game supplies (end-game triggers)">
      <span className="ss-item" title="Victory-point chips remaining (end-game trigger)">
        <span className="ss-num">{view.vp_chips_remaining}</span>
        <span className="ss-label">VP chips</span>
      </span>
      <span className="ss-item" title="Colonists remaining in the supply (end-game trigger)">
        <span className="ss-num">{view.colonist_supply}</span>
        <span className="ss-label">colonists</span>
      </span>
      <span className="ss-item" title="Quarries remaining">
        <span className="ss-num">{view.quarry_supply}</span>
        <span className="ss-label">quarries</span>
      </span>
      <span className="ss-item" title="Face-down plantation deck">
        <span className="ss-num">{view.plantation_facedown_count}</span>
        <span className="ss-label">deck</span>
      </span>
      <span className="ss-goods">
        {view.goods_supply.map((n, g) => (
          <span key={g} className="ss-good" title={`${GOOD_NAMES[g]} supply`}>
            <span className="good-dot" style={{ background: GOOD_COLORS[g] }} />
            {n}
          </span>
        ))}
      </span>
    </div>
  );
}
