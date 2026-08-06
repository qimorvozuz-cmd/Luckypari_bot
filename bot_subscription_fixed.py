#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Luckypari VIP Telegram Bot — single-file version
Python 3.11+
Framework: aiogram 3.x
Database: SQLite

Install:
    pip install -U aiogram python-dotenv

Environment variables (.env or hosting variables):
    BOT_TOKEN=123456:ABC...
    ADMIN_IDS=123456789,987654321
    CHANNEL_USERNAME=@your_channel
    REGISTRATION_URL=https://example.com/register?promo=TOM
    PROMO_CODE=TOM
    MIN_DEPOSIT=50000
    SUPPORT_USERNAME=@your_support
    DB_PATH=luckypari_bot.db
    APK_PATH=files/luckypari.apk
    INACTIVE_DAYS=5
    PROMO_INTERVAL_HOURS=24

Run:
    python bot.py

Important:
- Bot does not verify deposits automatically unless an official partner API is integrated.
- Admin checks player ID and deposit manually, then approves or rejects the request.
- Signals are entertainment/risk-management suggestions and never guarantee winnings.
- Only distribute an APK that you own or are authorized to distribute.
"""

import asyncio
import html
import logging
import os
import random
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

# ----------------------------- CONFIG -----------------------------

@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    channel_username: str
    channel_invite_url: str
    registration_url: str
    promo_code: str
    min_deposit: int
    support_username: str
    db_path: str
    apk_path: str
    inactive_days: int
    promo_interval_hours: int

    @staticmethod
    def from_env() -> "Config":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN topilmadi.")

        raw_admins = os.getenv("ADMIN_IDS", "").strip()
        admins = {
            int(x.strip()) for x in raw_admins.split(",")
            if x.strip().isdigit()
        }
        if not admins:
            raise RuntimeError("ADMIN_IDS topilmadi yoki noto‘g‘ri.")

        return Config(
            bot_token=token,
            admin_ids=admins,
            channel_username=os.getenv("CHANNEL_USERNAME", "").strip(),
            channel_invite_url=os.getenv("CHANNEL_INVITE_URL", "").strip(),
            registration_url=os.getenv("REGISTRATION_URL", "https://example.com").strip(),
            promo_code=os.getenv("PROMO_CODE", "TOM").strip(),
            min_deposit=int(os.getenv("MIN_DEPOSIT", "50000")),
            support_username=os.getenv("SUPPORT_USERNAME", "@support").strip(),
            db_path=os.getenv("DB_PATH", "luckypari_bot.db").strip(),
            apk_path=os.getenv("APK_PATH", "files/luckypari.apk").strip(),
            inactive_days=max(1, int(os.getenv("INACTIVE_DAYS", "5"))),
            promo_interval_hours=max(1, int(os.getenv("PROMO_INTERVAL_HOURS", "24"))),
        )

CFG = Config.from_env()
TZ = timezone(timedelta(hours=5))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("luckypari_bot")

router = Router()
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

# ----------------------------- DATABASE -----------------------------

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(CFG.db_path)
    conn.row_factory = sqlite3.Row
    return conn

def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")

def init_db() -> None:
    Path(CFG.db_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(db_connect()) as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS users (
                tg_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                age_confirmed INTEGER DEFAULT 0,
                approved INTEGER DEFAULT 0,
                blocked INTEGER DEFAULT 0,
                player_id TEXT,
                vip_level TEXT DEFAULT 'STANDARD',
                vip_until TEXT,
                notifications INTEGER DEFAULT 1,
                language TEXT DEFAULT 'uz',
                joined_at TEXT NOT NULL,
                last_active_at TEXT NOT NULL,
                last_promo_at TEXT
            );

            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL,
                player_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by INTEGER
            );

            CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                prize TEXT,
                starts_at TEXT,
                ends_at TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contest_entries (
                contest_id INTEGER NOT NULL,
                tg_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (contest_id, tg_id)
            );

            CREATE TABLE IF NOT EXISTS signal_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                signal_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        conn.commit()

def upsert_user(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    with closing(db_connect()) as conn:
        conn.execute(
            """
            INSERT INTO users
                (tg_id, username, full_name, joined_at, last_active_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET
                username=excluded.username,
                full_name=excluded.full_name,
                last_active_at=excluded.last_active_at
            """,
            (
                user.id,
                user.username or "",
                user.full_name or "",
                now_iso(),
                now_iso(),
            ),
        )
        conn.commit()

def touch_user(tg_id: int) -> None:
    with closing(db_connect()) as conn:
        conn.execute(
            "UPDATE users SET last_active_at=? WHERE tg_id=?",
            (now_iso(), tg_id),
        )
        conn.commit()

def get_user(tg_id: int) -> Optional[sqlite3.Row]:
    with closing(db_connect()) as conn:
        return conn.execute(
            "SELECT * FROM users WHERE tg_id=?",
            (tg_id,),
        ).fetchone()

def is_admin(tg_id: int) -> bool:
    return tg_id in CFG.admin_ids

def setting_get(key: str, default: str = "") -> str:
    with closing(db_connect()) as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,),
        ).fetchone()
    return row["value"] if row else default

def setting_set(key: str, value: str) -> None:
    with closing(db_connect()) as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )
        conn.commit()

# ----------------------------- STATES -----------------------------

class UserStates(StatesGroup):
    waiting_player_id = State()
    waiting_support_message = State()

class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_contest_title = State()
    waiting_contest_description = State()
    waiting_contest_prize = State()
    waiting_contest_end = State()
    waiting_apk = State()

# ----------------------------- KEYBOARDS -----------------------------

def main_menu(admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🍎 Apple signal"), KeyboardButton(text="🐔 Chicken Road")],
        [KeyboardButton(text="💎 VIP bo‘lim"), KeyboardButton(text="🏆 Konkurslar")],
        [KeyboardButton(text="🎁 Bonuslar"), KeyboardButton(text="📥 Luckypari APK")],
        [KeyboardButton(text="👤 Shaxsiy kabinet"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="👥 Referal tizimi"), KeyboardButton(text="🔔 Bildirishnomalar")],
        [KeyboardButton(text="🛟 Yordam"), KeyboardButton(text="ℹ️ Qoidalar")],
    ]
    if admin:
        rows.append([KeyboardButton(text="🛠 Admin panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def age_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Men 18 yoshdan kattaman", callback_data="age_yes")],
            [InlineKeyboardButton(text="❌ Chiqish", callback_data="age_no")],
        ]
    )

def registration_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Ro‘yxatdan o‘tish", url=CFG.registration_url)
    kb.button(text="🆔 Player ID yuborish", callback_data="send_player_id")
    kb.adjust(1)
    return kb.as_markup()

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏳ Arizalar", callback_data="admin_apps")
    kb.button(text="👥 Foydalanuvchilar", callback_data="admin_users")
    kb.button(text="📊 Statistika", callback_data="admin_stats")
    kb.button(text="📢 Xabar yuborish", callback_data="admin_broadcast")
    kb.button(text="🏆 Konkurs yaratish", callback_data="admin_contest_new")
    kb.button(text="📋 Konkurslar", callback_data="admin_contests")
    kb.button(text="📤 APK yangilash", callback_data="admin_apk")
    kb.button(text="💎 VIP boshqaruvi", callback_data="admin_vip_help")
    kb.adjust(2)
    return kb.as_markup()

# ----------------------------- HELPERS -----------------------------

async def safe_edit(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        pass

async def loading_animation(message: Message, title: str) -> None:
    frames = [
        f"{title}\n\n▰▱▱▱▱▱▱▱▱▱ 10%",
        f"{title}\n\n▰▰▰▱▱▱▱▱▱▱ 30%",
        f"{title}\n\n▰▰▰▰▰▱▱▱▱▱ 50%",
        f"{title}\n\n▰▰▰▰▰▰▰▱▱▱ 70%",
        f"{title}\n\n▰▰▰▰▰▰▰▰▰▰ 100%",
    ]
    for frame in frames:
        await safe_edit(message, frame)
        await asyncio.sleep(0.28)

async def subscribed(bot: Bot, user_id: int) -> bool:
    if not CFG.channel_username:
        return True
    try:
        chat_id: int | str = CFG.channel_username
        if CFG.channel_username.lstrip("-").isdigit():
            chat_id = int(CFG.channel_username)

        member = await bot.get_chat_member(chat_id, user_id)

        return member.status in {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        }
    except Exception as exc:
        log.warning(
            "Subscription check failed. chat_id=%s user_id=%s error=%r",
            chat_id,
            user_id,
            exc,
        )
        return False

def access_allowed(row: Optional[sqlite3.Row]) -> bool:
    if not row or not row["approved"] or row["blocked"]:
        return False
    vip_until = row["vip_until"]
    if vip_until:
        try:
            if datetime.fromisoformat(vip_until) < datetime.now(TZ):
                return False
        except ValueError:
            return False
    return True

async def require_access(message: Message, bot: Bot) -> bool:
    row = get_user(message.from_user.id)
    if not row or not row["age_confirmed"]:
        await message.answer("🔞 Avval /start orqali yoshni tasdiqlang.")
        return False
    if not await subscribed(bot, message.from_user.id):
        kb = InlineKeyboardBuilder()
        if CFG.channel_invite_url:
            kb.button(text="📢 Kanalga qo‘shilish", url=CFG.channel_invite_url)
        kb.button(text="✅ Obunani tekshirish", callback_data="check_subscription")
        kb.adjust(1)
        await message.answer(
            "🔒 <b>Davom etish uchun TOM BET kanaliga obuna bo‘ling.</b>\n\n"
            "Kanalga qo‘shilgach, «✅ Obunani tekshirish» tugmasini bosing.",
            reply_markup=kb.as_markup(),
        )
        return False
    if not access_allowed(row):
        await message.answer(
            "🔐 <b>VIP KIRISH YOPIQ</b>\n\n"
            f"1️⃣ Luckypari’da <b>{html.escape(CFG.promo_code)}</b> promokodi bilan ro‘yxatdan o‘ting.\n"
            f"2️⃣ Kamida <b>{CFG.min_deposit:,} so‘m</b> depozit qiling.\n"
            "3️⃣ Player ID raqamingizni yuboring.\n"
            "4️⃣ Admin tekshirganidan so‘ng ruxsat ochiladi.\n\n"
            "⚠️ Signal tavsiyalari yutuqni kafolatlamaydi.",
            reply_markup=registration_keyboard(),
        )
        return False
    return True

def apple_signal() -> str:
    lane = random.randint(1, 5)
    stop_row = random.randint(2, 4)
    risk = random.choice(["🟢 Past", "🟡 O‘rta", "🟠 Yuqori"])
    bankroll = random.choice(["1%", "1.5%", "2%"])
    return (
        "🍎 <b>APPLE VIP TAVSIYA</b>\n\n"
        f"🎯 Tanlov: <b>{lane}-katak</b>\n"
        f"🪜 Tavsiya etilgan chegara: <b>{stop_row}-qator</b>\n"
        f"📉 Risk: <b>{risk}</b>\n"
        f"💰 Stavka: balansning <b>{bankroll}</b>\n\n"
        "⚠️ Bu ehtimoliy tavsiya. Natija tasodifiy bo‘lishi mumkin."
    )

def chicken_signal() -> str:
    mode = random.choice(["Easy", "Medium"])
    steps = random.randint(2, 5)
    cashout = round(random.uniform(1.25, 1.85), 2)
    bankroll = random.choice(["1%", "1.5%", "2%"])
    return (
        "🐔 <b>CHICKEN ROAD VIP TAVSIYA</b>\n\n"
        f"🎮 Rejim: <b>{mode}</b>\n"
        f"👣 Tavsiya: <b>{steps} qadam</b>\n"
        f"💸 Chiqish nuqtasi: <b>x{cashout}</b>\n"
        f"🏦 Stavka: balansning <b>{bankroll}</b>\n\n"
        "⚠️ Bu ehtimoliy tavsiya. Yutuq kafolatlanmaydi."
    )

def log_signal(tg_id: int, game: str, text: str) -> None:
    with closing(db_connect()) as conn:
        conn.execute(
            """
            INSERT INTO signal_logs(tg_id, game, signal_text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (tg_id, game, text, now_iso()),
        )
        conn.commit()

# ----------------------------- START / AGE -----------------------------

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    upsert_user(message)
    row = get_user(message.from_user.id)
    if row and row["age_confirmed"]:
        await message.answer(
            "💎 <b>LUCKYPARI VIP SIGNAL CENTER</b>\n\n"
            "Kerakli bo‘limni tanlang:",
            reply_markup=main_menu(is_admin(message.from_user.id)),
        )
        return

    await message.answer(
        "🔞 <b>18+ TASDIQLASH</b>\n\n"
        "Ushbu bot faqat voyaga yetgan foydalanuvchilar uchun.\n"
        "Qimor moliyaviy yo‘qotish xavfini tug‘diradi.",
        reply_markup=age_keyboard(),
    )

@router.callback_query(F.data == "age_yes")
async def age_yes(call: CallbackQuery) -> None:
    with closing(db_connect()) as conn:
        conn.execute(
            "UPDATE users SET age_confirmed=1, last_active_at=? WHERE tg_id=?",
            (now_iso(), call.from_user.id),
        )
        conn.commit()
    await call.message.edit_text(
        "✅ Yosh tasdiqlandi.\n\n"
        "💎 <b>LUCKYPARI VIP SIGNAL CENTER</b>\n"
        "Kerakli bo‘limni tanlang."
    )
    await call.message.answer(
        "🏠 Bosh menyu:",
        reply_markup=main_menu(is_admin(call.from_user.id)),
    )
    await call.answer()

@router.callback_query(F.data == "age_no")
async def age_no(call: CallbackQuery) -> None:
    await call.message.edit_text("⛔ Botdan foydalanish uchun 18 yoshga to‘lgan bo‘lishingiz kerak.")
    await call.answer()

@router.callback_query(F.data == "check_subscription")
async def check_subscription(call: CallbackQuery, bot: Bot) -> None:
    if await subscribed(bot, call.from_user.id):
        await call.answer("✅ Obuna tasdiqlandi!", show_alert=True)
        try:
            await call.message.edit_text(
                "✅ <b>Obunangiz tasdiqlandi!</b>\n\n"
                "Endi bosh menyudan foydalanishingiz mumkin."
            )
        except TelegramBadRequest:
            pass
        await call.message.answer(
            "🏠 Bosh menyu:",
            reply_markup=main_menu(is_admin(call.from_user.id)),
        )
    else:
        await call.answer(
            "❌ Siz hali kanalga obuna bo‘lmagansiz yoki bot kanal admini emas.",
            show_alert=True,
        )

# ----------------------------- USER REGISTRATION -----------------------------

@router.callback_query(F.data == "send_player_id")
async def ask_player_id(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserStates.waiting_player_id)
    await call.message.answer(
        "🆔 Luckypari Player ID raqamingizni yuboring.\n\n"
        "Faqat raqam yoki hisob identifikatorini yuboring."
    )
    await call.answer()

@router.message(UserStates.waiting_player_id)
async def receive_player_id(message: Message, state: FSMContext, bot: Bot) -> None:
    upsert_user(message)
    player_id = (message.text or "").strip()
    if len(player_id) < 3 or len(player_id) > 40:
        await message.answer("❌ Player ID noto‘g‘ri. Qayta yuboring.")
        return

    with closing(db_connect()) as conn:
        existing = conn.execute(
            "SELECT id FROM applications WHERE tg_id=? AND status='pending'",
            (message.from_user.id,),
        ).fetchone()
        conn.execute(
            "UPDATE users SET player_id=?, last_active_at=? WHERE tg_id=?",
            (player_id, now_iso(), message.from_user.id),
        )
        if existing:
            conn.execute(
                "UPDATE applications SET player_id=?, created_at=? WHERE id=?",
                (player_id, now_iso(), existing["id"]),
            )
            app_id = existing["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO applications(tg_id, player_id, status, created_at)
                VALUES (?, ?, 'pending', ?)
                """,
                (message.from_user.id, player_id, now_iso()),
            )
            app_id = cur.lastrowid
        conn.commit()

    username = f"@{message.from_user.username}" if message.from_user.username else "yo‘q"
    text = (
        "🆕 <b>YANGI TEKSHIRUV ARIZASI</b>\n\n"
        f"👤 Foydalanuvchi: {html.escape(message.from_user.full_name)}\n"
        f"🔗 Username: {html.escape(username)}\n"
        f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n"
        f"🎰 Player ID: <code>{html.escape(player_id)}</code>\n"
        f"🎁 Promokod: <b>{html.escape(CFG.promo_code)}</b>\n"
        f"💰 Shart: kamida <b>{CFG.min_deposit:,} so‘m</b>\n"
        f"📄 Ariza: #{app_id}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"app_ok:{app_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"app_no:{app_id}"),
            ],
            [InlineKeyboardButton(text="💎 30 kun VIP", callback_data=f"app_vip30:{app_id}")],
        ]
    )
    for admin_id in CFG.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb)
        except Exception as exc:
            log.warning("Admin notification failed: %s", exc)

    await state.clear()
    await message.answer(
        "✅ Arizangiz yuborildi.\n\n"
        "Admin Player ID, promokod va depozitni tekshiradi. "
        "Natija bot orqali yuboriladi.",
        reply_markup=main_menu(is_admin(message.from_user.id)),
    )

# ----------------------------- SIGNALS -----------------------------

async def send_signal(message: Message, bot: Bot, game: str) -> None:
    upsert_user(message)
    if not await require_access(message, bot):
        return

    wait = await message.answer("📡 VIP tizim ishga tushmoqda...")
    await loading_animation(wait, "🔍 Ma’lumotlar tahlil qilinmoqda...")
    text = apple_signal() if game == "apple" else chicken_signal()
    log_signal(message.from_user.id, game, text)
    await safe_edit(wait, text)

@router.message(F.text == "🍎 Apple signal")
async def apple_handler(message: Message, bot: Bot) -> None:
    await send_signal(message, bot, "apple")

@router.message(F.text == "🐔 Chicken Road")
async def chicken_handler(message: Message, bot: Bot) -> None:
    await send_signal(message, bot, "chicken")

# ----------------------------- USER MENU -----------------------------

@router.message(F.text == "💎 VIP bo‘lim")
async def vip_section(message: Message) -> None:
    upsert_user(message)
    row = get_user(message.from_user.id)
    if not access_allowed(row):
        await message.answer(
            "🔐 <b>VIP BO‘LIM YOPIQ</b>\n\n"
            f"<b>{CFG.promo_code}</b> promokodi bilan ro‘yxatdan o‘ting, "
            f"kamida <b>{CFG.min_deposit:,} so‘m</b> depozit qiling va Player ID yuboring.",
            reply_markup=registration_keyboard(),
        )
        return

    until = row["vip_until"] or "cheklanmagan"
    await message.answer(
        "💎 <b>VIP KABINET</b>\n\n"
        f"👑 Daraja: <b>{html.escape(row['vip_level'])}</b>\n"
        f"📅 Amal qilish muddati: <b>{html.escape(until)}</b>\n"
        "⚡ Signal bildirishnomalari\n"
        "🏆 VIP konkurslar\n"
        "🎁 Maxsus bonuslar\n"
        "🛟 VIP yordam\n\n"
        "⚠️ Hech bir signal yutuqni kafolatlamaydi."
    )

@router.message(F.text == "📥 Luckypari APK")
async def send_apk(message: Message) -> None:
    upsert_user(message)
    apk_path = setting_get("apk_path", CFG.apk_path)
    path = Path(apk_path)
    if not path.exists() or not path.is_file():
        await message.answer(
            "📦 APK fayli hozircha admin tomonidan joylanmagan.\n\n"
            f"Ro‘yxatdan o‘tish: {CFG.registration_url}"
        )
        return
    try:
        await message.answer_document(
            FSInputFile(path),
            caption=(
                "📱 <b>Luckypari Android APK</b>\n\n"
                f"🎁 Promokod: <code>{html.escape(CFG.promo_code)}</code>\n"
                "🔐 Faqat ishonchli manbadan olingan va sizga ruxsat etilgan APK’ni o‘rnating."
            ),
        )
    except TelegramBadRequest as exc:
        await message.answer(f"❌ APK yuborilmadi: {html.escape(str(exc))}")

@router.message(F.text == "👤 Shaxsiy kabinet")
async def profile(message: Message) -> None:
    upsert_user(message)
    row = get_user(message.from_user.id)
    status = "✅ Tasdiqlangan" if row["approved"] else "⏳ Tasdiqlanmagan"
    notif = "🔔 Yoqilgan" if row["notifications"] else "🔕 O‘chirilgan"
    await message.answer(
        "👤 <b>SHAXSIY KABINET</b>\n\n"
        f"🆔 Telegram ID: <code>{row['tg_id']}</code>\n"
        f"🎰 Player ID: <code>{html.escape(row['player_id'] or 'kiritilmagan')}</code>\n"
        f"🔐 Holat: <b>{status}</b>\n"
        f"👑 Daraja: <b>{html.escape(row['vip_level'])}</b>\n"
        f"📅 VIP: <b>{html.escape(row['vip_until'] or 'yo‘q')}</b>\n"
        f"📣 Xabarlar: <b>{notif}</b>"
    )

@router.message(F.text == "📊 Statistika")
async def user_stats(message: Message) -> None:
    upsert_user(message)
    with closing(db_connect()) as conn:
        total = conn.execute(
            "SELECT COUNT(*) c FROM signal_logs WHERE tg_id=?",
            (message.from_user.id,),
        ).fetchone()["c"]
        apple = conn.execute(
            "SELECT COUNT(*) c FROM signal_logs WHERE tg_id=? AND game='apple'",
            (message.from_user.id,),
        ).fetchone()["c"]
        chicken = conn.execute(
            "SELECT COUNT(*) c FROM signal_logs WHERE tg_id=? AND game='chicken'",
            (message.from_user.id,),
        ).fetchone()["c"]
    await message.answer(
        "📊 <b>SIZNING STATISTIKANGIZ</b>\n\n"
        f"📡 Jami tavsiyalar: <b>{total}</b>\n"
        f"🍎 Apple: <b>{apple}</b>\n"
        f"🐔 Chicken Road: <b>{chicken}</b>\n\n"
        "Natijalar foydalanuvchi tomonidan mustaqil tekshiriladi."
    )

@router.message(F.text == "🎁 Bonuslar")
async def bonuses(message: Message) -> None:
    await message.answer(
        "🎁 <b>BONUSLAR</b>\n\n"
        f"🚀 Ro‘yxatdan o‘tish promokodi: <code>{html.escape(CFG.promo_code)}</code>\n"
        f"💰 Minimal faollashtirish depoziti: <b>{CFG.min_deposit:,} so‘m</b>\n\n"
        "Bonus shartlarini ilova ichida tekshiring.",
        reply_markup=registration_keyboard(),
    )

@router.message(F.text == "👥 Referal tizimi")
async def referrals(message: Message, bot: Bot) -> None:
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
    await message.answer(
        "👥 <b>REFERAL HAVOLA</b>\n\n"
        f"<code>{html.escape(link)}</code>\n\n"
        "Do‘stlaringizga yuborishingiz mumkin. Bonus berish qoidalari admin tomonidan belgilanadi."
    )

@router.message(F.text == "🔔 Bildirishnomalar")
async def notifications(message: Message) -> None:
    upsert_user(message)
    row = get_user(message.from_user.id)
    new_value = 0 if row["notifications"] else 1
    with closing(db_connect()) as conn:
        conn.execute(
            "UPDATE users SET notifications=? WHERE tg_id=?",
            (new_value, message.from_user.id),
        )
        conn.commit()
    await message.answer(
        "🔔 Bildirishnomalar yoqildi." if new_value else "🔕 Bildirishnomalar o‘chirildi."
    )

@router.message(F.text == "ℹ️ Qoidalar")
async def rules(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>QOIDALAR VA XAVFSIZLIK</b>\n\n"
        "• Faqat 18+ foydalanuvchilar uchun.\n"
        "• Qarzdorlik yoki zarur xarajatlar pulini tikmang.\n"
        "• Signal va statistikalar yutuq kafolati emas.\n"
        "• Yo‘qotishni quvib, stavkani oshirmang.\n"
        "• APK faylni faqat ruxsat etilgan manbadan o‘rnating.\n"
        "• Istalgan payt bildirishnomalarni o‘chirishingiz mumkin."
    )

@router.message(F.text == "🛟 Yordam")
async def support(message: Message, state: FSMContext) -> None:
    await state.set_state(UserStates.waiting_support_message)
    await message.answer(
        f"🛟 Savolingizni yozing. Admin: {html.escape(CFG.support_username)}\n\n"
        "Bekor qilish uchun /cancel yuboring."
    )

@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("✅ Amal bekor qilindi.", reply_markup=main_menu(is_admin(message.from_user.id)))

@router.message(UserStates.waiting_support_message)
async def support_receive(message: Message, state: FSMContext, bot: Bot) -> None:
    text = (message.text or "").strip()
    for admin_id in CFG.admin_ids:
        try:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✉️ Foydalanuvchiga yozish",
                        url=f"tg://user?id={message.from_user.id}"
                    )]
                ]
            )
            await bot.send_message(
                admin_id,
                "🛟 <b>YANGI YORDAM SO‘ROVI</b>\n\n"
                f"👤 {html.escape(message.from_user.full_name)}\n"
                f"🆔 <code>{message.from_user.id}</code>\n\n"
                f"{html.escape(text)}",
                reply_markup=kb,
            )
        except Exception:
            pass
    await state.clear()
    await message.answer("✅ Xabaringiz adminga yuborildi.")

# ----------------------------- CONTESTS -----------------------------

@router.message(F.text == "🏆 Konkurslar")
async def contests_list(message: Message) -> None:
    upsert_user(message)
    with closing(db_connect()) as conn:
        rows = conn.execute(
            """
            SELECT * FROM contests
            WHERE active=1
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()

    if not rows:
        await message.answer("🏆 Hozircha faol konkurs yo‘q.")
        return

    for row in rows:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="🎟 Ishtirok etish",
                    callback_data=f"contest_join:{row['id']}"
                )]
            ]
        )
        await message.answer(
            f"🏆 <b>{html.escape(row['title'])}</b>\n\n"
            f"{html.escape(row['description'])}\n\n"
            f"🎁 Sovrin: <b>{html.escape(row['prize'] or 'Belgilanmagan')}</b>\n"
            f"⏳ Tugash: <b>{html.escape(row['ends_at'] or 'Belgilanmagan')}</b>",
            reply_markup=kb,
        )

