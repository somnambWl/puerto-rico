/**
 * App — start screen + the live game view.
 *
 * Start screen: choose opponent (heuristic/rl), optional seed, human seat.
 * Creating a game (POST /games) yields a game_id; we then drive the game over
 * the WebSocket via useGameState. The layout is: shared Board across the top,
 * the human's large PlayerBoard prominent, the three AI boards compact in a
 * sidebar, the ActionPrompt, the Log, and a GameOver modal on terminal.
 *
 * Log derivation: the backend streams the resulting StateMsg after each applied
 * action but not the applied action's own label (legal_actions describe the
 * NEXT decision). So we log the human's chosen label directly, and for each
 * subsequent AI state we synthesize an entry from the seat that just moved
 * (the previous frame's to_move) and the phase it acted in.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { createGame, getCatalog, previewAction, type Opponent } from "./api";
import { CatalogProvider, useBuildingInfo } from "./catalog";
import { Board } from "./components/Board";
import { GameOver } from "./components/GameOver";
import { Log, type LogEntry } from "./components/Log";
import { PlaybackBar } from "./components/PlaybackBar";
import { PlayerBoard } from "./components/PlayerBoard";
import { ActionPrompt } from "./components/ActionPrompt";
import { PreviewPanel } from "./components/PreviewPanel";
import { computePreviewDiff, type PreviewDiff } from "./preview";
import { useGameState } from "./hooks/useGameState";
import type { Catalog, Highlight, LegalAction, StateMsg } from "./types";
import { PHASE_NAMES } from "./types";

const PREVIEW_DEBOUNCE_MS = 120;

interface GameSetup {
  gameId: string;
  humanSeat: number;
}

export default function App() {
  const [setup, setSetup] = useState<GameSetup | null>(null);

  // Fetch the static catalog once on app start. Failure is non-fatal — the
  // catalog context stays null and components fall back to the hardcoded maps.
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  useEffect(() => {
    let cancelled = false;
    getCatalog()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch(() => {
        /* fall back to hardcoded BUILDINGS / GOOD_NAMES maps */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Start-screen form state.
  const [opponent, setOpponent] = useState<Opponent>("heuristic");
  const [seedText, setSeedText] = useState("");
  const [humanSeat, setHumanSeat] = useState(0);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const onStart = useCallback(async () => {
    setCreating(true);
    setCreateError(null);
    try {
      const seed = seedText.trim() === "" ? undefined : Number(seedText.trim());
      const res = await createGame(opponent, {
        seed: Number.isNaN(seed as number) ? undefined : seed,
        human_seat: humanSeat,
      });
      setSetup({ gameId: res.game_id, humanSeat });
    } catch (e) {
      setCreateError(String(e));
    } finally {
      setCreating(false);
    }
  }, [opponent, seedText, humanSeat]);

  if (!setup) {
    return (
      <CatalogProvider catalog={catalog}>
      <div className="start-screen">
        <h1>Puerto Rico</h1>
        <div className="start-form">
          <label>
            Opponent
            <select
              value={opponent}
              onChange={(e) => setOpponent(e.target.value as Opponent)}
            >
              <option value="heuristic">Heuristic</option>
              <option value="rl">RL</option>
            </select>
          </label>
          <label>
            Human seat
            <select
              value={humanSeat}
              onChange={(e) => setHumanSeat(Number(e.target.value))}
            >
              {[0, 1, 2, 3].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label>
            Seed (optional)
            <input
              value={seedText}
              onChange={(e) => setSeedText(e.target.value)}
              placeholder="random"
            />
          </label>
          <button
            className="action-btn"
            disabled={creating}
            onClick={onStart}
          >
            {creating ? "Creating…" : "Start game"}
          </button>
          {createError && <div className="error">{createError}</div>}
        </div>
      </div>
      </CatalogProvider>
    );
  }

  return (
    <CatalogProvider catalog={catalog}>
      <GameView
        gameId={setup.gameId}
        humanSeat={setup.humanSeat}
        onNewGame={() => setSetup(null)}
      />
    </CatalogProvider>
  );
}

