/**
 * InfoTooltip — a hover tooltip that follows the cursor and clamps to the
 * viewport so it never clips at screen edges. Renders nothing until hovered.
 *
 * Used to show building info (name / cost / VP / capacity / description) over
 * the buildings-available shelf (Board) and each occupied city slot
 * (PlayerBoard). The trigger element is rendered inline; the tooltip floats in a
 * fixed-position layer.
 */

import { useCallback, useRef, useState } from "react";

import { buildingColor } from "../types";

interface InfoTooltipProps {
  /** The rendered tooltip body (shown on hover). */
  content: React.ReactNode;
  /** The always-visible trigger element. */
  children: React.ReactNode;
  /** Optional class for the inline wrapper. */
  className?: string;
}

const TOOLTIP_W = 240;
// Assumed max tooltip height, used only to decide whether to flip the tooltip
// above the cursor so it doesn't clip off the bottom of the viewport.
const TOOLTIP_EST_H = 160;
const MARGIN = 8;

export function InfoTooltip({ content, children, className }: InfoTooltipProps) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const frame = useRef<number | null>(null);

  const place = useCallback((clientX: number, clientY: number) => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      // Prefer to the right of the cursor; flip left if it would clip.
      let x = clientX + 14;
      if (x + TOOLTIP_W + MARGIN > vw) x = clientX - TOOLTIP_W - 14;
      if (x < MARGIN) x = MARGIN;
      // Below the cursor; clamp so it stays on-screen vertically.
      let y = clientY + 16;
      if (y + TOOLTIP_EST_H + MARGIN > vh)
        y = Math.max(MARGIN, clientY - TOOLTIP_EST_H);
      setPos({ x, y });
    });
  }, []);

  return (
    <span
      className={"tt-wrap" + (className ? " " + className : "")}
      onMouseEnter={(e) => place(e.clientX, e.clientY)}
      onMouseMove={(e) => place(e.clientX, e.clientY)}
      onMouseLeave={() => {
        if (frame.current !== null) cancelAnimationFrame(frame.current);
        setPos(null);
      }}
    >
      {children}
      {pos && (
        <div
          className="tooltip"
          style={{ left: pos.x, top: pos.y, width: TOOLTIP_W }}
          role="tooltip"
        >
          {content}
        </div>
      )}
    </span>
  );
}

/** Standard building tooltip body. `supply` shows "available / max" when given. */
export function BuildingTooltipBody({
  name,
  cost,
  vp,
  capacity,
  description,
  produces,
  available,
  max,
  isLarge,
}: {
  name: string;
  cost: number;
  vp: number;
  capacity: number;
  description?: string;
  produces?: string | null;
  available?: number;
  max?: number;
  isLarge?: boolean;
}) {
  const swatch = buildingColor(produces, isLarge);
  return (
    <div className="tt-building">
      <div className="tt-title">
        <span className="tt-swatch" style={{ background: swatch }} />
        {name}
      </div>
      <div className="tt-stats">
        <span className="tt-stat">${cost}</span>
        <span className="tt-stat">{vp} VP</span>
        <span className="tt-stat">
          {capacity > 0 ? (
            <>
              {Array.from({ length: capacity }).map((_, i) => (
                <span key={i} className="tt-colonist" />
              ))}
              cap {capacity}
            </>
          ) : (
            "cap 0"
          )}
        </span>
      </div>
      {produces && (
        <div className="tt-produces">Produces {produces}</div>
      )}
      {description && <div className="tt-desc">{description}</div>}
      {max !== undefined && (
        <div className="tt-supply">
          {available ?? 0} of {max} left
        </div>
      )}
    </div>
  );
}

/**
 * Role tooltip body: the catalog description plus dynamic, quantitative hints
 * computed from the current view (e.g. colonists on the ship, accumulated
 * placard doubloons). `hints` is a pre-computed list of one-liners and
 * `placardDoubloons` (if > 0) renders the accumulated bonus.
 */
export function RoleTooltipBody({
  name,
  description,
  hints,
  placardDoubloons,
}: {
  name: string;
  description?: string;
  hints: string[];
  placardDoubloons?: number;
}) {
  return (
    <div className="tt-building">
      <div className="tt-title">{name}</div>
      {description && <div className="tt-desc">{description}</div>}
      {hints.length > 0 && (
        <ul className="tt-hints">
          {hints.map((h, i) => (
            <li key={i}>{h}</li>
          ))}
        </ul>
      )}
      {placardDoubloons !== undefined && placardDoubloons > 0 && (
        <div className="tt-produces">+${placardDoubloons} accumulated on placard</div>
      )}
    </div>
  );
}
