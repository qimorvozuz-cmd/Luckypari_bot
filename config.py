import os
from dataclasses import dataclass


def _int(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} butun son bo'lishi kerak") from exc


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    channel_id: int
    channel_url: str
    registration_url: str
    promo_code: str
    min_deposit: int
    apk_path: str
    database_path: str


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN o'rnatilmagan")
    admins = frozenset(
        int(item.strip()) for item in os.getenv("ADMIN_IDS", "").split(",") if item.strip()
    )
    if not admins:
        raise RuntimeError("ADMIN_IDS o'rnatilmagan")
    channel_value = os.getenv("CHANNEL_ID", "").strip()
    if not channel_value:
        legacy_channel = os.getenv("CHANNEL_USERNAME", "").strip()
        channel_value = legacy_channel if legacy_channel.lstrip("-").isdigit() else "0"
    try:
        channel_id = int(channel_value)
    except ValueError:
        channel_id = 0
    if not channel_id:
        raise RuntimeError("CHANNEL_ID o'rnatilmagan")
    return Settings(
        bot_token=token,
        admin_ids=admins,
        channel_id=channel_id,
        channel_url=(os.getenv("CHANNEL_URL") or os.getenv("CHANNEL_INVITE_URL") or "https://t.me/example").strip(),
        registration_url=os.getenv("REGISTRATION_URL", "https://example.com/register").strip(),
        promo_code=os.getenv("PROMO_CODE", "TOM").strip(),
        min_deposit=_int("MIN_DEPOSIT", 50000),
        apk_path=os.getenv("APK_PATH", "assets/luckypari.apk").strip(),
        database_path=(os.getenv("DATABASE_PATH") or os.getenv("DB_PATH") or "data/bot.db").strip(),
    )
