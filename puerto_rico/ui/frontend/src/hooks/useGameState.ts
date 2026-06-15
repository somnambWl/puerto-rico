/**
 * useGameState — drives one game over the WebSocket.
 *
 * Protocol (backend app.py):
 *   - On connect, the server sends a {type:"state", ...StateMsg} frame.
 *   - The client sends {action_id} to apply the human's choice.
 *   - The server replies with one {type:"sequence", states:[...]} frame (the
 *     full ordered list: human action + each AI response) and THEN streams the
 *     same states as individual {type:"state", ...} frames ~0.12s apart.
 *   - {type:"error", message} on a bad action (socket stays open).
 *
 * Animation strategy: we ignore the streamed per-state frames for playback and
 * instead drive the animation ourselves from the single "sequence" frame. This
 * keeps frame timing under our control and avoids double-applying. Each state in
 * the sequence is shown in order on a timer; while the queue drains,
 * `isAnimating` is true so the UI disables input. Every consumed state is also
 * pushed to `logFeed` so the Log can append one entry per applied action.
 *
 * Reconnect: on mount (and on gameId change) we GET the current state so a
 * refresh restores the board even before the socket's first frame arrives.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { getState } from "../api";
import type { ServerFrame, StateMsg } from "../types";

const FRAME_DELAY_MS = 120;

export type ConnectionStatus = "connecting" | "open" | "closed";

export interface GameStateHook {
  currentState: StateMsg | null;
  isAnimating: boolean;
  status: ConnectionStatus;
  error: string | null;
  /** Each applied state, pushed in playback order, for the Log to consume. */
  logFeed: StateMsg[];
  sendAction: (actionId: number) => void;
}

export function useGameState(gameId: string | null): GameStateHook {
  const [currentState, setCurrentState] = useState<StateMsg | null>(null);
  const [isAnimating, setIsAnimating] = useState(false);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [logFeed, setLogFeed] = useState<StateMsg[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  // Pending animation queue + timer handle.
  const queueRef = useRef<StateMsg[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Drain one state from the queue, schedule the next.
  const drain = useCallback(() => {
    const next = queueRef.current.shift();
    if (next === undefined) {
      setIsAnimating(false);
      timerRef.current = null;
      return;
    }
    setCurrentState(next);
    setLogFeed((prev) => [...prev, next]);
    timerRef.current = setTimeout(drain, FRAME_DELAY_MS);
  }, []);

  const enqueue = useCallback(
    (states: StateMsg[]) => {
      if (states.length === 0) return;
      queueRef.current.push(...states);
      setIsAnimating(true);
      if (timerRef.current === null) {
        // Show the first frame immediately, then tick.
        drain();
      }
    },
    [drain],
  );

  // Open the socket (and seed from GET) whenever the gameId changes.
  useEffect(() => {
    if (!gameId) return;

    let cancelled = false;

    // Reconnect-safe seed: fetch the current state up-front.
    getState(gameId)
      .then((s) => {
        if (!cancelled && currentState === null) setCurrentState(s);
      })
      .catch(() => {
        /* the socket frame will populate it shortly */
      });

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(
      `${proto}://${window.location.host}/ws/games/${gameId}`,
    );
    wsRef.current = ws;
    setStatus("connecting");

    ws.onopen = () => {
      if (!cancelled) setStatus("open");
    };
    ws.onclose = () => {
      if (!cancelled) setStatus("closed");
    };
    ws.onerror = () => {
      if (!cancelled) setStatus("closed");
    };
    ws.onmessage = (ev) => {
      if (cancelled) return;
      let frame: ServerFrame;
      try {
        frame = JSON.parse(ev.data as string) as ServerFrame;
      } catch {
        return;
      }
      if (frame.type === "sequence") {
        // Drive the animation ourselves from the ordered list.
        enqueue(frame.states);
      } else if (frame.type === "state") {
        // The on-connect frame (and the per-state stream). Only adopt it
        // directly when we are NOT animating, so the stream does not jump
        // ahead of our paced playback.
        const { type: _t, ...state } = frame;
        void _t;
        if (queueRef.current.length === 0 && timerRef.current === null) {
          setCurrentState(state as StateMsg);
        }
      } else if (frame.type === "error") {
        setError(frame.message);
      }
    };

    return () => {
      cancelled = true;
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      queueRef.current = [];
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId, enqueue]);

  const sendAction = useCallback((actionId: number) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError("not connected");
      return;
    }
    setError(null);
    ws.send(JSON.stringify({ action_id: actionId }));
  }, []);

  return { currentState, isAnimating, status, error, logFeed, sendAction };
}
