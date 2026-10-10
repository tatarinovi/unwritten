import { useEffect, useLayoutEffect, useState, useRef, type CSSProperties, type KeyboardEvent } from "react";
import type { DialogueMessage } from "./types";
import "./talk.css";

export function TalkWindow({
  npcId,
  name,
  role,
  location,
  settlement,
  messages,
  draft,
  pending,
  error,
  notice,
  onDraft,
  onSend,
  onRetry,
  onTemplate,
  onClose,
}: {
  npcId: string;
  name: string;
  role: string;
  location: string;
  settlement: string;
  messages: DialogueMessage[];
  draft: string;
  pending: boolean;
  error: string | null;
  notice: string | null;
  onDraft: (value: string) => void;
  onSend: () => void;
  onRetry: () => void;
  onTemplate: () => void;
  onClose: () => void;
}) {
  const transcriptRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stickToEnd = useRef(true);
  const portraitSrc = npcId ? `/portraits/${encodeURIComponent(npcId)}.jpg` : "";
  const [portraitReady, setPortraitReady] = useState(false);
  const [portraitFailed, setPortraitFailed] = useState(!portraitSrc);
  const canSend = draft.trim().length > 0 && !pending;
  const showPortrait = Boolean(portraitSrc) && !portraitFailed;
  const [presence, setPresence] = useState<"idle" | "listening" | "speaking">("idle");
  const wasPending = useRef(false);
  const who = labelCase(name);
  const mood = bearing(who, pending ? "listening" : presence, error);
  const plateMark = settlement.match(/\d+/)?.[0] ?? "";
  const path = [settlement, location].filter(Boolean).join(" / ");
  const wash = showPortrait ? ({ "--wash": `url("${portraitSrc}")` } as CSSProperties) : undefined;

  useEffect(() => {
    setPortraitReady(false);
    setPortraitFailed(!portraitSrc);
  }, [portraitSrc]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (pending) {
      wasPending.current = true;
      setPresence("listening");
      return;
    }
    if (!wasPending.current) {
      return;
    }
    wasPending.current = false;
    setPresence("speaking");
    const timer = window.setTimeout(() => setPresence("idle"), 720);
    return () => window.clearTimeout(timer);
  }, [pending]);

  useLayoutEffect(() => {
    const node = inputRef.current;
    if (!node) {
      return;
    }
    const style = getComputedStyle(node);
    const line = Number.parseFloat(style.lineHeight);
    const pad = Number.parseFloat(style.paddingTop) + Number.parseFloat(style.paddingBottom);
    const border = Number.parseFloat(style.borderTopWidth) + Number.parseFloat(style.borderBottomWidth);
    const min = line * 2 + pad + border;
    const max = line * 6 + pad + border;
    node.style.height = "auto";
    const full = node.scrollHeight;
    const next = Math.max(min, Math.min(full, max));
    node.style.height = `${next}px`;
    node.style.overflowY = full > max + 1 ? "auto" : "hidden";
  }, [draft]);

  useEffect(() => {
    const node = transcriptRef.current;
    if (!node) {
      return;
    }
    stickToEnd.current = true;
    const scroll = () => {
      if (!stickToEnd.current) {
        return;
      }
      node.scrollTop = node.scrollHeight;
    };
    const onScroll = () => {
      const distance = node.scrollHeight - node.clientHeight - node.scrollTop;
      stickToEnd.current = distance < 48;
    };
    scroll();
    const frame = requestAnimationFrame(scroll);
    const observer = new ResizeObserver(scroll);
    observer.observe(node);
    node.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      node.removeEventListener("scroll", onScroll);
    };
  }, [messages, pending, error]);

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canSend) {
        onSend();
      }
    }
  }

  return (
    <div className="backdrop" onClick={onClose}>
      <section
        className="dialogue talk"
        role="dialog"
        aria-modal="true"
        aria-labelledby="talk-name"
        aria-busy={pending}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="scene">
          <figure className="portrait" data-presence={pending ? "listening" : presence}>
            {showPortrait ? (
              <img
                src={portraitSrc}
                alt=""
                className={portraitReady ? "is-ready" : undefined}
                ref={(node) => {
                  if (node && node.complete && node.naturalWidth > 0) {
                    setPortraitReady(true);
                  }
                }}
                onLoad={() => setPortraitReady(true)}
                onError={() => setPortraitFailed(true)}
              />
            ) : null}
            <div className="veil" aria-hidden="true" />
            {plateMark ? (
              <span className="plate-mark" aria-hidden="true">
                {plateMark}
              </span>
            ) : null}
            <div className={showPortrait && portraitReady ? "fallback is-hidden" : "fallback"} aria-hidden="true">
              <PortraitMark />
              <span className="monogram">{monogram(name)}</span>
            </div>
            <figcaption className="plate-copy">
              {role ? <p className="role">{role}</p> : null}
              <h2 id="talk-name">{who}</h2>
              {location ? <p className="place">{labelCase(location)}</p> : null}
            </figcaption>
            <div className="mood">
              <MoodMark />
              <div>
                <p className="mood-title">{mood.title}</p>
                <p className="mood-line">{mood.line}</p>
              </div>
            </div>
          </figure>

          <div className="thread" style={wash}>
            <header className="thread-bar">
              <PlaceMark />
              <div>
                {path ? <p className="path">{path}</p> : null}
                <p className="kicker">Разговор</p>
              </div>
            </header>
            <div className="transcript" ref={transcriptRef} role="log" aria-live="polite" aria-relevant="additions">
              {messages.length === 0 && !pending && !error ? <p className="empty">Пока вы не говорили.</p> : null}
              <ul>
                {messages.map((message, index) => (
                  <li
                    key={message.id}
                    className={message.role === "player" ? "from-player" : "from-npc"}
                    data-settling={presence === "speaking" && index === messages.length - 1 ? "" : undefined}
                  >
                    <span className="who">{message.role === "player" ? "Вы" : who}</span>
                    {message.source === "template" ? <span className="tag">Заготовка</span> : null}
                    <p>{message.text}</p>
                  </li>
                ))}
                {pending ? (
                  <li className="from-npc is-waiting">
                    <span className="who">{who}</span>
                    <p>Подбирает слова.</p>
                  </li>
                ) : null}
                {error ? (
                  <li className="from-npc is-error">
                    <span className="who">{who}</span>
                    <p>{error}</p>
                    <div className="replies">
                      <button type="button" disabled={pending} onClick={onRetry}>
                        Повторить
                      </button>
                      <button type="button" disabled={pending} onClick={onTemplate}>
                        Сказать заготовкой
                      </button>
                    </div>
                  </li>
                ) : null}
              </ul>
              {notice ? <p className="hint">{notice}</p> : null}
            </div>
            <div className="composer">
              <div className="composer-main">
                <textarea
                  ref={inputRef}
                  rows={2}
                  value={draft}
                  placeholder="Что вы скажете?"
                  disabled={pending}
                  aria-label={`Реплика для ${who}`}
                  onChange={(event) => onDraft(event.target.value)}
                  onKeyDown={onKeyDown}
                />
                <button type="button" className="send" disabled={!canSend} onClick={onSend}>
                  Сказать
                  <ReturnMark />
                </button>
              </div>
              <div className="composer-foot">
                <p className="hint">
                  <InfoMark />
                  Enter — отправить · Shift+Enter — новая строка
                </p>
                <button type="button" className="close" onClick={onClose}>
                  Закрыть
                  <kbd>Esc</kbd>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function bearing(
  who: string,
  presence: "idle" | "listening" | "speaking",
  error: string | null,
): { title: string; line: string } {
  if (error) {
    return { title: `${who} молчит`, line: "Реплика не дошла." };
  }
  if (presence === "listening") {
    return { title: `${who} молчит`, line: "Подбирает слова." };
  }
  if (presence === "speaking") {
    return { title: `${who} отвечает`, line: "Слова нашлись." };
  }
  return { title: `${who} насторожен`, line: "Держится отстранённо, но готов говорить." };
}

function labelCase(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return trimmed;
  }
  return trimmed.charAt(0).toLocaleUpperCase("ru") + trimmed.slice(1);
}

