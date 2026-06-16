/**
 * GameOver — modal shown when the state is terminal.
 *
 * Reads `result` (Result from session.py :: _result): per-player `final_score`
 * with its components (`vp_chips`, `building_vp` = building VP + large-building
 * bonus), `winner`, and `ranking`. Players are sorted by final score
 * descending; the winner row is highlighted.
 */

import { createPortal } from "react-dom";

import type { Result } from "../types";
import { GOOD_COLORS, GOOD_NAMES } from "../types";

interface GameOverProps {
  result: Result;
  playerNames: string[];
  onNewGame: () => void;
}

export function GameOver({ result, playerNames, onNewGame }: GameOverProps) {
  const sorted = [...result.players].sort(
    (a, b) => b.final_score - a.final_score,
  );

  // Render via a portal to document.body so the viewport shell (`.game`, which
  // is `overflow:hidden`) can neither clip nor cover the fixed overlay. The
  // overlay's high z-index keeps it above all in-game UI.
  return createPortal(
    <div className="modal-overlay">
      <div className="modal">
        <h2>Game over</h2>
        <div className="winner-line">
          Winner: <strong>{playerNames[result.winner] ?? `P${result.winner}`}</strong>
        </div>
        <table className="score-table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Total</th>
              <th>VP chips</th>
              <th>Building VP</th>
              <th>$</th>
              <th>Goods</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((p) => (
              <tr
                key={p.seat}
                className={p.seat === result.winner ? "winner-row" : ""}
              >
                <td>{playerNames[p.seat] ?? `P${p.seat}`}</td>
                <td className="score-total">{p.final_score}</td>
                <td>{p.vp_chips}</td>
                <td>{p.building_vp}</td>
                <td>{p.doubloons}</td>
                <td>
                  <span className="goods-mini">
                    {p.goods.map((n, g) =>
                      n > 0 ? (
                        <span
                          key={g}
                          className="good-inv"
                          title={GOOD_NAMES[g]}
                        >
                          <span
                            className="good-dot"
                            style={{ background: GOOD_COLORS[g] }}
                          />
                          {n}
                        </span>
                      ) : null,
                    )}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button className="action-btn" onClick={onNewGame}>
          New game
        </button>
      </div>
    </div>,
    document.body,
  );
}
