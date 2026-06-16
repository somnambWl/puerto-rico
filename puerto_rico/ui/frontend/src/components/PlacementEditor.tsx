/**
 * PlacementEditor — the control bar for the human's Mayor colonist placement.
 *
 * There is ONE placement area: the human's own PlayerBoard. The actual island /
 * city slots are the drop / click targets, and the pending arrangement (colonist
 * dots) is shown on those slots. This component is only the compact CONTROL BAR
 * that accompanies that surface:
 *
 *   - the San Juan colonist SOURCE (draggable tokens + a remaining count),
 *   - the open-circle count,
 *   - "Place all" / "Clear" / "Confirm placement" buttons.
 *
 * All of these operate on the SINGLE shared arrangement (see usePlacement),
 * which PlayerBoard also reads/writes. "Confirm placement" submits the whole
 * arrangement as one batch of action ids (a PLACE_COLONIST per assigned circle,
 * then a final store) in a single round-trip.
 *
 * Dragging a San Juan token onto a board slot, or clicking a placed colonist to
 * return it to San Juan, is handled by PlayerBoard against the same model.
 */

import type { PlacementModel } from "../hooks/usePlacement";

interface PlacementEditorProps {
  /** The shared placement arrangement (also driven by PlayerBoard's slots). */
  placement: PlacementModel;
  /** Begin dragging a colonist from the San Juan pool. */
  onSanJuanDragStart: () => void;
  /** End a San Juan drag (regardless of where it dropped). */
  onSanJuanDragEnd: () => void;
  /** Submit the realized arrangement as one batch of action ids. */
  onConfirm: (actionIds: number[]) => void;
}

export function PlacementEditor({
  placement,
  onSanJuanDragStart,
  onSanJuanDragEnd,
  onConfirm,
}: PlacementEditorProps) {
  const { sanJuan, openCount, placeAll, clearAll, buildBatch } = placement;

  return (
    <div className="placement-editor">
      <div className="pe-bar">
        <div className="pe-head">
          <span className="pe-title">Place your colonists</span>
          <span className="pe-counts">
            <strong>{sanJuan}</strong> in San Juan ·{" "}
            <strong>{openCount}</strong> open circle{openCount === 1 ? "" : "s"}
          </span>
        </div>

        {/* San Juan source: draggable tokens for every unplaced colonist. */}
        <div className="pe-sanjuan">
          <span className="pe-zone-label">San Juan</span>
          {sanJuan > 0 ? (
            Array.from({ length: sanJuan }).map((_, i) => (
              <span
                key={i}
                className="colonist-token"
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.effectAllowed = "move";
                  e.dataTransfer.setData("text/plain", "colonist");
                  onSanJuanDragStart();
                }}
                onDragEnd={onSanJuanDragEnd}
                title="Drag onto a board slot to place"
              >
                <span className="dot" />
              </span>
            ))
          ) : (
            <span className="muted">empty</span>
          )}
        </div>

        <div className="pe-actions">
          <button
            className="action-btn pe-place-all"
            onClick={placeAll}
            disabled={sanJuan === 0 || openCount === 0}
            title="Fill every empty circle (chains first), store the rest"
          >
            Place all
          </button>
          <button className="action-btn pe-clear" onClick={clearAll}>
            Clear
          </button>
          <button
            className="action-btn pe-confirm"
            onClick={() => onConfirm(buildBatch())}
            title="Submit this arrangement"
          >
            Confirm placement
          </button>
        </div>
      </div>
    </div>
  );
}
