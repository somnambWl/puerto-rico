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

import { useCallback, useEffect, useMemo, useState } from "react";

import { createGame, getCatalog, type Opponent } from "./api";
import { CatalogProvider, useBuildingInfo } from "./catalog";
import { Board } from "./components/Board";
import { GameOver } from "./components/GameOver";
import { Log } from "./components/Log";
import { PlaybackBar } from "./components/PlaybackBar";
import { PlayerBoard } from "./components/PlayerBoard";
import { ActionPrompt } from "./components/ActionPrompt";
import { PreviewPanel } from "./components/PreviewPanel";
import { Standings } from "./components/Standings";
import { useGameState } from "./hooks/useGameState";
import { useActionPreview } from "./hooks/useActionPreview";
import { useLogEntries } from "./hooks/useLogEntries";
import type {
  BuildingId,
  Catalog,
  Highlight,
  LegalAction,
} from "./types";

interface GameSetup {
  gameId: string;
  humanSeat: number;
}

/** Derive a Board highlight directly from a legal action's structured fields. */
function highlightForAction(action: LegalAction): Highlight {
  if (action.building != null) {
    return { kind: "building", buildingId: action.building };
  }
  if (action.role != null) {
    return { kind: "role", role: action.role };
  }
  if (action.kind === "ship") {
    return { kind: "ship", index: action.ship ?? -1 };
  }
  if (action.good != null) {
    return { kind: "good", good: action.good };
  }
  return null;
}

