/**
 * PlayerBoard — one player's personal state.
 *
 * Island (12 slots, colonist dots), city (12 building slots; large buildings
 * span 2 slots; colonist dots per staffed slot), doubloons, goods inventory,
 * stored colonists, and VP (shown for the human, "?" for opponents).
 *
 * The human board renders large; opponent boards render compact.
 */

import { useState } from "react";

import { useBuildingInfo } from "../catalog";
import { findAction } from "../findAction";
import type { BuildingId, LegalAction, PlayerView } from "../types";
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
  /** True when this seat holds the governor placard. */
  isGovernor?: boolean;
  /** 1-based seat order number to show as a turn-order badge. */
  orderNumber?: number;
  /** Highlight every city slot holding this building type. */
  highlightBuilding?: BuildingId | null;
  /** Hover a city slot to highlight that building type everywhere. */
  onBuildingHover?: (id: BuildingId | null) => void;
  /** Legal actions for the human's current turn — used for click/drag colonist
   * placement during the human's own Mayor phase. Empty otherwise. */
  legalActions?: LegalAction[];
  /** Take the action with this id (drop / click a colonist target). */
  onBoardAction?: (id: number) => void;
}

/** A draggable San Juan colonist token (Mayor placement). */
function ColonistToken({
  onDragStart,
  onDragEnd,
}: {
  onDragStart: () => void;
  onDragEnd: () => void;
}) {
  return (
    <span
      className="colonist-token"
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", "colonist");
        onDragStart();
      }}
      onDragEnd={onDragEnd}
      title="Drag onto an empty circle to place"
    >
      <span className="dot" />
    </span>
  );
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
  legalActions = [],
  onBoardAction,
}: PlayerBoardProps) {
  const buildingInfo = useBuildingInfo();
  const [dragging, setDragging] = useState(false);
  const cls =
    "player-board" +
    (isHuman ? " player-human" : " player-compact") +
    (active ? " player-active" : "");

  // Mayor placement is live only on the human's own board when a PLACE_COLONIST
  // is among the legal actions. Resolve the action id for a given drop target.
  const placing =
    isHuman && legalActions.some((a) => a.kind === "colonist");
  const cityActionId = (i: number) =>
    findAction(legalActions, { type: "colonist", kind: "city", index: i });
  const islandActionId = (i: number) =>
    findAction(legalActions, { type: "colonist", kind: "island", index: i });
  const storeActionId = findAction(legalActions, {
    type: "colonist",
    kind: "store",
  });
  const take = (id: number | null) => {
    if (id != null && onBoardAction) onBoardAction(id);
  };
  // Distinct empty placement targets still available this turn.
  const remainingTargets = placing
    ? legalActions.filter(
        (a) =>
          a.kind === "colonist" && a.colonist_target?.kind !== "store",
      ).length
    : 0;

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

      {/* Mayor placement: drag San Juan colonists onto empty circles. */}
      {placing && (
        <div className="mayor-placement">
          <div className="mayor-placement-head">
            <span className="mayor-placement-label">
              Place colonists — drag a token onto an empty circle
            </span>
            <button
              className="action-btn mayor-store-btn"
              disabled={storeActionId == null}
              onClick={() => take(storeActionId)}
              title="Keep the rest in San Juan and end placement"
            >
              Done / store remaining
            </button>
          </div>
          <div className="mayor-supply">
            {playerView.stored_colonists > 0 ? (
              Array.from({ length: playerView.stored_colonists }).map((_, i) => (
                <ColonistToken
                  key={i}
                  onDragStart={() => setDragging(true)}
                  onDragEnd={() => setDragging(false)}
                />
              ))
            ) : (
              <span className="muted">none in San Juan</span>
            )}
            <span className="muted mayor-remaining">
              {remainingTargets} open slot{remainingTargets === 1 ? "" : "s"}
            </span>
          </div>
        </div>
      )}

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
            // A tiled-but-unmanned island slot is a colonist drop target.
            const dropId =
              placing && !empty && !slot.colonist ? islandActionId(i) : null;
            const droppable = dropId != null;
            return (
              <div
                key={i}
                className={
                  "island-slot" +
                  (empty ? " slot-empty" : "") +
                  (droppable ? " drop-target" : "") +
                  (droppable && dragging ? " drop-active" : "")
                }
                style={empty ? undefined : { background: TILE_COLORS[slot.tile] }}
                title={
                  droppable
                    ? "Drop a colonist here"
                    : TILE_NAMES[slot.tile]
                }
                onClick={droppable ? () => take(dropId) : undefined}
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
                        setDragging(false);
                        take(dropId);
                      }
                    : undefined
                }
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
            const typeHl =
              !empty &&
              highlightBuilding != null &&
              slot.building === highlightBuilding;
            // A built slot with spare capacity is a colonist drop target during
            // the human's Mayor placement (the engine offers it as a legal
            // PLACE_COLONIST(city, index)).
            const dropId = placing && !empty ? cityActionId(i) : null;
            const droppable = dropId != null;
            const slotEl = (
              <div
                className={
                  "city-slot" +
                  (empty ? " slot-empty" : "") +
                  (large ? " city-large" : "") +
                  (typeHl ? " building-type-hl" : "") +
                  (droppable ? " drop-target" : "") +
                  (droppable && dragging ? " drop-active" : "")
                }
                title={
                  droppable ? "Drop a colonist here" : empty ? "empty" : name
                }
                onClick={droppable ? () => take(dropId) : undefined}
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
                        setDragging(false);
                        take(dropId);
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
