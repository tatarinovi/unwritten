import type { ActionResponse, Dialogue, GameEvent, World } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    try {
      response = await fetch(path, init);
    } catch {
      throw new Error("Нет связи с сервером. Проверьте, что API запущен.");
    }
  }
  if (!response.ok) {
    let detail = "Сервер отклонил запрос.";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      detail = "Сервер не смог обработать запрос.";
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function resume(now: string): Promise<{ advanced_minutes: number; world: World }> {
  return post("/api/session/resume", { now });
}

export function world(): Promise<World> {
  return request<World>("/api/world");
}

export function events(): Promise<GameEvent[]> {
  return request<GameEvent[]>("/api/events?limit=80");
}

export function act(body: {
  action_id: string;
  type: "move" | "look" | "wait";
  params: Record<string, string | number>;
  now: string;
}): Promise<ActionResponse> {
  return post<ActionResponse>("/api/actions", body);
}

export function speak(body: {
  action_id: string;
  npc_id: string;
  reply_id?: string;
  now: string;
}): Promise<Dialogue> {
  return post<Dialogue>("/api/dialogue", body);
}