@router.callback_query(F.data.startswith("contest_join:"))
async def contest_join(call: CallbackQuery) -> None:
    contest_id = int(call.data.split(":")[1])
    row = get_user(call.from_user.id)
    if not row or not row["approved"]:
        await call.answer("Avval profilingiz tasdiqlanishi kerak.", show_alert=True)
        return

    with closing(db_connect()) as conn:
        contest = conn.execute(
            "SELECT * FROM contests WHERE id=? AND active=1",
            (contest_id,),
        ).fetchone()
        if not contest:
            await call.answer("Konkurs faol emas.", show_alert=True)
            return
        conn.execute(
            """
            INSERT OR IGNORE INTO contest_entries(contest_id, tg_id, joined_at)
            VALUES (?, ?, ?)
            """,
            (contest_id, call.from_user.id, now_iso()),
        )
        conn.commit()
    await call.answer("✅ Konkursda ishtirokingiz qayd etildi.", show_alert=True)

# ----------------------------- ADMIN APPLICATIONS -----------------------------

@router.message(F.text == "🛠 Admin panel")
@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "🛠 <b>ADMIN PANEL</b>",
        reply_markup=admin_panel_keyboard(),
    )

@router.callback_query(F.data == "admin_apps")
async def admin_apps(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        return
    with closing(db_connect()) as conn:
        rows = conn.execute(
            """
            SELECT a.*, u.username, u.full_name
            FROM applications a
            LEFT JOIN users u ON u.tg_id=a.tg_id
            WHERE a.status='pending'
            ORDER BY a.id ASC
            LIMIT 20
            """
        ).fetchall()

    if not rows:
        await call.message.answer("✅ Kutilayotgan ariza yo‘q.")
    else:
        for row in rows:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"app_ok:{row['id']}"),
                        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"app_no:{row['id']}"),
                    ],
                    [InlineKeyboardButton(text="💎 30 kun VIP", callback_data=f"app_vip30:{row['id']}")],
                ]
            )
            await call.message.answer(
                f"📄 Ariza #{row['id']}\n"
                f"👤 {html.escape(row['full_name'] or '')}\n"
                f"🆔 TG: <code>{row['tg_id']}</code>\n"
                f"🎰 Player ID: <code>{html.escape(row['player_id'])}</code>",
                reply_markup=kb,
            )
    await call.answer()

