/**
 * Log — chronological history of applied actions.
 *
 * Built from the `logFeed`: each StateMsg pushed during playback is the state
 * *after* an action was applied. The label is now read from the frame's
 * `last_action_label` (what actually happened), falling back to a synthesized
 * "<phase> action" only when the backend didn't supply one (see useLogEntries).
 *
 * Scroll behaviour: the log auto-scrolls ONLY its own container (never the
 * page) and only sticks to the bottom when the user is already near the bottom.
 * If the user has scrolled up to read history, new entries do not yank them back
 * down — standard "stick to bottom unless scrolled up".
 */

import { useEffect, useRef } from "react";

export interface LogEntry {
  seat: number;
  label: string;
  isHuman: boolean;
}

interface LogProps {
  entries: LogEntry[];
  playerNames: string[];
}

/** Within this many px of the bottom counts as "near the bottom". */
const STICK_THRESHOLD_PX = 48;

export function Log({ entries, playerNames }: LogProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  // Whether the user is currently parked near the bottom (so we keep sticking).
  const stickRef = useRef(true);

  // Track scroll position to decide whether to keep auto-sticking.
  const onScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const distFromBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight;
    stickRef.current = distFromBottom <= STICK_THRESHOLD_PX;
  };

  // On new entries, scroll the container (not the page) to the bottom — but
  // only if the user was already near the bottom.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (stickRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [entries.length]);

  return (
    <div className="log">
      <h3>Log</h3>
      <div className="log-entries" ref={containerRef} onScroll={onScroll}>
        {entries.length === 0 && <div className="muted">No moves yet.</div>}
        {entries.map((e, i) => (
          <div
            key={i}
            className={"log-entry" + (e.isHuman ? " log-human" : "")}
          >
            <span className="log-player">
              {playerNames[e.seat] ?? `P${e.seat}`}
            </span>
            <span className="log-label">{e.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
