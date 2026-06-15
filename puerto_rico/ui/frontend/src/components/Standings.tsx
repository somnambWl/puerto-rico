/**
 * Standings — live, compact leaderboard.
 *
 * VP is public during the game (view.players[].score is the current total VP if
 * the game ended now), so we can show who is winning at a glance. Players are
 * sorted by `score` descending; the leader is highlighted and the human's row
 * is marked "You". Updates every frame as the view changes.
 */

import type { GameView } from "../types";

interface StandingsProps {
  view: GameView;
  playerNames: string[];
  humanSeat: number;
}

export function Standings({ view, playerNames, humanSeat }: StandingsProps) {
  const rows = view.players
    .map((p, seat) => ({
      seat,
      name: playerNames[seat] ?? `P${seat}`,
      score: p.score,
      doubloons: p.doubloons,
    }))
    .sort((a, b) => b.score - a.score);

  const leaderScore = rows.length > 0 ? rows[0].score : 0;

  return (
    <div className="standings">
      <h3>Standings</h3>
      <table className="standings-table">
        <tbody>
          {rows.map((r) => {
            const isLeader = r.score === leaderScore;
            return (
              <tr
                key={r.seat}
                className={
                  (isLeader ? "standings-leader " : "") +
                  (r.seat === humanSeat ? "standings-you" : "")
                }
              >
                <td className="standings-name">
                  {r.name}
                  {r.seat === humanSeat && (
                    <span className="standings-you-tag">You</span>
                  )}
                </td>
                <td className="standings-score" title="Victory points">
                  {r.score} VP
                </td>
                <td className="standings-db" title="Doubloons">
                  {r.doubloons}$
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
