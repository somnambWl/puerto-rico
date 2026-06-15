/**
 * useGameState — drives one game over the WebSocket, with step-by-step playback.
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
 * instead drive playback ourselves from the single "sequence" frame. The queued
 * sequence can be auto-played (slower default so a human can watch the AI),
 * PAUSED, advanced one step at a time, resumed, or skipped to the end. While the
 * queue drains, `isAnimating` is true so the UI disables human input. Every
 * consumed state is pushed to `logFeed` so the Log appends one entry per action.
 *
 * Reconnect: on mount (and on gameId change) we GET the current state so a
 * refresh restores the board even before the socket's first frame arrives.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { getState } from "../api";
import type { ServerFrame, StateMsg } from "../types";

export type PlaybackSpeed = "slow" | "normal" | "fast";

/** Auto-play delay per frame (ms) by speed. */
const SPEED_DELAY_MS: Record<PlaybackSpeed, number> = {
  slow: 1200,
  normal: 800,
  fast: 350,
};

export type ConnectionStatus = "connecting" | "open" | "closed";

export interface GameStateHook {
  currentState: StateMsg | null;
  isAnimating: boolean;
  /** True while the queue is non-empty AND auto-advance is paused. */
  isPaused: boolean;
  /** Frames still queued (not yet shown). */
  pendingCount: number;
  /** 1-based index of the frame currently shown within the active sequence. */
  playbackIndex: number;
  /** Total frames in the active sequence (0 when idle). */
  playbackTotal: number;
  speed: PlaybackSpeed;
  setSpeed: (s: PlaybackSpeed) => void;
  status: ConnectionStatus;
  error: string | null;
  /** Each applied state, pushed in playback order, for the Log to consume. */
  logFeed: StateMsg[];
  sendAction: (actionId: number) => void;
  pause: () => void;
  resume: () => void;
  /** Show the next queued frame immediately (auto-pauses). */
  step: () => void;
  /** Drain the whole queue at once and show the final frame. */
  skipToEnd: () => void;
}

export function useGameState(gameId: string | null): GameStateHook {
  const [currentState, setCurrentState] = useState<StateMsg | null>(null);
  const [isAnimating, setIsAnimating] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [playbackIndex, setPlaybackIndex] = useState(0);
  const [playbackTotal, setPlaybackTotal] = useState(0);
  const [speed, setSpeed] = useState<PlaybackSpeed>("normal");
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [logFeed, setLogFeed] = useState<StateMsg[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  // Pending animation queue + timer handle.
  const queueRef = useRef<StateMsg[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pausedRef = useRef(false);
  const speedRef = useRef<PlaybackSpeed>("normal");
  const shownRef = useRef(0); // frames shown in the active sequence

  useEffect(() => {
    speedRef.current = speed;
  }, [speed]);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Show one queued frame; returns true if one was shown.
  const showNext = useCallback((): boolean => {
    const next = queueRef.current.shift();
    if (next === undefined) return false;
    setCurrentState(next);
    setLogFeed((prev) => [...prev, next]);
    shownRef.current += 1;
    setPlaybackIndex(shownRef.current);
    setPendingCount(queueRef.current.length);
    if (queueRef.current.length === 0) {
      // Sequence finished.
      setIsAnimating(false);
      setIsPaused(false);
      pausedRef.current = false;
    }
    return true;
  }, []);

  // Auto-advance tick: respects pause.
  const tick = useCallback(() => {
    timerRef.current = null;
    if (pausedRef.current) return;
    const shown = showNext();
    if (shown && queueRef.current.length > 0 && !pausedRef.current) {
      timerRef.current = setTimeout(tick, SPEED_DELAY_MS[speedRef.current]);
    }
  }, [showNext]);

  const enqueue = useCallback(
    (states: StateMsg[]) => {
      if (states.length === 0) return;
      queueRef.current.push(...states);
      shownRef.current = 0;
      setPlaybackTotal(states.length);
      setPlaybackIndex(0);
      setPendingCount(queueRef.current.length);
      setIsAnimating(true);
      setIsPaused(false);
      pausedRef.current = false;
      clearTimer();
      // Show the first frame immediately, then auto-advance.
      showNext();
      if (queueRef.current.length > 0) {
        timerRef.current = setTimeout(tick, SPEED_DELAY_MS[speedRef.current]);
      }
    },
    [clearTimer, showNext, tick],
  );

  const pause = useCallback(() => {
    if (queueRef.current.length === 0) return;
    pausedRef.current = true;
    setIsPaused(true);
    clearTimer();
  }, [clearTimer]);

  const resume = useCallback(() => {
    if (queueRef.current.length === 0) return;
    pausedRef.current = false;
    setIsPaused(false);
    clearTimer();
    showNext();
    if (queueRef.current.length > 0 && !pausedRef.current) {
      timerRef.current = setTimeout(tick, SPEED_DELAY_MS[speedRef.current]);
    }
  }, [clearTimer, showNext, tick]);

  const step = useCallback(() => {
    if (queueRef.current.length === 0) return;
    // Stepping pauses auto-advance and shows exactly one more frame.
    pausedRef.current = true;
    clearTimer();
    showNext();
    if (queueRef.current.length > 0) setIsPaused(true);
  }, [clearTimer, showNext]);

  const skipToEnd = useCallback(() => {
    clearTimer();
    const q = queueRef.current;
    if (q.length === 0) return;
    const last = q[q.length - 1];
    // Push all remaining frames to the log so history stays complete.
    setLogFeed((prev) => [...prev, ...q]);
    shownRef.current += q.length;
    queueRef.current = [];
    setCurrentState(last);
    setPlaybackIndex(shownRef.current);
    setPendingCount(0);
    setIsAnimating(false);
    setIsPaused(false);
    pausedRef.current = false;
  }, [clearTimer]);

  // Open the socket (and seed from GET) whenever the gameId changes.
  useEffect(() => {
    if (!gameId) return;

    let cancelled = false;

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
        enqueue(frame.states);
      } else if (frame.type === "state") {
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
      clearTimer();
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

  return {
    currentState,
    isAnimating,
    isPaused,
    pendingCount,
    playbackIndex,
    playbackTotal,
    speed,
    setSpeed,
    status,
    error,
    logFeed,
    sendAction,
    pause,
    resume,
    step,
    skipToEnd,
  };
}
