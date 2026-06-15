/**
 * useLogEntries — derives the ordered Log from the playback feed.
 *
 * The backend streams the resulting StateMsg after each applied action but not
 * the applied action's own label (legal_actions describe the NEXT decision). So:
 *   - the human's chosen label is recorded directly (recordHumanAction),
 *   - for each subsequent AI frame we synthesize an entry from the seat that
 *     just moved (the previous frame's to_move) and the phase it acted in.
 *
 * `logFeed` is the append-only list of consumed states from useGameState; we
 * track how many we've turned into entries (consumedCount) and the previous
 * frame (prevFrame) across renders via refs.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { LogEntry } from "../components/Log";
import type { StateMsg } from "../types";
import { PHASE_NAMES } from "../types";

export interface LogEntriesHook {
  logEntries: LogEntry[];
  /**
   * Record the human's chosen action just before sending it: stores the label
   * for the resulting frame and seeds prevFrame with the state acted from, so
   * the first resulting frame is attributed to the human.
   */
  recordHumanAction: (actedFrom: StateMsg, label: string) => void;
}

export function useLogEntries(
  logFeed: StateMsg[],
  humanSeat: number,
): LogEntriesHook {
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);

  // The human's last chosen label, consumed by the next human-attributed frame.
  const pendingHumanLabel = useRef<string | null>(null);
  // The previous frame (whose to_move identifies who just acted).
  const prevFrame = useRef<StateMsg | null>(null);
  const consumedCount = useRef(0);

  const recordHumanAction = useCallback(
    (actedFrom: StateMsg, label: string) => {
      pendingHumanLabel.current = label;
      prevFrame.current = actedFrom;
    },
    [],
  );

  // Build log entries from newly consumed frames in logFeed.
  useEffect(() => {
    if (logFeed.length <= consumedCount.current) return;
    const newEntries: LogEntry[] = [];
    for (let i = consumedCount.current; i < logFeed.length; i++) {
      const frame = logFeed[i];
      const prev = prevFrame.current;
      // The seat that just acted is the previous frame's to_move; if we have no
      // previous frame, fall back to the human seat.
      const actorSeat = prev ? prev.to_move : humanSeat;
      const phaseName =
        PHASE_NAMES[prev ? prev.view.phase : frame.view.phase] ?? "move";
      let label: string;
      if (actorSeat === humanSeat && pendingHumanLabel.current) {
        label = pendingHumanLabel.current;
        pendingHumanLabel.current = null;
      } else {
        label = `${phaseName} action`;
      }
      newEntries.push({
        seat: actorSeat,
        label,
        isHuman: actorSeat === humanSeat,
      });
      prevFrame.current = frame;
    }
    consumedCount.current = logFeed.length;
    if (newEntries.length > 0) {
      setLogEntries((prev) => [...prev, ...newEntries]);
    }
  }, [logFeed, humanSeat]);

  return { logEntries, recordHumanAction };
}
