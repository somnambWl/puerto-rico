/**
 * TypeScript mirror of the backend wire protocol
 * (puerto_rico/ui/backend/schemas.py) and the engine public_view
 * (puerto_rico/engine/serialize.py :: public_view).
 *
 * The backend is authoritative: every field here matches a field the server
 * sends. The display-name maps near the bottom mirror the engine enums
 * (enums.py) so the renderer can show human-readable names without re-deriving
 * any rules. Building metadata (names, costs, VP, capacity) is NOT duplicated
 * here: /catalog is the single source of truth (see catalog.tsx).
 */

// --------------------------------------------------------------------------- //
// Wire protocol (schemas.py)                                                   //
// --------------------------------------------------------------------------- //

/** One legal action offered to the human (LegalActionMsg). */
export interface LegalAction {
  id: number;
  label: string;
  /** Coarse category for grouping: role/tile/build/colonist/sell/ship/choose/pass. */
  kind: string;
}

/** Per-player final score breakdown (Result.players entry). */
export interface ResultPlayer {
  seat: number;
  final_score: number;
  vp_chips: number;
  /** Everything above the chips: building VP + large-building bonus. */
  building_vp: number;
  doubloons: number;
  goods: number[];
}

/** Terminal result (Result). */
export interface Result {
  scores: number[];
  ranking: number[];
  winner: number;
  players: ResultPlayer[];
}

/** A full snapshot from the human's perspective (StateMsg). */
export interface StateMsg {
  view: GameView;
  legal_actions: LegalAction[];
  to_move: number;
  to_move_is_human: boolean;
  terminal: boolean;
  result: Result | null;
  /** True for hypothetical frames from POST /games/{id}/preview. */
  preview?: boolean;
}

// --------------------------------------------------------------------------- //
// Catalog (/catalog) — static reference data (backend catalog.py)              //
// --------------------------------------------------------------------------- //

/** One building entry from /catalog. */
export interface CatalogBuilding {
  id: number;
  name: string;
  cost: number;
  column: number;
  vp: number;
  capacity: number;
  is_large: boolean;
  is_production: boolean;
  produces: string | null;
  /** "production" | "large" | "small". */
  kind: string;
  description: string;
}

/** One good entry from /catalog (base sell value). */
export interface CatalogGood {
  good: number; // Good
  name: string;
  base_value: number;
}

export interface Catalog {
  buildings: CatalogBuilding[];
  goods: CatalogGood[];
}

/** Client -> server: chosen action id (ActionMsg). */
export interface ActionMsg {
  action_id: number;
}

// --- WebSocket frame discriminated union (server -> client) --------------- //

export interface StateFrame extends StateMsg {
  type: "state";
}

export interface SequenceFrame {
  type: "sequence";
  states: StateMsg[];
}

export interface ErrorFrame {
  type: "error";
  message: string;
}

export type ServerFrame = StateFrame | SequenceFrame | ErrorFrame;

// --------------------------------------------------------------------------- //
// public_view shape (serialize.py :: public_view)                              //
// --------------------------------------------------------------------------- //

export interface GameConfigView {
  num_players: number;
  seed: number;
  ruleset: string;
}

/** One island slot (_island_to_dict): tile type + whether a colonist staffs it. */
export interface IslandSlot {
  tile: number; // TileType
  colonist: boolean;
}

/** One city building slot (_city_to_dict). */
export interface CitySlot {
  building: number | null; // BuildingId | null (LARGE_CONT == 99)
  colonists: number;
}

/** A cargo ship (_cargo_to_dict). */
export interface CargoShip {
  capacity: number;
  good: number | null; // Good | null
  count: number;
}

/** A role placard (_placard_to_dict). */
export interface Placard {
  role: number; // Role
  doubloons: number;
  taken_by: number | null;
}

/** One player's public state (_player_public). vp_chips is null for opponents. */
export interface PlayerView {
  doubloons: number;
  island: IslandSlot[];
  city: CitySlot[];
  goods: number[]; // length-5, indexed by Good
  stored_colonists: number;
  vp_chips: number | null;
  roles_taken_this_round: number;
}

