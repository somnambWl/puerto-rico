/**
 * useLogEntries — derives the ordered Log from the playback feed.
 *
 * The backend now attaches `last_action_label` + `last_action_seat` to each
 * streamed frame: the action that PRODUCED that frame (e.g. "Build Harbor
 * (cost 6)" by seat 2). We use those directly so the log shows exactly what
 * each AI and the human did. We fall back to the old synthesized
 * "<phase> action" / human-recorded label only when the backend leaves those
 * null (initial connect / preview frames).
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

      // Prefer the backend-supplied action that produced this frame.
      const hasBackendLabel =
        frame.last_action_label != null && frame.last_action_seat != null;

      // The seat that just acted: the backend value when present, else the
      // previous frame's to_move (who was about to move before this frame).
      const actorSeat = hasBackendLabel
        ? (frame.last_action_seat as number)
        : prev
          ? prev.to_move
          : humanSeat;

      let label: string;
      if (hasBackendLabel) {
        label = frame.last_action_label as string;
        // Consume any pending human label so it doesn't leak to a later frame.
        if (actorSeat === humanSeat) pendingHumanLabel.current = null;
      } else if (actorSeat === humanSeat && pendingHumanLabel.current) {
        label = pendingHumanLabel.current;
        pendingHumanLabel.current = null;
      } else {
        const phaseName =
          PHASE_NAMES[prev ? prev.view.phase : frame.view.phase] ?? "move";
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
