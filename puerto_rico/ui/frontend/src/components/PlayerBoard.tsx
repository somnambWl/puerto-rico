/**
 * PlayerBoard — one player's personal state.
 *
 * Island (12 slots, colonist dots), city (12 building slots; large buildings
 * span 2 slots; colonist dots per staffed slot), doubloons, goods inventory,
 * stored colonists, and VP (shown for the human, "?" for opponents).
 *
 * The human board renders large; opponent boards render compact.
 */

import { useBuildingInfo } from "../catalog";
import type { PlayerView } from "../types";
import {
  GOOD_COLORS,
  GOOD_NAMES,
  LARGE_CONT,
  TILE_COLORS,
  TILE_NAMES,
} from "../types";
import { BuildingTooltipBody, InfoTooltip } from "./Tooltip";

interface PlayerBoardProps {
  playerView: PlayerView;
  seat: number;
  isHuman: boolean;
  name: string;
  active?: boolean;
}

function ColonistDots({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="dots">
      {Array.from({ length: count }).map((_, i) => (
        <span key={i} className="dot" />
      ))}
    </span>
  );
}

export function PlayerBoard({
  playerView,
  seat,
  isHuman,
  name,
  active,
}: PlayerBoardProps) {
  const buildingInfo = useBuildingInfo();
  const cls =
    "player-board" +
    (isHuman ? " player-human" : " player-compact") +
    (active ? " player-active" : "");

  return (
    <div className={cls}>
      <div className="player-header">
        <span className="player-name">
          {name} <span className="muted">(P{seat})</span>
        </span>
        <span className="player-vp">
          VP: {isHuman || playerView.vp_chips !== null ? playerView.vp_chips : "?"}
        </span>
      </div>

      <div className="player-stats">
        <span className="stat">${playerView.doubloons}</span>
        <span className="stat">
          colonists in San Juan: {playerView.stored_colonists}
        </span>
      </div>

      {/* Goods inventory */}
      <div className="player-goods">
        {playerView.goods.map((n, g) => (
          <span key={g} className="good-inv" title={GOOD_NAMES[g]}>
            <span
              className="good-dot"
              style={{ background: GOOD_COLORS[g] }}
            />
            {n}
          </span>
        ))}
      </div>

      {/* Island */}
      <div className="player-zone">
        <div className="zone-label">Island</div>
        <div className="island-grid">
          {playerView.island.map((slot, i) => {
            const empty = slot.tile === 0;
            return (
              <div
                key={i}
                className={"island-slot" + (empty ? " slot-empty" : "")}
                style={empty ? undefined : { background: TILE_COLORS[slot.tile] }}
                title={TILE_NAMES[slot.tile]}
              >
                {!empty && (
                  <>
                    <span className="slot-text">{TILE_NAMES[slot.tile]}</span>
                    {slot.colonist && <ColonistDots count={1} />}
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* City */}
      <div className="player-zone">
        <div className="zone-label">City</div>
        <div className="city-grid">
          {playerView.city.map((slot, i) => {
            if (slot.building === LARGE_CONT) {
              // Continuation slot of a large building — rendered by its head.
              return null;
            }
            const empty = slot.building === null;
            const meta = empty ? null : buildingInfo(slot.building as number);
            const large = meta?.is_large ?? false;
            const name = meta?.name ?? "";
            const slotEl = (
              <div
                className={
                  "city-slot" +
                  (empty ? " slot-empty" : "") +
                  (large ? " city-large" : "")
                }
                title={empty ? "empty" : name}
              >
                {!empty && (
                  <>
                    <span className="slot-text">{name}</span>
                    <ColonistDots count={slot.colonists} />
                  </>
                )}
              </div>
            );
            if (empty || !meta) {
              return (
                <div key={i} className="city-slot-wrap">
                  {slotEl}
                </div>
              );
            }
            return (
              <InfoTooltip
                key={i}
                className="city-slot-wrap"
                content={
                  <BuildingTooltipBody
                    name={meta.name}
                    cost={meta.cost}
                    vp={meta.vp}
                    capacity={meta.capacity}
                    description={meta.description}
                    produces={meta.produces}
                  />
                }
              >
                {slotEl}
              </InfoTooltip>
            );
          })}
        </div>
      </div>
    </div>
  );
}