export default function App() {
  const [setup, setSetup] = useState<GameSetup | null>(null);

  // Fetch the static catalog once on app start. Failure is non-fatal — the
  // catalog context stays null and building lookups degrade to a generic
  // "building N" label (see catalog.tsx :: useBuildingInfo).
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  useEffect(() => {
    let cancelled = false;
    getCatalog()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch(() => {
        /* non-fatal: building names fall back to "building N" */
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

  // One CatalogProvider at the root covers both the start screen and the game
  // view, so the catalog context is never duplicated.
  return (
    <CatalogProvider catalog={catalog}>
      {setup ? (
        <GameView
          gameId={setup.gameId}
          humanSeat={setup.humanSeat}
          onNewGame={() => setSetup(null)}
        />
      ) : (
        <StartScreen
          opponent={opponent}
          setOpponent={setOpponent}
          humanSeat={humanSeat}
          setHumanSeat={setHumanSeat}
          seedText={seedText}
          setSeedText={setSeedText}
          creating={creating}
          createError={createError}
          onStart={onStart}
        />
      )}
    </CatalogProvider>
  );
}

interface StartScreenProps {
  opponent: Opponent;
  setOpponent: (o: Opponent) => void;
  humanSeat: number;
  setHumanSeat: (s: number) => void;
  seedText: string;
  setSeedText: (s: string) => void;
  creating: boolean;
  createError: string | null;
  onStart: () => void;
}

function StartScreen({
  opponent,
  setOpponent,
  humanSeat,
  setHumanSeat,
  seedText,
  setSeedText,
  creating,
  createError,
  onStart,
}: StartScreenProps) {
  return (
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
  // Highlight every city slot (across all boards) holding this building type.
  const [highlightBuilding, setHighlightBuilding] = useState<BuildingId | null>(
    null,
  );

  const { logEntries, recordHumanAction } = useLogEntries(logFeed, humanSeat);
  const {
    previewLabel,
    previewDiff,
    previewLoading,
    previewHighlight,
    onPreview,
    clearPreview,
  } = useActionPreview(gameId, currentState, humanSeat, buildingInfo);

  const playerNames = useMemo(
    () => [0, 1, 2, 3].map((s) => playerName(s, humanSeat)),
    [humanSeat],
  );

  const onAction = useCallback(
    (id: number) => {
      const action = currentState?.legal_actions.find((a) => a.id === id);
      if (currentState) recordHumanAction(currentState, action?.label ?? "move");
      sendAction(id);
    },
    [currentState, recordHumanAction, sendAction],
  );

  // Click/drop a board element to act. Guarded by the same conditions as the
  // action prompt so a stray click during animation / an AI turn is ignored.
  const onBoardAction = useCallback(
    (id: number) => {
      if (
        isAnimating ||
        !currentState ||
        currentState.terminal ||
        !currentState.to_move_is_human
      ) {
        return;
      }
      if (!currentState.legal_actions.some((a) => a.id === id)) return;
      setHighlight(null);
      clearPreview();
      onAction(id);
    },
    [isAnimating, currentState, onAction, clearPreview],
  );

  // Hovering a clickable board element previews its action (same as a button).
  const onBoardHover = useCallback(
    (action: LegalAction | null) => {
      if (isAnimating) return;
      setHighlight(action ? highlightForAction(action) : null);
      onPreview(action);
    },
    [isAnimating, onPreview],
  );

  // Disable / clear preview while AI playback is animating.
  useEffect(() => {
    if (isAnimating) clearPreview();
  }, [isAnimating, clearPreview]);

  // Global keyboard shortcuts for AI playback. The human found AI pacing hard
  // to control with the mouse, so:
  //   Space — toggle Pause/Resume while animating; if paused with frames
  //           pending, Step one frame instead.
  //   →     — Step one AI frame (when frames pending).
  //   S     — Skip to the end of the current AI sequence.
  // Guarded so they never fire while typing in a form control, and cleaned up
  // on unmount.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target?.isContentEditable
      ) {
        return;
      }
      if (!isAnimating) return;

      if (e.code === "Space") {
        e.preventDefault();
        if (isPaused) {
          // Paused: step one frame if any remain, else resume.
          if (pendingCount > 0) step();
          else resume();
        } else {
          pause();
        }
      } else if (e.key === "ArrowRight") {
        if (pendingCount > 0) {
          e.preventDefault();
          step();
        }
      } else if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        skipToEnd();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isAnimating, isPaused, pendingCount, pause, resume, step, skipToEnd]);

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

  // Turn order for this round's role selection: clockwise from the governor.
  // orderNumberOf[seat] is the 1-based position (governor = 1).
  const numPlayers = view.players.length;
  const orderNumberOf: number[] = view.players.map((_, seat) => {
    const offset = (seat - view.governor + numPlayers) % numPlayers;
    return offset + 1;
  });

  const governorName = playerNames[view.governor] ?? `P${view.governor}`;
  const toMoveName =
    playerNames[view.current_player] ?? `P${view.current_player}`;

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
        <PlaybackBar
          active={isAnimating}
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
        <span className={"conn conn-" + status}>{status}</span>
        {error && <span className="error">{error}</span>}
      </header>

      <div className="game-layout">
        <main className="game-main">
          {/* Scrollable region: shared board + the human's large board. The
              action bar below is pinned and never scrolls out of view. */}
          <div className="game-main-scroll">
            <Board
              view={view}
              highlight={activeHighlight}
              governorName={governorName}
              toMoveName={toMoveName}
              onBuildingHover={setHighlightBuilding}
              legalActions={promptDisabled ? [] : currentState.legal_actions}
              onBoardAction={onBoardAction}
              onBoardHover={onBoardHover}
            />

            <PlayerBoard
              playerView={view.players[humanSeat]}
              seat={humanSeat}
              isHuman
              name={playerNames[humanSeat]}
              active={view.current_player === humanSeat}
              isGovernor={view.governor === humanSeat}
              orderNumber={orderNumberOf[humanSeat]}
              highlightBuilding={highlightBuilding}
              onBuildingHover={setHighlightBuilding}
              legalActions={promptDisabled ? [] : currentState.legal_actions}
              onBoardAction={onBoardAction}
            />
          </div>

          {/* Pinned action bar: always visible at the bottom of the left
              column. Its buttons wrap/scroll internally if there are many. */}
          <div className="game-action-bar">
            <ActionPrompt
              legalActions={currentState.legal_actions}
              onAction={onAction}
              disabled={promptDisabled}
              aiThinking={aiThinking}
              onHighlight={setHighlight}
              onPreview={onPreview}
              view={view}
            />
          </div>
        </main>

        <aside className="game-side">
          <Standings
            view={view}
            playerNames={playerNames}
            humanSeat={humanSeat}
          />
          <div className="opponents">
            {others.map((seat) => (
              <PlayerBoard
                key={seat}
                playerView={view.players[seat]}
                seat={seat}
                isHuman={false}
                name={playerNames[seat]}
                active={view.current_player === seat}
                isGovernor={view.governor === seat}
                orderNumber={orderNumberOf[seat]}
                highlightBuilding={highlightBuilding}
                onBuildingHover={setHighlightBuilding}
              />
            ))}
          </div>
          <Log entries={logEntries} playerNames={playerNames} />
        </aside>
      </div>

      {/* Floats at the top-right so it never overlaps the pinned action bar. */}
      <PreviewPanel
        label={previewLabel}
        diff={previewDiff}
        loading={previewLoading}
      />

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
