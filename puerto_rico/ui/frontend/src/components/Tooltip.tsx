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

interface InfoTooltipProps {
  /** The rendered tooltip body (shown on hover). */
  content: React.ReactNode;
  /** The always-visible trigger element. */
  children: React.ReactNode;
  /** Optional class for the inline wrapper. */
  className?: string;
}

const TOOLTIP_W = 240;
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
      if (y + 160 + MARGIN > vh) y = Math.max(MARGIN, clientY - 160);
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

/** Standard building tooltip body. */
export function BuildingTooltipBody({
  name,
  cost,
  vp,
  capacity,
  description,
  produces,
}: {
  name: string;
  cost: number;
  vp: number;
  capacity: number;
  description?: string;
  produces?: string | null;
}) {
  return (
    <div className="tt-building">
      <div className="tt-title">{name}</div>
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
    </div>
  );
}
