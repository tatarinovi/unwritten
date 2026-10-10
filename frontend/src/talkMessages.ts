import type { DialogueMessage } from "./types";

let localId = -1;

export function mergeTalkMessages(
  current: DialogueMessage[],
  playerText: string,
  result: { line: string; source?: "llm" | "template"; messages?: DialogueMessage[] | null },
): DialogueMessage[] {
  const incoming = result.messages ?? [];
  const hasPlayer = incoming.some((message) => message.role === "player" && message.text === playerText);
  const hasReply = incoming.some((message) => message.role === "npc" && message.text === result.line);
  if (hasPlayer && hasReply) {
    return incoming;
  }
  const base = incoming.length >= current.length ? [...incoming] : [...current];
  if (!base.some((message) => message.role === "player" && message.text === playerText)) {
    base.push(localMessage("player", playerText, "player"));
  }
  if (result.line && !base.some((message) => message.role === "npc" && message.text === result.line)) {
    base.push(localMessage("npc", result.line, result.source ?? "llm"));
  }
  return base;
}

export function optimisticPlayerLine(text: string): DialogueMessage {
  return localMessage("player", text, "player");
}

function localMessage(
  role: "player" | "npc",
  text: string,
  source: DialogueMessage["source"],
): DialogueMessage {
  localId -= 1;
  return { id: localId, role, text, time: "", clock: "", source };
}
