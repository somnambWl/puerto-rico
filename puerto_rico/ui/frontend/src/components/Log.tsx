/**
 * Log — chronological history of applied actions.
 *
 * Built from the `logFeed`: each StateMsg pushed during playback is the state
 * *after* an action was applied. We can't read the just-applied action's label
 * off the resulting state directly (legal_actions describe the NEXT decision),
 * so we annotate each appended state with the label of the action that produced
 * it. That annotation is supplied by App, which knows the human's chosen label
 * and tags AI states generically.
 *
 * Newest entry at the bottom; the panel auto-scrolls to the latest.
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

export function Log({ entries, playerNames }: LogProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [entries.length]);

  return (
    <div className="log">
      <h3>Log</h3>
      <div className="log-entries">
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
        <div ref={endRef} />
      </div>
    </div>
  );
}