/** The phase-specific sub-state (_phase_state_to_dict). */
export interface PhaseStateView {
  role_chooser: number;
  active_role: number | null; // Role | null
  order: number[];
  order_pos: number;
  colonists_to_place: number;
  captain_done: number[];
  sub: Record<string, unknown>;
}

/** The full public view (public_view). */
export interface GameView {
  config: GameConfigView;
  players: PlayerView[];
  perspective: number | null;
  governor: number;
  current_player: number;
  phase: number; // Phase
  placards: Placard[];
  colonist_ship: number;
  colonist_supply: number;
  cargo_ships: CargoShip[];
  trading_house: number[]; // list of Good values currently in the house
  goods_supply: number[]; // length-5, remaining supply per good
  plantation_faceup: number[]; // TileType values
  plantation_facedown_count: number;
  plantation_discard: number[];
  quarry_supply: number;
  vp_chips_remaining: number;
  buildings_supply: Record<string, number>; // BuildingId(str) -> remaining count
  phase_state: PhaseStateView;
  end_triggered: boolean;
}

// --------------------------------------------------------------------------- //
// Display maps (mirror engine enums + buildings CATALOG)                       //
// --------------------------------------------------------------------------- //

/** Good enum -> display name (enums.py :: Good). */
export const GOOD_NAMES: Record<number, string> = {
  0: "corn",
  1: "indigo",
  2: "sugar",
  3: "tobacco",
  4: "coffee",
};

export const GOOD_COLORS: Record<number, string> = {
  0: "#e6c200", // corn - yellow
  1: "#3a5fcd", // indigo - blue
  2: "#f5f5f5", // sugar - white
  3: "#8b5a2b", // tobacco - brown
  4: "#5a3a22", // coffee - dark brown
};

/** Role enum -> display name (enums.py :: Role). */
export const ROLE_NAMES: Record<number, string> = {
  0: "Settler",
  1: "Mayor",
  2: "Builder",
  3: "Craftsman",
  4: "Trader",
  5: "Captain",
  6: "Prospector",
};

/** TileType enum -> display name (enums.py :: TileType). */
export const TILE_NAMES: Record<number, string> = {
  0: "empty",
  1: "quarry",
  2: "corn",
  3: "indigo",
  4: "sugar",
  5: "tobacco",
  6: "coffee",
};

export const TILE_COLORS: Record<number, string> = {
  0: "#2b2b2b",
  1: "#9a9a9a", // quarry - grey
  2: "#e6c200", // corn
  3: "#3a5fcd", // indigo
  4: "#f5f5f5", // sugar
  5: "#8b5a2b", // tobacco
  6: "#5a3a22", // coffee
};

/** Phase enum -> display name (enums.py :: Phase). */
export const PHASE_NAMES: Record<number, string> = {
  0: "Role selection",
  1: "Settler",
  2: "Mayor",
  3: "Builder",
  4: "Craftsman",
  5: "Trader",
  6: "Captain",
  7: "Game over",
};

/**
 * BuildingId sentinel for the second slot of a placed large building (column 4
 * buildings span two city slots; the continuation slot carries this id).
 */
export const LARGE_CONT = 99;

// --------------------------------------------------------------------------- //
// Highlight model (Board <- ActionPrompt hover)                                //
// --------------------------------------------------------------------------- //

/**
 * A best-effort highlight signalled from a hovered action to the Board.
 * `ghost: true` marks a preview highlight (rendered as a dashed/ghost outline).
 */
export type Highlight =
  | { kind: "plantation"; index: number; ghost?: boolean }
  | { kind: "building"; buildingId: number; ghost?: boolean }
  | { kind: "ship"; index: number; ghost?: boolean }
  | { kind: "role"; role: number; ghost?: boolean }
  | { kind: "good"; good: number; ghost?: boolean }
  | null;
