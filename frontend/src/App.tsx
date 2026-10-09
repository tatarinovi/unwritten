import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api";
import type { Dialogue, GameAction, GameEvent, World } from "./types";

function actionId(): string {
  return crypto.randomUUID();
}

export function App() {
  const [world, setWorld] = useState<World | null>(null);
  const [events, setEvents] = useState<GameEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogue, setDialogue] = useState<Dialogue | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const busyRef = useRef(false);
  const requestId = useRef(0);
  const worldTimeRef = useRef<string | null>(null);

  const loadWorld = useCallback(async (now?: string) => {
    const id = ++requestId.current;
    const stamp = now ?? new Date().toISOString();
    await api.resume(stamp);
    const [nextWorld, nextEvents] = await Promise.all([api.world(), api.events()]);
    if (id !== requestId.current) {
      return null;
    }
    setWorld(nextWorld);
    setEvents(nextEvents);
    return nextWorld;
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      setLoading(true);
      setLoadError(null);
      try {
        await loadWorld();
        if (!cancelled) {
          setLoading(false);
        }
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "Не удалось загрузить мир.");
          setLoading(false);
        }
      }
    }
    void boot();
    return () => {
      cancelled = true;
    };
  }, [loadWorld]);

  useEffect(() => {
    worldTimeRef.current = world?.time ?? null;
  }, [world]);

  useEffect(() => {
    const node = logRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [events]);

  useEffect(() => {
    function onVisible() {
      if (document.visibilityState !== "visible" || busyRef.current) {
        return;
      }
      const previous = worldTimeRef.current;
      void loadWorld()
        .then((next) => {
          if (previous && next && next.time !== previous) {
            setDialogue(null);
          }
        })
        .catch((error: unknown) => {
          setActionError(error instanceof Error ? error.message : "Не удалось обновить мир.");
        });
    }
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [loadWorld]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setDialogue(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function run(task: () => Promise<void>) {
    const id = ++requestId.current;
    busyRef.current = true;
    setBusy(true);
    setActionError(null);
    try {
      await task();
    } catch (error) {
      if (id === requestId.current) {
        setActionError(error instanceof Error ? error.message : "Действие не выполнено.");
      }
    } finally {
      if (id === requestId.current) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  }

  function applyWorld(next: World) {
    setWorld(next);
  }

  async function refreshEvents() {
    setEvents(await api.events());
  }

  function onAction(action: GameAction) {
    if (action.type === "talk") {
      const npcId = String(action.params.npc_id);
      void run(async () => {
        const result = await api.speak({
          action_id: actionId(),
          npc_id: npcId,
          now: new Date().toISOString(),
        });
        applyWorld(result.world);
        setDialogue(result);
        await refreshEvents();
      });
      return;
    }
    const kind = action.type;
    void run(async () => {
      const result = await api.act({
        action_id: actionId(),
        type: kind,
        params: action.params,
        now: new Date().toISOString(),
      });
      applyWorld(result.world);
      await refreshEvents();
    });
  }

  function onReply(replyId: string) {
    if (!dialogue) {
      return;
    }
    const npcId = dialogue.npc_id;
    void run(async () => {
      const result = await api.speak({
        action_id: actionId(),
        npc_id: npcId,
        reply_id: replyId,
        now: new Date().toISOString(),
      });
      applyWorld(result.world);
      setDialogue(result);
      await refreshEvents();
    });
  }

  if (loading) {
    return (
      <main className="screen-state">
        <p className="brand">UNWRITTEN</p>
        <p>Загрузка мира…</p>
      </main>
    );
  }

  if (loadError || !world) {
    return (
      <main className="screen-state">
        <p className="brand">UNWRITTEN</p>
        <p>{loadError ?? "Мир не загрузился."}</p>
        <button type="button" onClick={() => window.location.reload()}>
          Повторить
        </button>
      </main>
    );
  }

  const moves = world.available_actions.filter((action) => action.type === "move");
  const local = world.available_actions.filter((action) => action.type === "look" || action.type === "talk");
  const waits = world.available_actions.filter((action) => action.type === "wait");

  return (
    <div className="app">
      <header className="top">
        <div className="brand-block">
          <p className="brand">UNWRITTEN</p>
          <p className="version">v0.0.1</p>
        </div>
        <p className="when">{world.day_label}</p>
        <p className="where">{world.location.name}</p>
      </header>

      <div className="shell">
        <main className="stage" aria-busy={busy}>
          <section className="panel place">
            <p className="eyebrow">{world.settlement.name}</p>
            <h1>{world.location.name}</h1>
            <p className="description">{world.location.description}</p>
          </section>

          <section className="panel">
            <h2>Кто здесь</h2>
            <p className="hint">{world.settlement.summary}</p>
            {world.present_npcs.length === 0 ? (
              <p className="empty">Рядом никого, с кем можно говорить.</p>
            ) : (
              <ul className="people">
                {world.present_npcs.map((npc) => (
                  <li key={npc.id}>
                    <div>
                      <strong>{npc.name}</strong>
                      <span>{npc.role}</span>
                    </div>
                    <p>
                      {npc.action_label}. {npc.fatigue_label}.
                    </p>
                    <p className="goal">{npc.goal}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel">
            <h2>Действия</h2>
            {actionError ? (
              <p className="banner" role="alert">
                {actionError}
              </p>
            ) : null}
            <ActionGroup title="Куда идти" actions={moves} busy={busy} onAction={onAction} />
            <ActionGroup title="На месте" actions={local} busy={busy} onAction={onAction} />
            <ActionGroup title="Время" actions={waits} busy={busy} onAction={onAction} inline />
          </section>
        </main>

        <aside className="side">
          <section className="panel">
            <h2>Вы</h2>
            <p className="player-name">{world.player.name}</p>
            <p className="hint">{world.player.role}</p>
            <p>{world.player.status_label}</p>
            <div
              className="meter"
              role="meter"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={world.player.fatigue}
              aria-label={`Усталость ${world.player.fatigue} из 100`}
            >
              <span style={{ width: `${world.player.fatigue}%` }} />
            </div>
            <p className="hint">Усталость {world.player.fatigue} из 100</p>
            <p className="goal">{world.player.goal}</p>
          </section>

          <section className="panel">
            <h2>{world.settlement.name}</h2>
            <dl className="facts">
              <div>
                <dt>Угроза</dt>
                <dd>
                  {world.settlement.threat_label}
                  <span>{world.settlement.threat_level}</span>
                </dd>
              </div>
              <div>
                <dt>Сеть</dt>
                <dd>
                  {world.settlement.grid_label}
                  <span>{world.settlement.grid_condition}</span>
                </dd>
              </div>
              <div>
                <dt>Запас на рынке</dt>
                <dd>
                  {world.settlement.stock_label}
                  <span>{world.settlement.market_stock}</span>
                </dd>
              </div>
              <div>
                <dt>Детали в мастерской</dt>
                <dd>
                  <span>{world.settlement.workshop_parts}</span>
                </dd>
              </div>
            </dl>
            <ul className="whereabouts">
              {world.npcs.map((npc) => (
                <li key={npc.id}>
                  <strong>{npc.name}</strong>
                  <span>
                    {npc.location_name}, {npc.action_label}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section className="panel log-panel">
            <h2>Журнал</h2>
            <div className="log" ref={logRef}>
              {events.length === 0 ? <p className="empty">Пока пусто.</p> : null}
              <ul>
                {events.map((event) => (
                  <li key={event.id} className={event.kind.startsWith("npc_") ? "npc" : ""}>
                    <time dateTime={event.time}>{event.clock}</time>
                    <span>{event.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>
        </aside>
      </div>

      {dialogue ? (
        <div className="backdrop" onClick={() => setDialogue(null)}>
          <section
            className="dialogue"
            role="dialog"
            aria-modal="true"
            aria-labelledby="dialogue-name"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="eyebrow">Разговор</p>
            <h2 id="dialogue-name">{dialogue.npc_name}</h2>
            <p className="line">{dialogue.line}</p>
            {dialogue.note ? <p className="hint">{dialogue.note}</p> : null}
            <div className="replies">
              {dialogue.options.map((option) => (
                <button key={option.id} type="button" disabled={busy} onClick={() => onReply(option.id)}>
                  {option.label}
                </button>
              ))}
            </div>
            <button type="button" className="quiet" onClick={() => setDialogue(null)}>
              Закрыть
            </button>
          </section>
        </div>
      ) : null}
    </div>
  );
}

function ActionGroup({
  title,
  actions,
  busy,
  onAction,
  inline = false,
}: {
  title: string;
  actions: GameAction[];
  busy: boolean;
  onAction: (action: GameAction) => void;
  inline?: boolean;
}) {
  if (actions.length === 0) {
    return null;
  }
  return (
    <div className="group">
      <h3>{title}</h3>
      <div className={inline ? "row" : "stack"}>
        {actions.map((action) => (
          <button
            key={`${action.type}-${action.label}`}
            type="button"
            disabled={busy}
            onClick={() => onAction(action)}
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  );
}
