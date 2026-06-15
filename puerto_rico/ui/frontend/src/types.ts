/**
 * TypeScript mirror of the backend wire protocol
 * (puerto_rico/ui/backend/schemas.py) and the engine public_view
 * (puerto_rico/engine/serialize.py :: public_view).
 *
 * The backend is authoritative: every field here matches a field the server
 * sends. The display-name maps near the bottom mirror the engine enums
 * (enums.py) and the buildings CATALOG (buildings.py) so the renderer can show
 * human-readable names without re-deriving any rules.
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

/** BuildingId enum -> { name, cost, vp, large } (buildings.py :: CATALOG). */
export interface BuildingMeta {
  name: string;
  cost: number;
  vp: number;
  /** Large beige building (column 4): spans two city slots. */
  large: boolean;
}

export const LARGE_CONT = 99;

export const BUILDINGS: Record<number, BuildingMeta> = {
  // production buildings
  0: { name: "Small Indigo Plant", cost: 1, vp: 1, large: false },
  1: { name: "Indigo Plant", cost: 3, vp: 2, large: false },
  2: { name: "Small Sugar Mill", cost: 2, vp: 1, large: false },
  3: { name: "Sugar Mill", cost: 4, vp: 2, large: false },
  4: { name: "Tobacco Storage", cost: 5, vp: 3, large: false },
  5: { name: "Coffee Roaster", cost: 6, vp: 3, large: false },
  // small beige buildings
  6: { name: "Small Market", cost: 1, vp: 1, large: false },
  7: { name: "Hacienda", cost: 2, vp: 1, large: false },
  8: { name: "Construction Hut", cost: 2, vp: 1, large: false },
  9: { name: "Small Warehouse", cost: 3, vp: 1, large: false },
  10: { name: "Hospice", cost: 4, vp: 2, large: false },
  11: { name: "Office", cost: 5, vp: 2, large: false },
  12: { name: "Large Market", cost: 5, vp: 2, large: false },
  13: { name: "Large Warehouse", cost: 6, vp: 2, large: false },
  14: { name: "Factory", cost: 7, vp: 3, large: false },
  15: { name: "University", cost: 8, vp: 3, large: false },
  16: { name: "Harbor", cost: 8, vp: 3, large: false },
  17: { name: "Wharf", cost: 9, vp: 3, large: false },
  // large beige buildings (span two slots)
  18: { name: "Guild Hall", cost: 10, vp: 4, large: true },
  19: { name: "Residence", cost: 10, vp: 4, large: true },
  20: { name: "Fortress", cost: 10, vp: 4, large: true },
  21: { name: "Customs House", cost: 10, vp: 4, large: true },
  22: { name: "City Hall", cost: 10, vp: 4, large: true },
};

export function buildingName(id: number | null): string {
  if (id === null) return "";
  if (id === LARGE_CONT) return "";
  return BUILDINGS[id]?.name ?? `building ${id}`;
}

// --------------------------------------------------------------------------- //
// Highlight model (Board <- ActionPrompt hover)                                //
// --------------------------------------------------------------------------- //

/** A best-effort highlight signalled from a hovered action to the Board. */
export type Highlight =
  | { kind: "plantation"; index: number }
  | { kind: "building"; buildingId: number }
  | { kind: "ship"; index: number }
  | { kind: "role"; role: number }
  | { kind: "good"; good: number }
  | null;
