export type Npc = {
  id: string;
  name: string;
  role: string;
  location_id: string;
  location_name: string;
  fatigue: number;
  fatigue_label: string;
  goal: string;
  current_action: string;
  action_label: string;
  traits: string[];
};

export type GameAction = {
  type: "move" | "look" | "wait" | "talk";
  label: string;
  params: Record<string, string | number>;
};

export type World = {
  time: string;
  day_label: string;
  seed: number;
  location: {
    id: string;
    name: string;
    description: string;
  };
  present_npcs: Npc[];
  npcs: Npc[];
  player: {
    id: string;
    name: string;
    role: string;
    fatigue: number;
    status_label: string;
    location_id: string;
    goal: string;
  };
  settlement: {
    name: string;
    summary: string;
    threat_level: number;
    threat_label: string;
    grid_condition: number;
    grid_label: string;
    market_stock: number;
    stock_label: string;
    workshop_parts: number;
  };
  available_actions: GameAction[];
};

export type GameEvent = {
  id: number;
  time: string;
  clock: string;
  kind: string;
  message: string;
  actor_id: string | null;
  data: Record<string, string | number | null>;
};

export type DialogueMessage = {
  id: number;
  role: "player" | "npc";
  text: string;
  time: string;
  clock: string;
  source: "player" | "llm" | "template";
};

export type Conversation = {
  npc_id: string;
  npc_name: string;
  role: string;
  speech: "llm" | "template";
  messages: DialogueMessage[];
};

export type Dialogue = {
  replayed: boolean;
  npc_id: string;
  npc_name: string;
  role?: string;
  line: string;
  options: { id: string; label: string }[];
  note: string | null;
  source?: "llm" | "template";
  messages?: DialogueMessage[];
  world: World;
};

export type ActionResponse = {
  replayed: boolean;
  detail: string;
  world: World;
};
