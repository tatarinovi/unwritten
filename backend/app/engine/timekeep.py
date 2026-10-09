from __future__ import annotations

from datetime import datetime, timedelta, timezone

GAME_START = datetime(2061, 4, 12, 8, 0, 0)
MOVE_MINUTES = 10
TALK_MINUTES = 5
TICK_MINUTES = 10
MAX_ABSENCE_MINUTES = 24 * 60

MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

MONTHS_SHORT = (
    "янв",
    "фев",
    "мар",
    "апр",
    "мая",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
)


def format_iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def parse_game_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def format_day_label(moment: datetime) -> str:
    month = MONTHS[moment.month - 1]
    return f"{moment.day} {month} {moment.year}, {moment:%H:%M}"


def format_clock(moment: datetime) -> str:
    month = MONTHS_SHORT[moment.month - 1]
    return f"{moment.day} {month}, {moment:%H:%M}"


def ensure_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        aware = moment.replace(tzinfo=timezone.utc)
    else:
        aware = moment.astimezone(timezone.utc)
    return aware.replace(microsecond=0)


def dump_real(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    return ensure_utc(moment).isoformat()


def load_real(value: str | None) -> datetime | None:
    if not value:
        return None
    return ensure_utc(datetime.fromisoformat(value))


def minutes_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def add_minutes(moment: datetime, minutes: int) -> datetime:
    return moment + timedelta(minutes=minutes)


def in_hour_window(moment: datetime, start_hour: int, end_hour: int) -> bool:
    return start_hour <= moment.hour < end_hour


def tick_marks(start: datetime, minutes: int) -> list[datetime]:
    """Tick instants strictly after `start` and at or before `start + minutes`."""
    if minutes <= 0:
        return []
    elapsed = int((start - GAME_START).total_seconds() // 60)
    target = elapsed + minutes
    marks: list[datetime] = []
    next_tick = (elapsed // TICK_MINUTES + 1) * TICK_MINUTES
    while next_tick <= target:
        marks.append(GAME_START + timedelta(minutes=next_tick))
        next_tick += TICK_MINUTES
    return marks


def _unit(value: int, one: str, few: str, many: str) -> str:
    mod100 = value % 100
    mod10 = value % 10
    if 11 <= mod100 <= 14:
        word = many
    elif mod10 == 1:
        word = one
    elif 2 <= mod10 <= 4:
        word = few
    else:
        word = many
    return f"{value} {word}"


def duration_phrase(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    parts: list[str] = []
    if hours:
        parts.append(_unit(hours, "час", "часа", "часов"))
    if mins or not hours:
        parts.append(_unit(mins, "минуту", "минуты", "минут"))
    return " ".join(parts)