async def process_application(call: CallbackQuery, status: str, vip_days: Optional[int] = None) -> None:
    if not is_admin(call.from_user.id):
        return
    app_id = int(call.data.split(":")[1])
    with closing(db_connect()) as conn:
        app = conn.execute(
            "SELECT * FROM applications WHERE id=?",
            (app_id,),
        ).fetchone()
        if not app:
            await call.answer("Ariza topilmadi.", show_alert=True)
            return

        if status == "approved":
            vip_until = None
            level = "VIP"
            if vip_days:
                vip_until = (datetime.now(TZ) + timedelta(days=vip_days)).isoformat(timespec="seconds")
                level = "GOLD"
            conn.execute(
                """
                UPDATE users
                SET approved=1, blocked=0, vip_level=?, vip_until=?
                WHERE tg_id=?
                """,
                (level, vip_until, app["tg_id"]),
            )
        else:
            conn.execute(
                "UPDATE users SET approved=0 WHERE tg_id=?",
                (app["tg_id"],),
            )

        conn.execute(
            """
            UPDATE applications
            SET status=?, reviewed_at=?, reviewed_by=?
            WHERE id=?
            """,
            (status, now_iso(), call.from_user.id, app_id),
        )
        conn.commit()

    try:
        if status == "approved":
            period = f"{vip_days} kun" if vip_days else "cheklanmagan"
            await call.bot.send_message(
                app["tg_id"],
                "✅ <b>ARIZANGIZ TASDIQLANDI</b>\n\n"
                f"💎 VIP kirish: <b>{period}</b>\n"
                "Barcha ruxsat etilgan bo‘limlardan foydalanishingiz mumkin."
            )
        else:
            await call.bot.send_message(
                app["tg_id"],
                "❌ <b>ARIZA RAD ETILDI</b>\n\n"
                "Player ID, promokod yoki depozit ma’lumotlarini tekshirib, qayta yuboring."
            )
    except Exception:
        pass

    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Bajarildi.", show_alert=True)

