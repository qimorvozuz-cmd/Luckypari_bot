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
    channel_id = _int("CHANNEL_ID")
    if not channel_id:
        raise RuntimeError("CHANNEL_ID o'rnatilmagan")
    return Settings(
        bot_token=token,
        admin_ids=admins,
        channel_id=channel_id,
        channel_url=os.getenv("CHANNEL_URL", "https://t.me/example").strip(),
        registration_url=os.getenv("REGISTRATION_URL", "https://example.com/register").strip(),
        promo_code=os.getenv("PROMO_CODE", "TOM").strip(),
        apk_path=os.getenv("APK_PATH", "assets/luckypari.apk").strip(),
        database_path=os.getenv("DATABASE_PATH", "data/bot.db").strip(),
    )
