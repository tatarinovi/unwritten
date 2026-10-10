import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api";
import { TalkWindow } from "./TalkWindow";
import { mergeTalkMessages, optimisticPlayerLine } from "./talkMessages";
import type { Dialogue, DialogueMessage, GameAction, GameEvent, Npc, World } from "./types";
import "./home.css";

/* Swap a file by editing a path. Keys are world ids. A missing key leaves an empty plate.
   page-backdrop uses BACKDROP_ART. location-hero and move-* use LOCATION_ART.
   portrait-* uses PORTRAIT_ART. */
const LOCATION_ART: Record<string, string> = {
  city_gates: "/locations/city-gates.jpg",
  market: "/locations/market.jpg",
  workshop: "/locations/workshop.jpg",
};

const PORTRAIT_ART: Record<string, string> = {
  ivar: "/portraits/ivar.jpg",
  marek: "/portraits/marek.jpg",
  eyra: "/portraits/eyra.jpg",
};

const BACKDROP_ART = "/locations/district.jpg";

type TalkSession = {
  npcId: string;
  name: string;
  role: string;
  location: string;
  messages: DialogueMessage[];
  draft: string;
  pending: boolean;
  error: string | null;
  notice: string | null;
  requestId: string | null;
  sent: string | null;
};

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
  const [talk, setTalk] = useState<TalkSession | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const busyRef = useRef(false);
  const requestId = useRef(0);
  const worldTimeRef = useRef<string | null>(null);
  const talkDismissed = useRef(false);
  const closeTalkRef = useRef<() => void>(() => {});

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
        closeTalkRef.current();
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

  function closeTalk() {
    talkDismissed.current = true;
    setTalk(null);
  }
  closeTalkRef.current = closeTalk;

  useEffect(() => {
    if (!world) {
      return;
    }
    setTalk((current) => {
      if (!current) {
        return current;
      }
      const npc = world.npcs.find((item) => item.id === current.npcId);
      if (!npc) {
        return current;
      }
      if (npc.location_name === current.location && npc.name === current.name && npc.role === current.role) {
        return current;
      }
      return { ...current, location: npc.location_name, name: npc.name, role: npc.role };
    });
  }, [world]);

  async function openTalk(npcId: string) {
    setDialogue(null);
    setActionError(null);
    talkDismissed.current = false;
    const place = world?.npcs.find((item) => item.id === npcId)?.location_name ?? world?.location.name ?? "";
    try {
      const body = await api.conversation(npcId);
      if (talkDismissed.current) {
        return;
      }
      setTalk({
        npcId: body.npc_id,
        name: body.npc_name,
        role: body.role,
        location: place,
        messages: body.messages,
        draft: "",
        pending: false,
        error: null,
        notice: null,
        requestId: null,
        sent: null,
      });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Разговор не открылся.");
    }
  }

  async function sendTalk(useTemplate: boolean, retry = false) {
    if (!talk || busyRef.current) {
      return;
    }
    const text = (retry ? talk.sent ?? "" : talk.draft).trim();
    if (!text) {
      return;
    }
    const npcId = talk.npcId;
    const action_id = retry && talk.requestId ? talk.requestId : actionId();
    busyRef.current = true;
    setBusy(true);
    setActionError(null);
    setTalk((current) => {
      if (!current || current.npcId !== npcId) {
        return current;
      }
      const last = current.messages.at(-1);
      const already = retry && last?.role === "player" && last.text === text;
      return {
        ...current,
        messages: already ? current.messages : [...current.messages, optimisticPlayerLine(text)],
        draft: "",
        pending: true,
        error: null,
        notice: null,
        requestId: action_id,
        sent: text,
      };
    });
    try {
      const result = await api.speak({
        action_id,
        npc_id: npcId,
        text,
        use_template: useTemplate,
        now: new Date().toISOString(),
      });
      applyWorld(result.world);
      const place = result.world.npcs.find((item) => item.id === npcId)?.location_name ?? "";
      setTalk((current) => {
        if (talkDismissed.current) {
          return current;
        }
        const messages = mergeTalkMessages(current?.messages ?? [], text, result);
        const base: TalkSession =
          current && current.npcId === npcId
            ? current
            : {
                npcId,
                name: result.npc_name,
                role: result.role ?? "",
                location: place,
                messages,
                draft: "",
                pending: false,
                error: null,
                notice: result.note,
                requestId: null,
                sent: null,
              };
        return {
          ...base,
          name: result.npc_name || base.name,
          role: result.role || base.role,
          location: place || base.location,
          messages,
          pending: false,
          error: null,
          notice: result.note,
          requestId: null,
          sent: null,
          draft: "",
        };
      });
      try {
        await refreshEvents();
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "Журнал не обновился.");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Реплика не дошла.";
      const shown = `${message} Строка осталась в разговоре.`;
      setTalk((current) => {
        if (!current || current.npcId !== npcId || talkDismissed.current) {
          return current;
        }
        return { ...current, pending: false, error: shown, requestId: action_id, draft: "" };
      });
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  function onAction(action: GameAction) {
    if (action.type === "talk" && action.params.dialogue === "llm") {
      void openTalk(String(action.params.npc_id));
      return;
    }
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
  const hero = LOCATION_ART[world.location.id];
  const fatigue = clampPercent(world.player.fatigue);
  const placeDescription = world.location.description.trim();

  return (
    <>
      <div className="home-backdrop" data-slot="page-backdrop" aria-hidden="true">
        <img src={BACKDROP_ART} alt="" />
      </div>
      <div className="home">
        <header className="home-top">
          <div className="home-brand">
            <p className="home-word">UNWRITTEN</p>
            <p className="home-version">v0.0.3</p>
          </div>
          <p className="home-when">{world.day_label}</p>
          <p className="home-where">
            <Pin />
            {world.location.name}
          </p>
        </header>

        <main className="home-board" aria-busy={busy}>
          <section className="home-world" aria-labelledby="home-place-name">
            <div className="home-hero" data-slot="location-hero" data-location={world.location.id}>
              {hero ? <img src={hero} alt="" /> : null}
              <div className="home-hero-shade" />
            </div>
            <div className="home-world-copy">
              <p className="home-kicker">{world.settlement.name}</p>
              <h1 id="home-place-name">{world.location.name}</h1>
              {placeDescription ? <p className="home-prose">{placeDescription}</p> : null}
            </div>
          </section>

          <section className="home-interact" aria-label="Рядом">
            <div className="home-block">
              <h2>Люди рядом</h2>
              {world.present_npcs.length === 0 ? (
                <p className="home-empty">Рядом никого, с кем можно говорить.</p>
              ) : (
                <ul className="home-people">
                  {world.present_npcs.map((npc) => (
                    <PresentPerson
                      key={npc.id}
                      npc={npc}
                      talk={local.find((action) => action.type === "talk" && String(action.params.npc_id) === npc.id)}
                      busy={busy}
                      onAction={onAction}
                    />
                  ))}
                </ul>
              )}
            </div>
            <div className="home-block">
              <h2>Действия</h2>
              {actionError ? (
                <p className="home-alert" role="alert">
                  {actionError}
                </p>
              ) : null}
              <ActionGroup title="Перемещение" actions={moves} busy={busy} onAction={onAction} />
              <ActionGroup title="На месте" actions={local} busy={busy} onAction={onAction} />
              <ActionGroup title="Время" actions={waits} busy={busy} onAction={onAction} />
            </div>
          </section>

          <aside className="home-info" aria-label="Сведения">
            <section className="home-block home-player">
              <p className="home-kicker">Вы</p>
              <h2>{world.player.name}</h2>
              {world.player.role.trim() ? <p className="home-quiet">{world.player.role}</p> : null}
              {world.player.status_label.trim() ? <p className="home-quiet">{world.player.status_label}</p> : null}
              {typeof world.player.fatigue === "number" ? (
                <>
                  <div
                    className="home-meter"
                    role="meter"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={fatigue}
                    aria-label={`Усталость ${fatigue} из 100`}
                  >
                    <span style={{ width: `${fatigue}%` }} />
                  </div>
                  <p className="home-quiet">Усталость {fatigue} из 100</p>
                </>
              ) : null}
              {world.player.goal.trim() ? <p className="home-goal">{world.player.goal}</p> : null}
            </section>

            <section className="home-block">
              <h2>{world.settlement.name}</h2>
              {world.settlement.summary.trim() ? (
                <p className="home-quiet home-summary">{world.settlement.summary}</p>
              ) : null}
              <dl className="home-facts">
                <Fact label="Угроза" note={world.settlement.threat_label} value={world.settlement.threat_level} />
                <Fact label="Сеть" note={world.settlement.grid_label} value={world.settlement.grid_condition} />
                <Fact label="Запас на рынке" note={world.settlement.stock_label} value={world.settlement.market_stock} />
                <Fact label="Детали в мастерской" value={world.settlement.workshop_parts} />
              </dl>
              {world.npcs.length > 0 ? (
                <ul className="home-who">
                  {world.npcs.map((npc) => (
                    <li key={npc.id}>
                      <strong>{npc.name}</strong>
                      <span>
                        {npc.location_name}, {npc.action_label}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>

            <section className="home-block">
              <h2>Журнал</h2>
              <div className="home-log" ref={logRef}>
                {events.length === 0 ? <p className="home-empty">Пока пусто.</p> : null}
                <ul>
                  {events.map((event) => (
                    <li key={event.id}>
                      <time dateTime={event.time}>{event.clock}</time>
                      <span>{event.message}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          </aside>
        </main>
      </div>

      {talk || dialogue ? (
        <div className="home-front">
          {talk ? (
            <TalkWindow
              npcId={talk.npcId}
              name={talk.name}
              role={talk.role}
              location={talk.location}
              settlement={world.settlement.name}
              messages={talk.messages}
              draft={talk.draft}
              pending={talk.pending}
              error={talk.error}
              notice={talk.notice}
              onDraft={(value) => setTalk((current) => (current ? { ...current, draft: value } : current))}
              onSend={() => void sendTalk(false)}
              onRetry={() => void sendTalk(false, true)}
              onTemplate={() => void sendTalk(true, true)}
              onClose={closeTalk}
            />
          ) : null}
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
      ) : null}
    </>
  );
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(value)));
}

function Fact({ label, note, value }: { label: string; note?: string; value?: number }) {
  const text = note?.trim() ?? "";
  if (!text && typeof value !== "number") {
    return null;
  }
  return (
    <div className="home-fact">
      <dt>{label}</dt>
      {text ? <dd className="home-note">{text}</dd> : null}
      {typeof value === "number" ? <dd className="home-num">{value}</dd> : null}
    </div>
  );
}

function PresentPerson({
  npc,
  talk,
  busy,
  onAction,
}: {
  npc: Npc;
  talk: GameAction | undefined;
  busy: boolean;
  onAction: (action: GameAction) => void;
}) {
  const body = (
    <>
      <Portrait npc={npc} />
      <span>
        <p className="home-person-name">{npc.name}</p>
        {npc.role.trim() ? <p className="home-person-role">{npc.role}</p> : null}
        <p className="home-person-status">{[npc.action_label, npc.fatigue_label].filter(Boolean).join(", ")}</p>
        {npc.goal.trim() ? <p className="home-person-status">{npc.goal}</p> : null}
      </span>
    </>
  );
  return (
    <li>
      {talk ? (
        <button type="button" className="home-person" disabled={busy} onClick={() => onAction(talk)}>
          {body}
          <Chevron />
        </button>
      ) : (
        <div className="home-person">{body}</div>
      )}
    </li>
  );
}

function Portrait({ npc }: { npc: Npc }) {
  const src = PORTRAIT_ART[npc.id];
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <span className="home-portrait home-portrait-fallback" data-slot={`portrait-${npc.id}`} aria-hidden="true">
        {npc.name.slice(0, 1)}
      </span>
    );
  }
  return (
    <img
      className="home-portrait"
      src={src}
      alt=""
      data-slot={`portrait-${npc.id}`}
      onError={() => setFailed(true)}
    />
  );
}

function ActionGroup({
  title,
  actions,
  busy,
  onAction,
}: {
  title: string;
  actions: GameAction[];
  busy: boolean;
  onAction: (action: GameAction) => void;
}) {
  if (actions.length === 0) {
    return null;
  }
  return (
    <div className="home-group">
      <h3>{title}</h3>
      <div className="home-actions">
        {actions.map((action) => (
          <ActionButton key={`${action.type}-${action.label}`} action={action} busy={busy} onAction={onAction} />
        ))}
      </div>
    </div>
  );
}

function ActionButton({
  action,
  busy,
  onAction,
}: {
  action: GameAction;
  busy: boolean;
  onAction: (action: GameAction) => void;
}) {
  const destination = action.type === "move" ? action.params.location_id : undefined;
  const art = typeof destination === "string" ? LOCATION_ART[destination] : undefined;
  const slot =
    action.type === "move"
      ? `move-${String(destination)}`
      : action.type === "talk"
        ? `talk-${String(action.params.npc_id)}`
        : action.type === "wait"
          ? `wait-${String(action.params.minutes)}`
          : "look";
  return (
    <button type="button" className="home-action" data-slot={slot} disabled={busy} onClick={() => onAction(action)}>
      {art ? (
        <span className="home-thumb" aria-hidden="true">
          <img src={art} alt="" />
        </span>
      ) : null}
      <span className="home-action-label">{action.label}</span>
      <Chevron />
    </button>
  );
}

function Chevron() {
  return (
    <svg className="home-chevron" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Pin() {
  return (
    <svg className="home-pin" viewBox="0 0 16 16" width="15" height="15" aria-hidden="true">
      <path
        d="M8 14.2s4.2-3.7 4.2-7.1A4.2 4.2 0 0 0 8 2.9a4.2 4.2 0 0 0-4.2 4.2c0 3.4 4.2 7.1 4.2 7.1Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="8" cy="7.1" r="1.35" fill="currentColor" />
    </svg>
  );
}
