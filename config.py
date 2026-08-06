import os
from dataclasses import dataclass


def env_int(name: str, default: int = 0) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        return int(value)
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
    vip_deposit: int
    mega_deposit: int
    referral_reward: int
    apk_path: str
    database_path: str


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN o'rnatilmagan")
    try:
        admins = frozenset(int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip())
    except ValueError as exc:
        raise RuntimeError("ADMIN_IDS vergul bilan ajratilgan raqamlar bo'lishi kerak") from exc
    if not admins:
        raise RuntimeError("ADMIN_IDS o'rnatilmagan")
    raw_channel = os.getenv("CHANNEL_ID", "").strip()
    if not raw_channel:
        legacy = os.getenv("CHANNEL_USERNAME", "").strip()
        raw_channel = legacy if legacy.lstrip("-").isdigit() else "0"
    try:
        channel_id = int(raw_channel)
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
        vip_deposit=env_int("VIP_DEPOSIT", env_int("MIN_DEPOSIT", 50000)),
        mega_deposit=env_int("MEGA_DEPOSIT", 100000),
        referral_reward=env_int("REFERRAL_REWARD", 10000),
        apk_path=os.getenv("APK_PATH", "/data/luckypari.apk").strip(),
        database_path=(os.getenv("DATABASE_PATH") or os.getenv("DB_PATH") or "/data/bot.db").strip(),
    )
