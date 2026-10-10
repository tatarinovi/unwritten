import assert from "node:assert/strict";
import test from "node:test";
import { mergeTalkMessages } from "./src/talkMessages.ts";

test("server history that already contains the exchange replaces the open transcript", () => {
  const older = [
    { id: 1, role: "player" as const, text: "Старое", time: "", clock: "", source: "player" as const },
    { id: 2, role: "npc" as const, text: "Ответ", time: "", clock: "", source: "llm" as const },
  ];
  const incoming = [
    ...older,
    { id: 3, role: "player" as const, text: "Новая", time: "", clock: "", source: "player" as const },
    { id: 4, role: "npc" as const, text: "Слышу", time: "", clock: "", source: "llm" as const },
  ];
  const merged = mergeTalkMessages(older, "Новая", { line: "Слышу", source: "llm", messages: incoming });
  assert.deepEqual(merged, incoming);
});

test("a stale list does not swallow the reply that just succeeded", () => {
  const older = [
    { id: 1, role: "player" as const, text: "Старое", time: "", clock: "", source: "player" as const },
    { id: 2, role: "npc" as const, text: "Ответ", time: "", clock: "", source: "llm" as const },
  ];
  const merged = mergeTalkMessages(older, "Новая", { line: "Слышу", source: "llm", messages: older });
  assert.equal(merged.at(-2)?.text, "Новая");
  assert.equal(merged.at(-1)?.text, "Слышу");
  assert.equal(merged.at(-1)?.source, "llm");
  assert.equal(merged[0]?.text, "Старое");
});