function playerName(seat: number, humanSeat: number): string {
  return seat === humanSeat ? "You" : `AI ${seat}`;
}

interface GameViewProps {
  gameId: string;
  humanSeat: number;
  onNewGame: () => void;
}

function GameView({ gameId, humanSeat, onNewGame }: GameViewProps) {
  const {
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
  } = useGameState(gameId);

  const buildingInfo = useBuildingInfo();

  const [highlight, setHighlight] = useState<Highlight>(null);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);

  // --- Action preview (hover a legal action -> diff the resulting state) --- //
  const [previewLabel, setPreviewLabel] = useState<string | null>(null);
  const [previewDiff, setPreviewDiff] = useState<PreviewDiff | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewHighlight, setPreviewHighlight] = useState<Highlight>(null);
  const previewTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previewAbort = useRef<AbortController | null>(null);
  // Cache preview diffs per action id, scoped to the current decision state.
  const previewCache = useRef<Map<number, PreviewDiff>>(new Map());
  const previewStateKey = useRef<string>("");

  // Track the human's last chosen label so the resulting frame logs correctly.
  const pendingHumanLabel = useRef<string | null>(null);
  // The previous frame (whose to_move identifies who just acted).
  const prevFrame = useRef<StateMsg | null>(null);
  const consumedCount = useRef(0);

  const playerNames = useMemo(
    () => [0, 1, 2, 3].map((s) => playerName(s, humanSeat)),
    [humanSeat],
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

  const onAction = useCallback(
    (id: number) => {
      const action = currentState?.legal_actions.find((a) => a.id === id);
      pendingHumanLabel.current = action?.label ?? "move";
      // Seed prevFrame with the state the human is acting from, so the first
      // resulting frame attributes the action to the human.
      if (currentState) prevFrame.current = currentState;
      sendAction(id);
    },
    [currentState, sendAction],
  );

  // A key identifying the current human-decision state, so the preview cache is
  // invalidated whenever the decision context changes.
  const decisionKey = useMemo(() => {
    if (!currentState) return "";
    const v = currentState.view;
    return `${v.phase}:${currentState.to_move}:${currentState.legal_actions
      .map((a) => a.id)
      .join(",")}`;
  }, [currentState]);

  const clearPreview = useCallback(() => {
    if (previewTimer.current !== null) {
      clearTimeout(previewTimer.current);
      previewTimer.current = null;
    }
    if (previewAbort.current !== null) {
      previewAbort.current.abort();
      previewAbort.current = null;
    }
    setPreviewLabel(null);
    setPreviewDiff(null);
    setPreviewLoading(false);
    setPreviewHighlight(null);
  }, []);

  const onPreview = useCallback(
    (action: LegalAction | null) => {
      // Reset the cache if the decision context changed.
      if (previewStateKey.current !== decisionKey) {
        previewStateKey.current = decisionKey;
        previewCache.current.clear();
      }
      if (action === null) {
        clearPreview();
        return;
      }
      if (!currentState) return;

      setPreviewLabel(action.label);

      // Serve from cache immediately if present.
      const cached = previewCache.current.get(action.id);
      if (cached) {
        if (previewTimer.current !== null) {
          clearTimeout(previewTimer.current);
          previewTimer.current = null;
        }
        setPreviewDiff(cached);
        setPreviewLoading(false);
        setPreviewHighlight(cached.highlight);
        return;
      }

      setPreviewDiff(null);
      setPreviewLoading(true);
      setPreviewHighlight(null);

      // Debounce the network request; cancel any in-flight one.
      if (previewTimer.current !== null) clearTimeout(previewTimer.current);
      previewTimer.current = setTimeout(() => {
        if (previewAbort.current !== null) previewAbort.current.abort();
        const ctrl = new AbortController();
        previewAbort.current = ctrl;
        const keyAtRequest = decisionKey;
        previewAction(gameId, action.id, ctrl.signal)
          .then((after) => {
            // Ignore stale responses (decision changed or hover moved on).
            if (keyAtRequest !== previewStateKey.current) return;
            const diff = computePreviewDiff(
              currentState,
              after,
              humanSeat,
              buildingInfo,
            );
            previewCache.current.set(action.id, diff);
            setPreviewDiff(diff);
            setPreviewLoading(false);
            setPreviewHighlight(diff.highlight);
          })
          .catch(() => {
            /* aborted or failed — leave the panel showing the label only */
            setPreviewLoading(false);
          });
      }, PREVIEW_DEBOUNCE_MS);
    },
    [clearPreview, currentState, decisionKey, gameId, humanSeat, buildingInfo],
  );

  // Disable / clear preview while AI playback is animating.
  useEffect(() => {
    if (isAnimating) clearPreview();
  }, [isAnimating, clearPreview]);

  if (!currentState) {
    return (
      <div className="loading">
        <div className="muted">Connecting… ({status})</div>
        {error && <div className="error">{error}</div>}
      </div>
    );
  }

  const view = currentState.view;
  const aiThinking =
    !currentState.terminal && !currentState.to_move_is_human && !isAnimating;
  const promptDisabled =
    isAnimating ||
    currentState.terminal ||
    !currentState.to_move_is_human;

  const others = view.players
    .map((_, seat) => seat)
    .filter((seat) => seat !== humanSeat);

  // The preview ghost-highlight wins over the hover highlight when present.
  const activeHighlight = previewHighlight ?? highlight;

  // Latest move label for the playback bar (most recent log entry).
  const latestMoveLabel =
    logEntries.length > 0
      ? `${playerNames[logEntries[logEntries.length - 1].seat] ?? ""}: ${
          logEntries[logEntries.length - 1].label
        }`
      : null;

  return (
    <div className="game">
      <header className="game-header">
        <span>
          Game {gameId.slice(0, 8)} · you are P{humanSeat}
        </span>
        <span className={"conn conn-" + status}>{status}</span>
        {error && <span className="error">{error}</span>}
      </header>

      <div className="game-layout">
        <main className="game-main">
          <Board
            view={view}
            highlight={activeHighlight}
            onPlantationClick={() => {
              /* visual highlight toggle handled via hover; click is a no-op
                 placeholder so the row reads as interactive */
            }}
          />

          {isAnimating && (
            <PlaybackBar
              index={playbackIndex}
              total={playbackTotal}
              pendingCount={pendingCount}
              isPaused={isPaused}
              speed={speed}
              latestLabel={latestMoveLabel}
              onPause={pause}
              onResume={resume}
              onStep={step}
              onSkip={skipToEnd}
              onSpeed={setSpeed}
            />
          )}

          <PlayerBoard
            playerView={view.players[humanSeat]}
            seat={humanSeat}
            isHuman
            name={playerNames[humanSeat]}
            active={view.current_player === humanSeat}
          />

          <ActionPrompt
            legalActions={currentState.legal_actions}
            onAction={onAction}
            disabled={promptDisabled}
            aiThinking={aiThinking}
            onHighlight={setHighlight}
            onPreview={onPreview}
          />

          <PreviewPanel
            label={previewLabel}
            diff={previewDiff}
            loading={previewLoading}
          />
        </main>

        <aside className="game-side">
          <div className="opponents">
            {others.map((seat) => (
              <PlayerBoard
                key={seat}
                playerView={view.players[seat]}
                seat={seat}
                isHuman={false}
                name={playerNames[seat]}
                active={view.current_player === seat}
              />
            ))}
          </div>
          <Log entries={logEntries} playerNames={playerNames} />
        </aside>
      </div>

      {currentState.terminal && currentState.result && (
        <GameOver
          result={currentState.result}
          playerNames={playerNames}
          onNewGame={onNewGame}
        />
      )}
    </div>
  );
}