function monogram(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return "·";
  }
  if (parts.length === 1) {
    return parts[0].slice(0, 1).toLocaleUpperCase("ru");
  }
  return (parts[0].slice(0, 1) + parts[1].slice(0, 1)).toLocaleUpperCase("ru");
}

function PortraitMark() {
  return (
    <svg className="silhouette" viewBox="0 0 120 160" focusable="false">
      <circle cx="60" cy="46" r="22" />
      <path d="M18 158c4-34 20-52 42-52s38 18 42 52" />
    </svg>
  );
}

function PlaceMark() {
  return (
    <svg className="place-mark" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path d="M4 20V9.2L12 4l8 5.2V20" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M10 20v-6h4v6" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function MoodMark() {
  return (
    <svg className="mood-mark" viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
      <path d="M12.2 3.1a6.6 6.6 0 1 0 4.4 11.4A5.7 5.7 0 0 1 12.2 3.1Z" fill="currentColor" />
    </svg>
  );
}

function ReturnMark() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path d="M13 3.5v4.2a2.3 2.3 0 0 1-2.3 2.3H4" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M6.4 7.2 3.6 10l2.8 2.8" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function InfoMark() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
      <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <path d="M8 7.2V11" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="8" cy="5.1" r="0.7" fill="currentColor" />
    </svg>
  );
}