@router.callback_query(F.data.startswith("app_ok:"))
async def app_ok(call: CallbackQuery) -> None:
    await process_application(call, "approved")

@router.callback_query(F.data.startswith("app_vip30:"))
async def app_vip30(call: CallbackQuery) -> None:
    await process_application(call, "approved", vip_days=30)

@router.callback_query(F.data.startswith("app_no:"))
async def app_no(call: CallbackQuery) -> None:
    await process_application(call, "rejected")

# ----------------------------- ADMIN STATS / USERS -----------------------------

@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        return
    with closing(db_connect()) as conn:
        total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        approved = conn.execute("SELECT COUNT(*) c FROM users WHERE approved=1").fetchone()["c"]
        pending = conn.execute("SELECT COUNT(*) c FROM applications WHERE status='pending'").fetchone()["c"]
        blocked = conn.execute("SELECT COUNT(*) c FROM users WHERE blocked=1").fetchone()["c"]
        contests = conn.execute("SELECT COUNT(*) c FROM contests WHERE active=1").fetchone()["c"]
        signals = conn.execute("SELECT COUNT(*) c FROM signal_logs").fetchone()["c"]
    await call.message.answer(
        "📊 <b>ADMIN STATISTIKA</b>\n\n"
        f"👥 Jami foydalanuvchi: <b>{total}</b>\n"
        f"✅ Tasdiqlangan: <b>{approved}</b>\n"
        f"⏳ Arizalar: <b>{pending}</b>\n"
        f"⛔ Bloklangan: <b>{blocked}</b>\n"
        f"🏆 Faol konkurs: <b>{contests}</b>\n"
        f"📡 Berilgan tavsiyalar: <b>{signals}</b>"
    )
    await call.answer()

