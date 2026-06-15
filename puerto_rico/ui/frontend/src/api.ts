/**
 * REST helpers for the UI backend.
 *
 * - POST /games -> { game_id, state }
 * - GET  /games/{id} -> StateMsg
 *
 * Requests go to relative paths so Vite's dev proxy (vite.config.ts) forwards
 * them to the FastAPI backend on :8000.
 */

import type { StateMsg } from "./types";

export type Opponent = "heuristic" | "rl";

export interface NewGameOpts {
  seed?: number;
  human_seat?: number;
  difficulty?: string;
}

export interface NewGameResponse {
  game_id: string;
  state: StateMsg;
}

/** POST /games — create a new game and return its id + initial state. */
export async function createGame(
  opponent: Opponent,
  opts: NewGameOpts = {},
): Promise<NewGameResponse> {
  const body: Record<string, unknown> = { opponent };
  if (opts.seed !== undefined) body.seed = opts.seed;
  if (opts.human_seat !== undefined) body.human_seat = opts.human_seat;
  if (opts.difficulty !== undefined) body.difficulty = opts.difficulty;

  const res = await fetch("/games", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`createGame failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as NewGameResponse;
}

/** GET /games/{id} — current state (reconnect / refresh). */
export async function getState(gameId: string): Promise<StateMsg> {
  const res = await fetch(`/games/${gameId}`);
  if (!res.ok) {
    throw new Error(`getState failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as StateMsg;
}
