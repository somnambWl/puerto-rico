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

import { createGame, type Opponent } from "./api";
import { Board } from "./components/Board";
import { GameOver } from "./components/GameOver";
import { Log, type LogEntry } from "./components/Log";
import { PlayerBoard } from "./components/PlayerBoard";
import { ActionPrompt } from "./components/ActionPrompt";
import { useGameState } from "./hooks/useGameState";
import type { Highlight, StateMsg } from "./types";
import { PHASE_NAMES } from "./types";

interface GameSetup {
  gameId: string;
  humanSeat: number;
}

export default function App() {
  const [setup, setSetup] = useState<GameSetup | null>(null);

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

  return (
    <GameView
      gameId={setup.gameId}
      humanSeat={setup.humanSeat}
      onNewGame={() => setSetup(null)}
    />
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
  const { currentState, isAnimating, status, error, logFeed, sendAction } =
    useGameState(gameId);

  const [highlight, setHighlight] = useState<Highlight>(null);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);

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
            highlight={highlight}
            onPlantationClick={() => {
              /* visual highlight toggle handled via hover; click is a no-op
                 placeholder so the row reads as interactive */
            }}
          />

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