@router.callback_query(F.data == "admin_users")
async def admin_users(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        return
    with closing(db_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY joined_at DESC LIMIT 25"
        ).fetchall()
    if not rows:
        await call.message.answer("Foydalanuvchi yo‘q.")
    else:
        lines = ["👥 <b>OXIRGI FOYDALANUVCHILAR</b>\n"]
        for row in rows:
            mark = "✅" if row["approved"] else "⏳"
            lines.append(
                f"{mark} <code>{row['tg_id']}</code> "
                f"{html.escape(row['full_name'] or '')} "
                f"— {html.escape(row['vip_level'])}"
            )
        await call.message.answer("\n".join(lines))
    await call.answer()

@router.callback_query(F.data == "admin_vip_help")
async def admin_vip_help(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        return
    await call.message.answer(
        "💎 <b>VIP BOSHQARUVI</b>\n\n"
        "Buyruqlar:\n"
        "<code>/vip USER_ID DAYS LEVEL</code>\n"
        "Misol: <code>/vip 123456789 30 GOLD</code>\n\n"
        "<code>/unvip USER_ID</code>\n"
        "<code>/block USER_ID</code>\n"
        "<code>/unblock USER_ID</code>"
    )
    await call.answer()

@router.message(Command("vip"))
async def vip_command(message: Message, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.answer("Format: /vip USER_ID DAYS [LEVEL]")
        return
    user_id = int(parts[1])
    days = int(parts[2])
    level = parts[3].upper() if len(parts) > 3 else "GOLD"
    vip_until = (datetime.now(TZ) + timedelta(days=days)).isoformat(timespec="seconds")
    with closing(db_connect()) as conn:
        conn.execute(
            """
            UPDATE users SET approved=1, blocked=0, vip_level=?, vip_until=?
            WHERE tg_id=?
            """,
            (level, vip_until, user_id),
        )
        conn.commit()
    await message.answer("✅ VIP ruxsat berildi.")
    try:
        await bot.send_message(user_id, f"💎 Sizga {days} kunlik {html.escape(level)} VIP ruxsat berildi.")
    except Exception:
        pass

@router.message(Command("unvip"))
async def unvip_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Format: /unvip USER_ID")
        return
    with closing(db_connect()) as conn:
        conn.execute(
            "UPDATE users SET approved=0, vip_level='STANDARD', vip_until=NULL WHERE tg_id=?",
            (int(parts[1]),),
        )
        conn.commit()
    await message.answer("✅ VIP ruxsat olib tashlandi.")

@router.message(Command("block"))
async def block_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Format: /block USER_ID")
        return
    with closing(db_connect()) as conn:
        conn.execute("UPDATE users SET blocked=1 WHERE tg_id=?", (int(parts[1]),))
        conn.commit()
    await message.answer("⛔ Foydalanuvchi bloklandi.")

@router.message(Command("unblock"))
async def unblock_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Format: /unblock USER_ID")
        return
    with closing(db_connect()) as conn:
        conn.execute("UPDATE users SET blocked=0 WHERE tg_id=?", (int(parts[1]),))
        conn.commit()
    await message.answer("✅ Blok olib tashlandi.")

# ----------------------------- ADMIN BROADCAST -----------------------------

@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_broadcast)
    await call.message.answer(
        "📢 Hammaga yuboriladigan xabarni yuboring.\n"
        "Matn, rasm, video yoki fayl bo‘lishi mumkin.\n\n"
        "Faqat bildirishnomasi yoqilgan foydalanuvchilarga yuboriladi."
    )
    await call.answer()

@router.message(AdminStates.waiting_broadcast)
async def broadcast_send(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    with closing(db_connect()) as conn:
        users = conn.execute(
            "SELECT tg_id FROM users WHERE notifications=1 AND blocked=0"
        ).fetchall()

    sent = 0
    failed = 0
    for row in users:
        try:
            await bot.copy_message(
                chat_id=row["tg_id"],
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            sent += 1
            await asyncio.sleep(0.04)
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
        except Exception:
            failed += 1

    await state.clear()
    await message.answer(f"✅ Yuborildi: {sent}\n❌ Yetib bormadi: {failed}")

# ----------------------------- ADMIN CONTEST WIZARD -----------------------------

@router.callback_query(F.data == "admin_contest_new")
async def contest_new(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_contest_title)
    await call.message.answer("🏆 Konkurs nomini yuboring:")
    await call.answer()

@router.message(AdminStates.waiting_contest_title)
async def contest_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(AdminStates.waiting_contest_description)
    await message.answer("📝 Konkurs shartlarini yuboring:")

@router.message(AdminStates.waiting_contest_description)
async def contest_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=(message.text or "").strip())
    await state.set_state(AdminStates.waiting_contest_prize)
    await message.answer("🎁 Sovrinni yozing:")

@router.message(AdminStates.waiting_contest_prize)
async def contest_prize(message: Message, state: FSMContext) -> None:
    await state.update_data(prize=(message.text or "").strip())
    await state.set_state(AdminStates.waiting_contest_end)
    await message.answer("📅 Tugash sanasini yozing. Masalan: 20.08.2026 23:59")

@router.message(AdminStates.waiting_contest_end)
async def contest_end(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    end_text = (message.text or "").strip()
    with closing(db_connect()) as conn:
        conn.execute(
            """
            INSERT INTO contests
                (title, description, prize, starts_at, ends_at, active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                data["title"],
                data["description"],
                data["prize"],
                now_iso(),
                end_text,
                now_iso(),
            ),
        )
        conn.commit()
    await state.clear()
    await message.answer("✅ Konkurs yaratildi.", reply_markup=admin_panel_keyboard())

@router.callback_query(F.data == "admin_contests")
async def admin_contests(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        return
    with closing(db_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM contests ORDER BY id DESC LIMIT 20"
        ).fetchall()
    if not rows:
        await call.message.answer("Konkurslar yo‘q.")
    else:
        for row in rows:
            status = "🟢 Faol" if row["active"] else "⚫ Yopilgan"
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="⛔ Yopish" if row["active"] else "✅ Faollashtirish",
                        callback_data=f"contest_toggle:{row['id']}"
                    )]
                ]
            )
            await call.message.answer(
                f"#{row['id']} {status}\n<b>{html.escape(row['title'])}</b>",
                reply_markup=kb,
            )
    await call.answer()

@router.callback_query(F.data.startswith("contest_toggle:"))
async def contest_toggle(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        return
    contest_id = int(call.data.split(":")[1])
    with closing(db_connect()) as conn:
        row = conn.execute(
            "SELECT active FROM contests WHERE id=?",
            (contest_id,),
        ).fetchone()
        if not row:
            await call.answer("Topilmadi.", show_alert=True)
            return
        new_value = 0 if row["active"] else 1
        conn.execute(
            "UPDATE contests SET active=? WHERE id=?",
            (new_value, contest_id),
        )
        conn.commit()
    await call.answer("Holat o‘zgartirildi.", show_alert=True)

# ----------------------------- ADMIN APK -----------------------------

@router.callback_query(F.data == "admin_apk")
async def admin_apk_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_apk)
    await call.message.answer(
        "📤 Yangi APK faylni document sifatida yuboring.\n"
        "Fayl kengaytmasi .apk bo‘lishi kerak."
    )
    await call.answer()

@router.message(AdminStates.waiting_apk, F.document)
async def admin_apk_receive(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    doc = message.document
    filename = (doc.file_name or "").lower()
    if not filename.endswith(".apk"):
        await message.answer("❌ Faqat .apk fayl yuboring.")
        return

    target = Path(CFG.apk_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    file = await bot.get_file(doc.file_id)
    await bot.download_file(file.file_path, destination=target)
    setting_set("apk_path", str(target))
    await state.clear()
    await message.answer(
        f"✅ APK yangilandi.\n"
        f"Fayl: <code>{html.escape(str(target))}</code>"
    )

# ----------------------------- INACTIVE USER PROMOS -----------------------------

async def inactive_user_worker(bot: Bot) -> None:
    """
    Sends at most one reminder per PROMO_INTERVAL_HOURS to opted-in inactive users.
    The text avoids guaranteed-win claims and includes an opt-out reminder.
    """
    await asyncio.sleep(20)
    while True:
        try:
            cutoff = datetime.now(TZ) - timedelta(days=CFG.inactive_days)
            promo_cutoff = datetime.now(TZ) - timedelta(hours=CFG.promo_interval_hours)

            with closing(db_connect()) as conn:
                users = conn.execute(
                    """
                    SELECT tg_id, approved
                    FROM users
                    WHERE notifications=1
                      AND blocked=0
                      AND last_active_at < ?
                      AND (last_promo_at IS NULL OR last_promo_at < ?)
                    LIMIT 200
                    """,
                    (cutoff.isoformat(timespec="seconds"), promo_cutoff.isoformat(timespec="seconds")),
                ).fetchall()

            for row in users:
                if row["approved"]:
                    text = (
                        "💎 <b>VIP MARKAZDA YANGILIK BOR</b>\n\n"
                        "🍎 Apple va 🐔 Chicken Road bo‘limlari faol.\n"
                        "🏆 Yangi konkurslarni ham tekshiring.\n\n"
                        "⚠️ Tavsiyalar yutuqni kafolatlamaydi.\n"
                        "Bildirishnomalarni menyudan o‘chirishingiz mumkin."
                    )
                else:
                    text = (
                        "🎁 <b>VIP KIRISHNI FAOLLASHTIRING</b>\n\n"
                        f"<b>{html.escape(CFG.promo_code)}</b> promokodi bilan ro‘yxatdan o‘ting, "
                        f"kamida <b>{CFG.min_deposit:,} so‘m</b> depozit qiling va Player ID yuboring.\n\n"
                        "Bildirishnomalarni menyudan o‘chirishingiz mumkin."
                    )
                try:
                    await bot.send_message(
                        row["tg_id"],
                        text,
                        reply_markup=registration_keyboard() if not row["approved"] else None,
                    )
                    with closing(db_connect()) as conn:
                        conn.execute(
                            "UPDATE users SET last_promo_at=? WHERE tg_id=?",
                            (now_iso(), row["tg_id"]),
                        )
                        conn.commit()
                    await asyncio.sleep(0.05)
                except Exception:
                    pass

        except Exception as exc:
            log.exception("Inactive worker error: %s", exc)

        await asyncio.sleep(3600)

# ----------------------------- FALLBACK -----------------------------

@router.message()
async def fallback(message: Message) -> None:
    upsert_user(message)
    await message.answer(
        "🏠 Kerakli bo‘limni menyudan tanlang.",
        reply_markup=main_menu(is_admin(message.from_user.id)),
    )

# ----------------------------- MAIN -----------------------------

async def main() -> None:
    init_db()
    bot = Bot(CFG.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    asyncio.create_task(inactive_user_worker(bot))
    log.info("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
