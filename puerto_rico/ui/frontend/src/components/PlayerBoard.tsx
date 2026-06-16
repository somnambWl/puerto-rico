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
import type { PlacementModel } from "../hooks/usePlacement";
import type { BuildingId, PlayerView } from "../types";
import {
  buildingColor,
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
  /** True when this seat holds the governor placard. */
  isGovernor?: boolean;
  /** 1-based seat order number to show as a turn-order badge. */
  orderNumber?: number;
  /** Highlight every city slot holding this building type. */
  highlightBuilding?: BuildingId | null;
  /** Hover a city slot to highlight that building type everywhere. */
  onBuildingHover?: (id: BuildingId | null) => void;
  /**
   * The shared Mayor-placement arrangement. When present (the human's own Mayor
   * turn), this board IS the placement surface: island/city slots become drop /
   * click targets, pending colonist dots are read from the model, and drops /
   * clicks mutate the model (no per-action submit — Confirm batches it).
   */
  placement?: PlacementModel | null;
  /** True while a San Juan token is being dragged (for drop affordance). */
  placingDragActive?: boolean;
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
  isGovernor,
  orderNumber,
  highlightBuilding,
  onBuildingHover,
  placement = null,
  placingDragActive = false,
}: PlayerBoardProps) {
  const buildingInfo = useBuildingInfo();
  const cls =
    "player-board" +
    (isHuman ? " player-human" : " player-compact") +
    (active ? " player-active" : "") +
    (placement ? " player-placing" : "");

  // Mayor placement is live only on the human's own board when the shared
  // placement model is supplied.
  const placing = isHuman && placement != null;

  return (
    <div className={cls}>
      <div className="player-header">
        <span className="player-name">
          {orderNumber !== undefined && (
            <span className="player-order" title="Turn order">
              {orderNumber}
            </span>
          )}
          {name} <span className="muted">(P{seat})</span>
          {isGovernor && (
            <span className="governor-badge" title="Governor">
              👑 Governor
            </span>
          )}
          {active && <span className="tomove-badge">to move</span>}
        </span>
        <span className="player-vp">
          <span className="vp-chips" title="VP chips earned">
            {playerView.vp_chips ?? 0} chips
          </span>
          <span className="vp-total" title="Total VP if game ended now">
            {playerView.score} total
          </span>
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
            // During placement, a tiled island slot is interactive: show the
            // PENDING colonist from the shared model (not the lifted live state).
            const pendingHere =
              placing && !empty && placement!.isFilled("island", i, 0);
            const droppable = placing && !empty && !pendingHere;
            const onSlot = () => {
              if (!placing || empty) return;
              if (pendingHere) placement!.removeFrom("island", i);
              else placement!.placeOn("island", i);
            };
            return (
              <div
                key={i}
                className={
                  "island-slot" +
                  (empty ? " slot-empty" : "") +
                  (droppable ? " drop-target" : "") +
                  (droppable && placingDragActive ? " drop-active" : "")
                }
                style={empty ? undefined : { background: TILE_COLORS[slot.tile] }}
                title={
                  droppable
                    ? "Drop a colonist here"
                    : pendingHere
                      ? "Click to return this colonist to San Juan"
                      : TILE_NAMES[slot.tile]
                }
                onClick={placing && !empty ? onSlot : undefined}
                onDragOver={
                  droppable
                    ? (e) => {
                        e.preventDefault();
                        e.dataTransfer.dropEffect = "move";
                      }
                    : undefined
                }
                onDrop={
                  droppable
                    ? (e) => {
                        e.preventDefault();
                        placement!.placeOn("island", i);
                      }
                    : undefined
                }
              >
                {!empty && (
                  <>
                    <span className="slot-text">{TILE_NAMES[slot.tile]}</span>
                    {/* Placement: pending dot from the model. Otherwise: live. */}
                    {placing
                      ? pendingHere && <ColonistDots count={1} />
                      : slot.colonist && <ColonistDots count={1} />}
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
            const accent = empty
              ? undefined
              : buildingColor(meta?.produces, large);
            const name = meta?.name ?? "";
            const capacity = meta?.capacity ?? 0;
            const typeHl =
              !empty &&
              highlightBuilding != null &&
              slot.building === highlightBuilding;
            // During placement, a built slot shows its PENDING colonist count
            // from the shared model and is a drop / click target while it has
            // spare capacity. Clicking a staffed slot returns one colonist.
            const pendingCount =
              placing && !empty ? placement!.cityFilledCount(i) : 0;
            const droppable =
              placing && !empty && pendingCount < capacity;
            const onSlot = () => {
              if (!placing || empty) return;
              if (pendingCount < capacity) placement!.placeOn("city", i);
              else placement!.removeFrom("city", i);
            };
            const slotEl = (
              <div
                className={
                  "city-slot" +
                  (empty ? " slot-empty" : "") +
                  (large ? " city-large" : "") +
                  (typeHl ? " building-type-hl" : "") +
                  (droppable ? " drop-target" : "") +
                  (droppable && placingDragActive ? " drop-active" : "")
                }
                style={
                  accent
                    ? {
                        borderLeft: `5px solid ${accent}`,
                        background: `color-mix(in srgb, ${accent} 22%, var(--panel-2))`,
                      }
                    : undefined
                }
                title={
                  droppable
                    ? "Drop a colonist here"
                    : placing && !empty && pendingCount > 0
                      ? "Click to return a colonist to San Juan"
                      : empty
                        ? "empty"
                        : name
                }
                onClick={placing && !empty ? onSlot : undefined}
                onDragOver={
                  droppable
                    ? (e) => {
                        e.preventDefault();
                        e.dataTransfer.dropEffect = "move";
                      }
                    : undefined
                }
                onDrop={
                  droppable
                    ? (e) => {
                        e.preventDefault();
                        placement!.placeOn("city", i);
                      }
                    : undefined
                }
                onMouseEnter={
                  empty ? undefined : () => onBuildingHover?.(slot.building)
                }
                onMouseLeave={
                  empty ? undefined : () => onBuildingHover?.(null)
                }
              >
                {!empty && (
                  <>
                    <span className="slot-text">{name}</span>
                    {/* Placement: pending dots from the model. Otherwise live. */}
                    <ColonistDots
                      count={placing ? pendingCount : slot.colonists}
                    />
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
                    isLarge={meta.is_large}
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
