/**
 * Board — the shared table state rendered from `view`.
 *
 * Role placards (with accumulated doubloons; available roles highlighted during
 * role selection), the colonist ship, cargo ships, the trading house, supplies
 * (colonists + VP chips remaining), the face-up plantation row (clickable), and
 * the buildings-available shelf (from buildings_supply).
 *
 * `highlight` is a best-effort signal from a hovered action (ActionPrompt) used
 * to outline the referenced element.
 */

import type { GameView, Highlight } from "../types";
import {
  BUILDINGS,
  GOOD_COLORS,
  GOOD_NAMES,
  PHASE_NAMES,
  ROLE_NAMES,
  TILE_COLORS,
  TILE_NAMES,
} from "../types";

interface BoardProps {
  view: GameView;
  highlight?: Highlight;
  onPlantationClick?: (index: number) => void;
}

const PHASE_ROLE_SELECTION = 0;

export function Board({ view, highlight, onPlantationClick }: BoardProps) {
  const roleSelection = view.phase === PHASE_ROLE_SELECTION;

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
                  (hl ? " hl" : "")
                }
              >
                <div className="placard-name">{ROLE_NAMES[p.role] ?? "?"}</div>
                <div className="placard-doubloons">
                  {p.doubloons > 0 ? `$${p.doubloons}` : " "}
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
              <div key={i} className={"ship cargo-ship" + (hl ? " hl" : "")}>
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
            {view.trading_house.map((g, i) => (
              <span
                key={i}
                className="good-chip"
                style={{ background: GOOD_COLORS[g] }}
                title={GOOD_NAMES[g]}
              >
                {GOOD_NAMES[g]}
              </span>
            ))}
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
                className={"plantation-tile" + (hl ? " hl" : "")}
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

      {/* Buildings shelf */}
      <section className="board-section">
        <h3>Buildings available</h3>
        <div className="building-shelf">
          {Object.entries(view.buildings_supply)
            .map(([id, n]) => [Number(id), n] as [number, number])
            .filter(([, n]) => n > 0)
            .sort((a, b) => a[0] - b[0])
            .map(([id, n]) => {
              const meta = BUILDINGS[id];
              const hl =
                highlight &&
                highlight.kind === "building" &&
                highlight.buildingId === id;
              return (
                <div
                  key={id}
                  className={
                    "shelf-building" +
                    (meta?.large ? " shelf-large" : "") +
                    (hl ? " hl" : "")
                  }
                  title={meta?.name}
                >
                  <span className="shelf-name">{meta?.name ?? `#${id}`}</span>
                  <span className="shelf-meta">
                    ${meta?.cost} · {meta?.vp}vp · x{n}
                  </span>
                </div>
              );
            })}
        </div>
      </section>
    </div>
  );
}
