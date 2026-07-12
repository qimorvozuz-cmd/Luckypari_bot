"""
Tommy Partners Bot v3 — yagona fayl.

O'RNATISH:
    pip install -U python-telegram-bot python-dotenv anthropic

RAILWAY VARIABLES:
    BOT_TOKEN=...
    ADMIN_CHAT_ID=...
    REGISTRATION_URL=https://Luckyparipartners.com
    ANTHROPIC_API_KEY=...   # ixtiyoriy
    AI_MODEL=claude-3-5-haiku-latest  # ixtiyoriy

ISHGA TUSHIRISH:
    python Luckypari_bot.py
"""

import asyncio
import html
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

try:
    from anthropic import Anthropic
except Exception:
    Anthropic = None

load_dotenv()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"{name} Railway Variables bo'limida topilmadi"
        )

    return value


BOT_TOKEN = required_env("BOT_TOKEN")
ADMIN_CHAT_ID = int(
    required_env("ADMIN_CHAT_ID")
)

REGISTRATION_URL = os.getenv(
    "REGISTRATION_URL",
    "https://Luckyparipartners.com",
).strip()

ANTHROPIC_API_KEY = os.getenv(
    "ANTHROPIC_API_KEY",
    "",
).strip()

AI_MODEL = os.getenv(
    "AI_MODEL",
    "claude-3-5-haiku-latest",
).strip()

DB_PATH = Path(
    os.getenv(
        "DB_PATH",
        "tommy_bot.db",
    )
)

ASSET_DIR = Path(
    os.getenv(
        "ASSET_DIR",
        "assets",
    )
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(
    "tommy_partners"
)

EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)

USERNAME_RE = re.compile(
    r"^@[A-Za-z0-9_]{3,32}$"
)

REG_SOURCE, REG_MODEL, REG_EMAIL, REG_USERNAME, REG_GEO, REG_PROMO = range(6)


# ============================================================
# DATABASE
# ============================================================

def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    return con


def now() -> str:
    return datetime.now().isoformat(
        timespec="seconds"
    )


def init_db() -> None:
    with db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                text TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                admin_message_id INTEGER,
                created_at TEXT NOT NULL,
                closed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS admin_links (
                admin_message_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                ticket_id INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS partners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                source TEXT,
                model TEXT,
                email TEXT,
                telegram_username TEXT,
                geo TEXT,
                promo TEXT,
                created_at TEXT NOT NULL
            );
            """
        )


def save_user(
    update: Update,
) -> None:

    user = update.effective_user

    if not user:
        return

    timestamp = now()

    with db() as con:
        con.execute(
            """
            INSERT INTO users (
                user_id,
                first_name,
                last_name,
                username,
                created_at,
                last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT(user_id) DO UPDATE SET
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                username = excluded.username,
                last_seen_at = excluded.last_seen_at
            """,
            (
                user.id,
                user.first_name or "",
                user.last_name or "",
                user.username or "",
                timestamp,
                timestamp,
            ),
        )


def create_ticket(
    user_id: int,
    category: str,
    text: str,
) -> int:

    with db() as con:
        cursor = con.execute(
            """
            INSERT INTO tickets (
                user_id,
                category,
                text,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                category,
                text,
                now(),
            ),
        )

        return int(
            cursor.lastrowid
        )


def link_admin_message(
    admin_message_id: int,
    user_id: int,
    ticket_id: Optional[int],
) -> None:

    with db() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO admin_links (
                admin_message_id,
                user_id,
                ticket_id,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                admin_message_id,
                user_id,
                ticket_id,
                now(),
            ),
        )

        if ticket_id:
            con.execute(
                """
                UPDATE tickets
                SET admin_message_id = ?
                WHERE id = ?
                """,
                (
                    admin_message_id,
                    ticket_id,
                ),
            )


def get_admin_link(
    admin_message_id: int,
):
    with db() as con:
        return con.execute(
            """
            SELECT *
            FROM admin_links
            WHERE admin_message_id = ?
            """,
            (
                admin_message_id,
            ),
        ).fetchone()


def close_ticket(
    ticket_id: int,
) -> None:

    with db() as con:
        con.execute(
            """
            UPDATE tickets
            SET status = 'closed',
                closed_at = ?
            WHERE id = ?
            """,
            (
                now(),
                ticket_id,
            ),
        )


def add_partner(
    user_id: int,
    source: str,
    model: str,
    email: str,
    telegram_username: str,
    geo: str,
    promo: str,
) -> int:

    with db() as con:
        cursor = con.execute(
            """
            INSERT INTO partners (
                user_id,
                source,
                model,
                email,
                telegram_username,
                geo,
                promo,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                source,
                model,
                email,
                telegram_username,
                geo,
                promo,
                now(),
            ),
        )

        return int(
            cursor.lastrowid
        )


def stats() -> dict:
    with db() as con:
        users = con.execute(
            """
            SELECT COUNT(*) AS count
            FROM users
            """
        ).fetchone()["count"]

        open_tickets = con.execute(
            """
            SELECT COUNT(*) AS count
            FROM tickets
            WHERE status = 'open'
            """
        ).fetchone()["count"]

        closed_tickets = con.execute(
            """
            SELECT COUNT(*) AS count
            FROM tickets
            WHERE status = 'closed'
            """
        ).fetchone()["count"]

        partners = con.execute(
            """
            SELECT COUNT(*) AS count
            FROM partners
            """
        ).fetchone()["count"]

    return {
        "users": users,
        "open": open_tickets,
        "closed": closed_tickets,
        "partners": partners,
    }


# ============================================================
# HAMKORLIK MODELLARI
# ============================================================

MODEL_INFO = {
    "rs": (
        "💎 <b>RevShare (RS)</b>\n\n"

        "RevShare — siz olib kelgan o'yinchilardan kompaniya "
        "olgan sof daromadning kelishilgan foizini olish modelidir.\n\n"

        "✅ 50% gacha RS muhokama qilinadi\n"
        "✅ O'yinchi faol bo'lgan davrda daromad davom etishi mumkin\n"
        "✅ Haftalik hisob-kitob va shaxsiy support\n"
        "✅ Trafik sifati yaxshi bo'lsa individual shartlar\n\n"

        "📌 Aniq foiz GEO, trafik hajmi va sifatiga qarab "
        "Tommy bilan kelishiladi."
    ),

    "cpa": (
        "💵 <b>CPA</b>\n\n"

        "CPA — har bir tasdiqlangan va sifatli FTD uchun "
        "qat'iy to'lov modelidir.\n\n"

        "✅ Har bir FTD uchun oldindan kelishilgan stavka\n"
        "✅ GEO va trafik sifatiga qarab individual narx\n"
        "✅ Fraud va motivatsiyalangan trafik qabul qilinmaydi\n"
        "✅ Barqaror natija bo'lsa stavka oshirilishi mumkin\n\n"

        "📌 Aniq CPA stavkasi statistika ko'rilgandan "
        "keyin kelishiladi."
    ),

    "hybrid": (
        "⚡ <b>Hybrid</b>\n\n"

        "Hybrid — CPA va RevShare birgalikda ishlaydigan model.\n\n"

        "✅ Har bir sifatli FTD uchun qat'iy to'lov\n"
        "✅ O'yinchilardan tushgan daromaddan qo'shimcha foiz\n"
        "✅ Barqaror trafik uchun qulay\n"
        "✅ Stavka va foiz individual belgilanadi\n\n"

        "📌 Hybrid odatda tekshirilgan va sifatli "
        "trafik manbalariga beriladi."
    ),

    "fix": (
        "📦 <b>Fix</b>\n\n"

        "Fix — reklama joylashtirish yoki kelishilgan "
        "muddat uchun qat'iy summa.\n\n"

        "✅ Kanal yoki bloger statistikasi tekshiriladi\n"
        "✅ Ko'rishlar, auditoriya sifati va oldingi natijalar hisobga olinadi\n"
        "✅ KPI va to'lov tartibi oldindan kelishiladi\n"
        "✅ Yirik va tekshirilgan trafik uchun mos\n\n"

        "📌 Fix avtomatik berilmaydi, Tommy bilan "
        "individual ko'rib chiqiladi."
    ),

    "postpay": (
        "📅 <b>Postpay</b>\n\n"

        "Postpay — reklama uchun to'lov kelishilgan "
        "KPI bajarilgandan keyin beriladi.\n\n"

        "✅ KPI FTD, depozit hajmi yoki boshqa natija bo'lishi mumkin\n"
        "✅ Natija tasdiqlangandan keyin to'lov\n"
        "✅ Barqaror trafik va uzoq muddatli hamkorlik uchun qulay\n"
        "✅ KPI va muddat oldindan yozma kelishiladi\n\n"

        "📌 Aniq shartlar Tommy bilan individual belgilanadi."
    ),
}


# ============================================================
# MAVJUD HAMKORLAR UCHUN TAVSIYALAR
# ============================================================

PARTNER_TIPS = {
    "ftd": (
        "📊 <b>FTD oshirish bo'yicha tavsiyalar</b>\n\n"

        "1️⃣ Auditoriyani GEO va qiziqishiga qarab ajrating.\n"
        "2️⃣ Kamida 3 xil kreativni A/B test qiling.\n"
        "3️⃣ Postda ro'yxatdan o'tish va depozit bosqichini aniq tushuntiring.\n"
        "4️⃣ Konkurs, cashback yoki live formatdan foydalaning.\n"
        "5️⃣ Klik ko'p, FTD kam bo'lsa landing va registratsiya bosqichini tekshiring."
    ),

    "conversion": (
        "🎯 <b>Konversiyani oshirish</b>\n\n"

        "✅ Bir postda bitta asosiy taklif bo'lsin\n"
        "✅ Promo-kod va foydasini yuqorida ko'rsating\n"
        "✅ Real video yoki live orqali ishonch oshiring\n"
        "✅ Auditoriyaga mos til va dizayn tanlang\n"
        "✅ CTR, registration va FTD ni alohida o'lchang"
    ),

    "interest": (
        "🔥 <b>Auditoriyani qiziqtirish</b>\n\n"

        "✅ Oddiy reklama o'rniga voqea va natija ko'rsating\n"
        "✅ Sportda muhim o'yinlar va live vaziyatlardan foydalaning\n"
        "✅ Casinoda yangi slot, cashback va konkurs formatlarini sinang\n"
        "✅ Reels, Stories va Telegram postini birga ishlating\n"
        "✅ Har postda aniq CTA yozing"
    ),
}
# ============================================================
# TO'LOVLAR BO'YICHA MA'LUMOTLAR
# ============================================================

PAYMENT_INFO = {
    "schedule": (
        "📅 <b>To'lov kuni</b>\n\n"

        "To'lov sanasi tanlangan hamkorlik modeliga bog'liq.\n\n"

        "✅ RevShare hisob-kitobi davriy amalga oshiriladi\n"
        "✅ CPA tasdiqlangan sifatli FTD bo'yicha hisoblanadi\n"
        "✅ Fix va Postpay shartlari oldindan kelishiladi\n"
        "✅ To'lov muddati individual shartlarda ko'rsatiladi\n\n"

        "📌 Shaxsiy hisob bo'yicha aniq ma'lumot kerak bo'lsa, "
        "Tommy bilan bog'lanishingiz mumkin."
    ),

    "methods": (
        "💳 <b>To'lov usullari</b>\n\n"

        "To'lov usullari GEO, summa va hamkorlik shartlariga "
        "qarab farq qilishi mumkin.\n\n"

        "✅ Kriptovalyuta\n"
        "✅ Bank yoki elektron to'lov usullari\n"
        "✅ Individual to'lov rekvizitlari\n\n"

        "📌 Aniq to'lov usuli Tommy bilan kelishiladi."
    ),

    "pending": (
        "⏳ <b>Pending yoki kechikayotgan to'lov</b>\n\n"

        "Tekshiruv uchun quyidagi ma'lumotlarni tayyorlang:\n\n"

        "🆔 Affiliate ID\n"
        "💵 To'lov summasi\n"
        "📅 So'rov yuborilgan sana\n"
        "💳 To'lov usuli yoki hamyon\n"
        "📸 Imkon bo'lsa screenshot\n\n"

        "📌 Ushbu ma'lumotlar orqali Tommy to'lov holatini "
        "tezroq tekshira oladi."
    ),

    "calculation": (
        "🧮 <b>To'lov qanday hisoblanadi?</b>\n\n"

        "💎 RevShare — kelishilgan foiz asosida\n"
        "💵 CPA — tasdiqlangan sifatli FTD asosida\n"
        "⚡ Hybrid — CPA va RevShare birgalikda\n"
        "📦 Fix — oldindan kelishilgan summa asosida\n"
        "📅 Postpay — kelishilgan KPI bajarilgandan keyin\n\n"

        "📌 Yakuniy summa tasdiqlangan statistika va "
        "hamkorlik shartlari asosida hisoblanadi."
    ),
}


# ============================================================
# TAYYOR POSTLAR
# ============================================================

POSTS = {
    "casino_live": (
        "🔥 <b>LIVE KAZINO BOSHLANDI!</b>\n\n"

        "🎰 Eng qiziqarli o'yinlar hozir jonli efirda!\n"
        "🎁 Maxsus imkoniyatlardan foydalaning.\n\n"

        "🔑 Promo-kod: <code>{promo}</code>\n"
        "🔗 Ro'yxatdan o'tish: {url}\n\n"

        "⚡ Hoziroq qo'shiling va imkoniyatni boy bermang!\n\n"

        "🔞 18+ | Mas'uliyat bilan o'ynang."
    ),

    "casino_bonus": (
        "🎁 <b>MAXSUS BONUS!</b>\n\n"

        "🎰 Yangi foydalanuvchilar uchun maxsus taklif.\n\n"

        "✅ Ro'yxatdan o'ting\n"
        "✅ Promo-kodni kiriting\n"
        "✅ Bonus imkoniyatidan foydalaning\n\n"

        "🔑 Promo-kod: <code>{promo}</code>\n"
        "🔗 Havola: {url}\n\n"

        "🔞 18+ | Mas'uliyat bilan o'ynang."
    ),

    "casino_cashback": (
        "💰 <b>CASHBACK IMKONIYATI!</b>\n\n"

        "Maxsus cashback shartlarini tekshiring va "
        "yangi imkoniyatlardan foydalaning.\n\n"

        "🔑 Promo-kod: <code>{promo}</code>\n"
        "🔗 Havola: {url}\n\n"

        "🔞 18+ | Mas'uliyat bilan o'ynang."
    ),

    "sport_live": (
        "⚽ <b>LIVE SPORT!</b>\n\n"

        "🔥 Muhim uchrashuvlar hozir jonli davom etmoqda.\n"
        "📊 Koeffitsiyentlarni kuzating va tanlovingizni qiling.\n\n"

        "🔑 Promo-kod: <code>{promo}</code>\n"
        "🔗 Havola: {url}\n\n"

        "🔞 18+ | Mas'uliyat bilan o'ynang."
    ),

    "sport_prematch": (
        "🏆 <b>BUGUNGI MUHIM O'YIN!</b>\n\n"

        "⚽ Jamoalarni tahlil qiling\n"
        "📈 Koeffitsiyentlarni solishtiring\n"
        "🎯 O'z tanlovingizni qiling\n\n"

        "🔑 Promo-kod: <code>{promo}</code>\n"
        "🔗 Havola: {url}\n\n"

        "🔞 18+ | Mas'uliyat bilan o'ynang."
    ),

    "sport_bonus": (
        "🎁 <b>SPORT UCHUN MAXSUS TAKLIF!</b>\n\n"

        "Yangi sport muxlislari uchun maxsus imkoniyat.\n"
        "Ro'yxatdan o'ting va promo-koddan foydalaning.\n\n"

        "🔑 Promo-kod: <code>{promo}</code>\n"
        "🔗 Havola: {url}\n\n"

        "🔞 18+ | Mas'uliyat bilan o'ynang."
    ),
}


# ============================================================
# AI SOZLAMALARI
# ============================================================

_ai_client = None

if ANTHROPIC_API_KEY and Anthropic is not None:
    try:
        _ai_client = Anthropic(
            api_key=ANTHROPIC_API_KEY
        )

    except Exception as error:
        logger.error(
            "Anthropic ishga tushmadi: %s",
            error,
        )


AI_SYSTEM_PROMPT = (
    "Sen Tommy Partners affiliate dasturining professional "
    "AI yordamchisisan. "

    "Faqat affiliate marketing, trafik, FTD, konversiya, "
    "reklama kreativlari, Telegram, Instagram, YouTube, TikTok, "
    "SEO, CPA, RevShare, Hybrid, Fix, Postpay va hamkorlarga "
    "yordam mavzularida javob ber. "

    "Javoblar o'zbek tilida, sodda, amaliy va professional bo'lsin. "

    "Aniq to'lov summasi, kafolatlangan daromad yoki "
    "tasdiqlanmagan faktni o'ylab topma. "

    "Shaxsiy shartlar Tommy bilan kelishilishini ayt. "

    "Javobni 4-8 ta qisqa bandda yoz. "
    "Javob oxirida foydalanuvchi yana savol berishi "
    "mumkinligini ayt."
)


async def get_ai_answer(
    question: str,
) -> Optional[str]:

    if not _ai_client:
        return None

    def request_ai() -> str:
        response = _ai_client.messages.create(
            model=AI_MODEL,
            max_tokens=600,
            system=AI_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": question,
                }
            ],
        )

        if not response.content:
            return ""

        return response.content[0].text.strip()

    try:
        return await asyncio.to_thread(
            request_ai
        )

    except Exception as error:
        logger.exception(
            "AI javob bermadi: %s",
            error,
        )

        return None


# ============================================================
# YORDAMCHI FUNKSIYALAR
# ============================================================

def escape(
    value: object,
) -> str:

    return html.escape(
        str(value or "—")
    )


def user_full_name(
    user,
) -> str:

    name = " ".join(
        part
        for part in [
            user.first_name or "",
            user.last_name or "",
        ]
        if part
    ).strip()

    return name or "Noma'lum"


def user_username(
    user,
) -> str:

    if user.username:
        return f"@{user.username}"

    return "Username mavjud emas"


def get_session(
    context: ContextTypes.DEFAULT_TYPE,
) -> dict:

    return context.user_data.setdefault(
        "session",
        {
            "locked": False,
            "category": None,
            "ticket_id": None,
            "waiting_first_message": False,
        },
    )


def clear_session(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    context.user_data["session"] = {
        "locked": False,
        "category": None,
        "ticket_id": None,
        "waiting_first_message": False,
    }


def is_locked(
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:

    return bool(
        get_session(context).get("locked")
    )


def get_message_text(
    message,
) -> str:

    if message.text:
        return message.text

    if message.caption:
        return message.caption

    if message.photo:
        return "📷 Rasm yuborildi"

    if message.video:
        return "🎥 Video yuborildi"

    if message.document:
        filename = (
            message.document.file_name
            or "Fayl"
        )

        return f"📎 {filename}"

    if message.voice:
        return "🎙 Ovozli xabar yuborildi"

    if message.audio:
        return "🎵 Audio yuborildi"

    return "Media xabar yuborildi"


def format_post(
    post_key: str,
    promo: str,
) -> str:

    template = POSTS.get(
        post_key
    )

    if not template:
        return "⚠️ Tayyor post topilmadi."

    return template.format(
        promo=escape(promo),
        url=escape(REGISTRATION_URL),
    )


def find_banner_path(
    category: str,
    banner_type: str,
) -> Optional[Path]:

    extensions = [
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    ]

    folder = (
        ASSET_DIR
        / "banners"
        / category
    )

    for extension in extensions:
        candidate = (
            folder
            / f"{banner_type}{extension}"
        )

        if candidate.exists():
            return candidate

    return None


# ============================================================
# KLAVIATURALAR
# ============================================================

def main_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💰 Hamkorlik modellari",
                    callback_data="main:models",
                )
            ],
            [
                InlineKeyboardButton(
                    "📝 Yangi hamkor bo'lish",
                    callback_data="register:start",
                )
            ],
            [
                InlineKeyboardButton(
                    "📈 Mavjud hamkorlar",
                    callback_data="main:partners",
                )
            ],
            [
                InlineKeyboardButton(
                    "💳 To'lovlar",
                    callback_data="main:payments",
                )
            ],
            [
                InlineKeyboardButton(
                    "✉️ Boshqa savol",
                    callback_data="main:other",
                )
            ],
        ]
    )


def back_main_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⬅️ Asosiy menyu",
                    callback_data="main:home",
                )
            ]
        ]
    )


def models_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💎 RevShare (RS)",
                    callback_data="model:rs",
                )
            ],
            [
                InlineKeyboardButton(
                    "💵 CPA",
                    callback_data="model:cpa",
                )
            ],
            [
                InlineKeyboardButton(
                    "⚡ Hybrid",
                    callback_data="model:hybrid",
                )
            ],
            [
                InlineKeyboardButton(
                    "📦 Fix",
                    callback_data="model:fix",
                )
            ],
            [
                InlineKeyboardButton(
                    "📅 Postpay",
                    callback_data="model:postpay",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Asosiy menyu",
                    callback_data="main:home",
                )
            ],
        ]
    )


def model_detail_keyboard(
    model_key: str,
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📩 Tommy'dan so'rash",
                    callback_data=f"contact:{model_key}",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Modellarga qaytish",
                    callback_data="main:models",
                )
            ],
        ]
    )


def partners_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📊 FTD oshirish",
                    callback_data="tip:ftd",
                )
            ],
            [
                InlineKeyboardButton(
                    "🎯 Konversiyani oshirish",
                    callback_data="tip:conversion",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔥 Auditoriyani qiziqtirish",
                    callback_data="tip:interest",
                )
            ],
            [
                InlineKeyboardButton(
                    "🤖 AI yordamchi",
                    callback_data="partner:ai",
                )
            ],
            [
                InlineKeyboardButton(
                    "🖼 Bannerlar",
                    callback_data="partner:banners",
                ),
                InlineKeyboardButton(
                    "📝 Tayyor postlar",
                    callback_data="partner:posts",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📩 Tommy bilan bog'lanish",
                    callback_data="contact:partner",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Asosiy menyu",
                    callback_data="main:home",
                )
            ],
        ]
    )


def tip_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🤖 Qo'shimcha AI maslahat",
                    callback_data="partner:ai",
                )
            ],
            [
                InlineKeyboardButton(
                    "📩 Tommy bilan bog'lanish",
                    callback_data="contact:partner",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Hamkorlar bo'limi",
                    callback_data="main:partners",
                )
            ],
        ]
    )


def payments_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📅 To'lov kuni",
                    callback_data="payment:schedule",
                )
            ],
            [
                InlineKeyboardButton(
                    "💳 To'lov usullari",
                    callback_data="payment:methods",
                )
            ],
            [
                InlineKeyboardButton(
                    "⏳ Pending to'lov",
                    callback_data="payment:pending",
                )
            ],
            [
                InlineKeyboardButton(
                    "🧮 Hisob-kitob",
                    callback_data="payment:calculation",
                )
            ],
            [
                InlineKeyboardButton(
                    "📩 Tommy bilan bog'lanish",
                    callback_data="contact:payment",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Asosiy menyu",
                    callback_data="main:home",
                )
            ],
        ]
    )


def contact_confirm_keyboard(
    category: str,
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Ha, yuborish",
                    callback_data=f"contact_start:{category}",
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Yo'q",
                    callback_data="main:home",
                )
            ],
        ]
    )


def active_chat_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ Suhbatni yakunlash",
                    callback_data="chat:cancel",
                )
            ]
        ]
    )


def banner_category_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎰 Casino",
                    callback_data="banner_category:casino",
                )
            ],
            [
                InlineKeyboardButton(
                    "⚽ Sport",
                    callback_data="banner_category:sport",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Hamkorlar bo'limi",
                    callback_data="main:partners",
                )
            ],
        ]
    )


def banner_type_keyboard(
    category: str,
) -> InlineKeyboardMarkup:

    if category == "casino":
        items = [
            ("🔥 LIVE", "live"),
            ("🎁 BONUS", "bonus"),
            ("💰 CASHBACK", "cashback"),
            ("🎰 UNIVERSAL", "universal"),
        ]

    else:
        items = [
            ("⚡ LIVE", "live"),
            ("🏆 PREMATCH", "prematch"),
            ("🎁 BONUS", "bonus"),
            ("⚽ UNIVERSAL", "universal"),
        ]

    rows = [
        [
            InlineKeyboardButton(
                title,
                callback_data=(
                    f"banner_type:{category}:{key}"
                ),
            )
        ]
        for title, key in items
    ]

    rows.append(
        [
            InlineKeyboardButton(
                "⬅️ Bannerlar",
                callback_data="partner:banners",
            )
        ]
    )

    return InlineKeyboardMarkup(
        rows
    )


def post_category_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎰 Casino postlari",
                    callback_data="post_category:casino",
                )
            ],
            [
                InlineKeyboardButton(
                    "⚽ Sport postlari",
                    callback_data="post_category:sport",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Hamkorlar bo'limi",
                    callback_data="main:partners",
                )
            ],
        ]
    )


def post_type_keyboard(
    category: str,
) -> InlineKeyboardMarkup:

    if category == "casino":
        items = [
            ("🔥 LIVE", "live"),
            ("🎁 BONUS", "bonus"),
            ("💰 CASHBACK", "cashback"),
        ]

    else:
        items = [
            ("⚡ LIVE", "live"),
            ("🏆 PREMATCH", "prematch"),
            ("🎁 BONUS", "bonus"),
        ]

    rows = [
        [
            InlineKeyboardButton(
                title,
                callback_data=(
                    f"post_type:{category}:{key}"
                ),
            )
        ]
        for title, key in items
    ]

    rows.append(
        [
            InlineKeyboardButton(
                "⬅️ Postlar",
                callback_data="partner:posts",
            )
        ]
    )

    return InlineKeyboardMarkup(
        rows
    )


def registration_models_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💎 RevShare",
                    callback_data="reg_model:RevShare",
                )
            ],
            [
                InlineKeyboardButton(
                    "💵 CPA",
                    callback_data="reg_model:CPA",
                )
            ],
            [
                InlineKeyboardButton(
                    "⚡ Hybrid",
                    callback_data="reg_model:Hybrid",
                )
            ],
            [
                InlineKeyboardButton(
                    "📦 Fix",
                    callback_data="reg_model:Fix",
                )
            ],
            [
                InlineKeyboardButton(
                    "📅 Postpay",
                    callback_data="reg_model:Postpay",
                )
            ],
        ]
    )


def admin_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📊 Statistika",
                    callback_data="admin:stats",
                )
            ],
            [
                InlineKeyboardButton(
                    "📩 Ochiq murojaatlar",
                    callback_data="admin:tickets",
                )
            ],
            [
                InlineKeyboardButton(
                    "👥 Yangi hamkorlar",
                    callback_data="admin:partners",
                )
            ],
        ]
    )
  # ============================================================
# BOSHLANG'ICH MENYU
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    save_user(update)

    if is_locked(context):
        await update.effective_message.reply_text(
            (
                "💬 <b>Tommy bilan faol suhbatingiz mavjud.</b>\n\n"
                "Savolingizni yozishda davom eting yoki "
                "suhbatni yakunlang."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=active_chat_keyboard(),
        )
        return

    clear_session(context)

    await update.effective_message.reply_text(
        (
            "👋 <b>Tommy Partners botiga xush kelibsiz!</b>\n\n"
            "Bu yerda hamkorlik modellari haqida ma'lumot olishingiz, "
            "mavjud hamkor sifatida yordam olishingiz, banner va tayyor "
            "postlardan foydalanishingiz yoki Tommy bilan "
            "bog'lanishingiz mumkin.\n\n"
            "👇 Kerakli bo'limni tanlang:"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


# ============================================================
# ASOSIY MENYU CALLBACK
# ============================================================

async def main_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    if is_locked(context):
        await query.message.reply_text(
            (
                "🔒 <b>Boshqa bo'limlar vaqtincha yopiq.</b>\n\n"
                "Tommy bilan suhbat tugamaguncha faqat "
                "xabar yuborishingiz mumkin."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=active_chat_keyboard(),
        )
        return

    action = query.data.split(
        ":",
        1,
    )[1]

    if action == "home":
        await query.message.reply_text(
            (
                "🏠 <b>Asosiy menyu</b>\n\n"
                "Kerakli bo'limni tanlang:"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        return

    if action == "models":
        await query.message.reply_text(
            (
                "💰 <b>Hamkorlik modellari</b>\n\n"
                "Batafsil ma'lumot olish uchun "
                "modelni tanlang:"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=models_keyboard(),
        )
        return

    if action == "partners":
        await query.message.reply_text(
            (
                "📈 <b>Mavjud hamkorlar bo'limi</b>\n\n"
                "Bu yerda FTD, konversiya, auditoriyani qiziqtirish, "
                "AI maslahat, banner va tayyor postlar bo'yicha "
                "yordam olishingiz mumkin."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=partners_keyboard(),
        )
        return

    if action == "payments":
        await query.message.reply_text(
            (
                "💳 <b>To'lovlar bo'limi</b>\n\n"
                "Kerakli mavzuni tanlang. Ma'lumot yetarli bo'lmasa, "
                "Tommy bilan bog'lanishingiz mumkin."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=payments_keyboard(),
        )
        return

    if action == "other":
        await query.message.reply_text(
            (
                "✉️ <b>Boshqa savol</b>\n\n"
                "Savolingizni Tommy'ga yuborishni xohlaysizmi?"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=contact_confirm_keyboard(
                "other"
            ),
        )


# ============================================================
# HAMKORLIK MODELLARI CALLBACK
# ============================================================

async def model_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    if is_locked(context):
        await query.message.reply_text(
            "🔒 Avval faol suhbatni yakunlang.",
            reply_markup=active_chat_keyboard(),
        )
        return

    model_key = query.data.split(
        ":",
        1,
    )[1]

    information = MODEL_INFO.get(
        model_key
    )

    if not information:
        await query.message.reply_text(
            "⚠️ Model haqida ma'lumot topilmadi."
        )
        return

    await query.message.reply_text(
        information
        + (
            "\n\n💬 Qo'shimcha ma'lumot kerak bo'lsa, "
            "savolingizni yuboring. Tommy sizga shu chat "
            "orqali javob beradi."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=model_detail_keyboard(
            model_key
        ),
    )


# ============================================================
# MAVJUD HAMKORLAR TAVSIYALARI
# ============================================================

async def tip_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    if is_locked(context):
        await query.message.reply_text(
            "🔒 Avval faol suhbatni yakunlang.",
            reply_markup=active_chat_keyboard(),
        )
        return

    tip_key = query.data.split(
        ":",
        1,
    )[1]

    text = PARTNER_TIPS.get(
        tip_key
    )

    if not text:
        await query.message.reply_text(
            "⚠️ Ma'lumot topilmadi."
        )
        return

    await query.message.reply_text(
        text
        + (
            "\n\n💬 Yana savolingiz bo'lsa, AI yordamchiga "
            "yozishingiz yoki Tommy bilan bog'lanishingiz mumkin."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=tip_keyboard(),
    )


# ============================================================
# TO'LOVLAR CALLBACK
# ============================================================

async def payment_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    if is_locked(context):
        await query.message.reply_text(
            "🔒 Avval faol suhbatni yakunlang.",
            reply_markup=active_chat_keyboard(),
        )
        return

    payment_key = query.data.split(
        ":",
        1,
    )[1]

    text = PAYMENT_INFO.get(
        payment_key
    )

    if not text:
        await query.message.reply_text(
            "⚠️ To'lov ma'lumoti topilmadi."
        )
        return

    await query.message.reply_text(
        text
        + (
            "\n\n💬 Qo'shimcha tekshiruv kerak bo'lsa, "
            "murojaatingizni Tommy'ga yuborishingiz mumkin."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📩 Tommy bilan bog'lanish",
                        callback_data="contact:payment",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ To'lovlar bo'limi",
                        callback_data="main:payments",
                    )
                ],
            ]
        ),
    )


# ============================================================
# MAVJUD HAMKORLAR BO'LIMI
# ============================================================

async def partner_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    if is_locked(context):
        await query.message.reply_text(
            "🔒 Avval faol suhbatni yakunlang.",
            reply_markup=active_chat_keyboard(),
        )
        return

    action = query.data.split(
        ":",
        1,
    )[1]

    if action == "ai":
        context.user_data[
            "waiting_ai_question"
        ] = True

        await query.message.reply_text(
            (
                "🤖 <b>AI yordamchi</b>\n\n"
                "FTD, trafik, konversiya, reklama, kreativ yoki "
                "auditoriyani qiziqtirish bo'yicha "
                "savolingizni yozing.\n\n"
                "Masalan:\n"
                "• FTD kam, nima qilish kerak?\n"
                "• Telegram kanal konversiyasini qanday oshiraman?\n"
                "• Qanday konkurs samarali bo'ladi?\n\n"
                "❌ Bekor qilish uchun /cancel yozing."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=back_main_keyboard(),
        )
        return

    if action == "banners":
        await query.message.reply_text(
            (
                "🖼 <b>Bannerlar</b>\n\n"
                "Banner yo'nalishini tanlang:"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=banner_category_keyboard(),
        )
        return

    if action == "posts":
        await query.message.reply_text(
            (
                "📝 <b>Tayyor postlar</b>\n\n"
                "Post yo'nalishini tanlang:"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=post_category_keyboard(),
        )
        return


# ============================================================
# BANNER CALLBACKLARI
# ============================================================

async def banner_category_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    if is_locked(context):
        await query.message.reply_text(
            "🔒 Avval faol suhbatni yakunlang.",
            reply_markup=active_chat_keyboard(),
        )
        return

    category = query.data.split(
        ":",
        1,
    )[1]

    await query.message.reply_text(
        (
            "🖼 <b>Banner turini tanlang:</b>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=banner_type_keyboard(
            category
        ),
    )


async def banner_type_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    if is_locked(context):
        await query.message.reply_text(
            "🔒 Avval faol suhbatni yakunlang.",
            reply_markup=active_chat_keyboard(),
        )
        return

    _, category, banner_type = query.data.split(
        ":",
        2,
    )

    context.user_data[
        "banner_request"
    ] = {
        "category": category,
        "type": banner_type,
    }

    await query.message.reply_text(
        (
            "🔑 <b>Banner uchun promo-kodni yozing.</b>\n\n"
            "Masalan: LIVE"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_keyboard(),
    )


# ============================================================
# POST CALLBACKLARI
# ============================================================

async def post_category_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    if is_locked(context):
        await query.message.reply_text(
            "🔒 Avval faol suhbatni yakunlang.",
            reply_markup=active_chat_keyboard(),
        )
        return

    category = query.data.split(
        ":",
        1,
    )[1]

    await query.message.reply_text(
        (
            "📝 <b>Post turini tanlang:</b>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=post_type_keyboard(
            category
        ),
    )


async def post_type_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    if is_locked(context):
        await query.message.reply_text(
            "🔒 Avval faol suhbatni yakunlang.",
            reply_markup=active_chat_keyboard(),
        )
        return

    _, category, post_type = query.data.split(
        ":",
        2,
    )

    context.user_data[
        "post_request"
    ] = {
        "category": category,
        "type": post_type,
    }

    await query.message.reply_text(
        (
            "🔑 <b>Post uchun promo-kodni yozing.</b>\n\n"
            "Masalan: LIVE"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_keyboard(),
    )


# ============================================================
# TOMMY BILAN BOG'LANISH
# ============================================================

async def contact_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    if is_locked(context):
        await query.message.reply_text(
            "🔒 Sizda faol suhbat mavjud.",
            reply_markup=active_chat_keyboard(),
        )
        return

    category = query.data.split(
        ":",
        1,
    )[1]

    await query.message.reply_text(
        (
            "📩 <b>Tommy bilan bog'lanish</b>\n\n"
            "Savolingizni Tommy'ga yuborishni xohlaysizmi?"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=contact_confirm_keyboard(
            category
        ),
    )


async def contact_start_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    category = query.data.split(
        ":",
        1,
    )[1]

    user_session = get_session(
        context
    )

    user_session["locked"] = True
    user_session["category"] = category
    user_session["ticket_id"] = None
    user_session[
        "waiting_first_message"
    ] = True

    await query.message.reply_text(
        (
            "✍️ <b>Savolingizni batafsil yozing.</b>\n\n"
            "Men uni Tommy'ga yuboraman. Tommy tez orada "
            "shu chat orqali sizga javob beradi.\n\n"
            "🔒 Suhbat tugamaguncha boshqa bo'limlar yopiq bo'ladi."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=active_chat_keyboard(),
    )


async def chat_cancel_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    user_session = get_session(
        context
    )

    ticket_id = user_session.get(
        "ticket_id"
    )

    if ticket_id:
        close_ticket(
            int(ticket_id)
        )

    clear_session(
        context
    )

    await query.message.reply_text(
        (
            "✅ <b>Suhbat yakunlandi.</b>\n\n"
            "Asosiy menyu qayta ochildi."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


# ============================================================
# YANGI HAMKOR RO'YXATDAN O'TISHI
# ============================================================

async def registration_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    query = update.callback_query
    await query.answer()

    if is_locked(context):
        await query.message.reply_text(
            "🔒 Avval faol suhbatni yakunlang.",
            reply_markup=active_chat_keyboard(),
        )
        return ConversationHandler.END

    context.user_data[
        "registration"
    ] = {}

    await query.message.reply_text(
        (
            "📝 <b>Yangi hamkor bo'lish</b>\n\n"
            "Avval rasmiy saytda ro'yxatdan o'ting:\n"
            f"🔗 {escape(REGISTRATION_URL)}\n\n"
            "Endi trafik manbangizni yuboring.\n\n"
            "Masalan:\n"
            "• Telegram kanal\n"
            "• Instagram\n"
            "• YouTube\n"
            "• TikTok\n"
            "• Sayt\n\n"
            "❌ Bekor qilish uchun /cancel yozing."
        ),
        parse_mode=ParseMode.HTML,
    )

    return REG_SOURCE


async def registration_source_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    context.user_data[
        "registration"
    ]["source"] = (
        update.effective_message.text.strip()
    )

    await update.effective_message.reply_text(
        (
            "💰 <b>Hamkorlik modelini tanlang:</b>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=registration_models_keyboard(),
    )

    return REG_MODEL


async def registration_model_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    query = update.callback_query
    await query.answer()

    model = query.data.split(
        ":",
        1,
    )[1]

    context.user_data[
        "registration"
    ]["model"] = model

    await query.message.reply_text(
        (
            "📧 <b>Email manzilingizni yuboring:</b>\n\n"
            "Masalan: name@gmail.com"
        ),
        parse_mode=ParseMode.HTML,
    )

    return REG_EMAIL


async def registration_email_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    email = (
        update.effective_message.text.strip()
    )

    if not EMAIL_RE.match(
        email
    ):
        await update.effective_message.reply_text(
            (
                "⚠️ <b>Email noto'g'ri.</b>\n\n"
                "Masalan: name@gmail.com"
            ),
            parse_mode=ParseMode.HTML,
        )

        return REG_EMAIL

    context.user_data[
        "registration"
    ]["email"] = email

    await update.effective_message.reply_text(
        (
            "🔗 <b>Telegram username yuboring:</b>\n\n"
            "Masalan: @username"
        ),
        parse_mode=ParseMode.HTML,
    )

    return REG_USERNAME


async def registration_username_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    username_value = (
        update.effective_message.text.strip()
    )

    if not USERNAME_RE.match(
        username_value
    ):
        await update.effective_message.reply_text(
            (
                "⚠️ <b>Username noto'g'ri.</b>\n\n"
                "Masalan: @username"
            ),
            parse_mode=ParseMode.HTML,
        )

        return REG_USERNAME

    context.user_data[
        "registration"
    ]["telegram_username"] = username_value

    await update.effective_message.reply_text(
        (
            "🌍 <b>Qaysi GEO bo'yicha trafik olib kelasiz?</b>"
        ),
        parse_mode=ParseMode.HTML,
    )

    return REG_GEO


async def registration_geo_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    context.user_data[
        "registration"
    ]["geo"] = (
        update.effective_message.text.strip()
    )

    await update.effective_message.reply_text(
        (
            "📢 <b>Qanday reklama usullaridan foydalanasiz?</b>\n\n"
            "Masalan: Telegram, Instagram, YouTube, TikTok yoki SEO."
        ),
        parse_mode=ParseMode.HTML,
    )

    return REG_PROMO
  async def registration_promo_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    user = update.effective_user

    registration = context.user_data.get(
        "registration",
        {},
    )

    registration["promo"] = (
        update.effective_message.text.strip()
    )

    partner_id = add_partner(
        user_id=user.id,
        source=registration.get(
            "source",
            "—",
        ),
        model=registration.get(
            "model",
            "—",
        ),
        email=registration.get(
            "email",
            "—",
        ),
        telegram_username=registration.get(
            "telegram_username",
            "—",
        ),
        geo=registration.get(
            "geo",
            "—",
        ),
        promo=registration.get(
            "promo",
            "—",
        ),
    )

    admin_text = (
        "👥 <b>YANGI HAMKOR</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"👤 <b>Ism:</b> "
        f"{escape(user_full_name(user))}\n"

        f"🔗 <b>Username:</b> "
        f"{escape(registration.get('telegram_username'))}\n"

        f"🆔 <b>Telegram ID:</b> "
        f"<code>{user.id}</code>\n"

        f"📧 <b>Email:</b> "
        f"{escape(registration.get('email'))}\n"

        f"🌍 <b>GEO:</b> "
        f"{escape(registration.get('geo'))}\n"

        f"💰 <b>Model:</b> "
        f"{escape(registration.get('model'))}\n"

        f"📢 <b>Trafik manbasi:</b> "
        f"{escape(registration.get('source'))}\n"

        f"🎯 <b>Reklama usuli:</b> "
        f"{escape(registration.get('promo'))}\n"

        f"🔢 <b>Hamkor №:</b> "
        f"<code>{partner_id}</code>\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "↩️ <b>Hamkorga javob berish uchun "
        "shu xabarga Reply qiling.</b>"
    )

    try:
        admin_message = await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_text,
            parse_mode=ParseMode.HTML,
        )

        link_admin_message(
            admin_message_id=admin_message.message_id,
            user_id=user.id,
            ticket_id=None,
        )

        await update.effective_message.reply_text(
            (
                "✅ <b>Ma'lumotlaringiz Tommy'ga yuborildi.</b>\n\n"
                "Tommy ma'lumotlaringizni ko'rib chiqib, "
                "shu chat orqali siz bilan bog'lanadi."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )

    except TelegramError as error:
        logger.exception(
            "Yangi hamkor admin'ga yuborilmadi: %s",
            error,
        )

        await update.effective_message.reply_text(
            (
                "⚠️ Ma'lumotlarni yuborishda texnik xato yuz berdi.\n"
                "Iltimos, keyinroq qayta urinib ko'ring."
            )
        )

    context.user_data.pop(
        "registration",
        None,
    )

    return ConversationHandler.END


async def registration_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    context.user_data.pop(
        "registration",
        None,
    )

    context.user_data.pop(
        "waiting_ai_question",
        None,
    )

    if update.callback_query:
        await update.callback_query.answer()

        await update.callback_query.message.reply_text(
            "❌ Ro'yxatdan o'tish bekor qilindi.",
            reply_markup=main_keyboard(),
        )

    else:
        await update.effective_message.reply_text(
            "❌ Amal bekor qilindi.",
            reply_markup=main_keyboard(),
        )

    return ConversationHandler.END


# ============================================================
# FOYDALANUVCHI XABARLARI
# ============================================================

async def user_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user = update.effective_user
    message = update.effective_message

    if not user or not message:
        return

    if user.id == ADMIN_CHAT_ID:
        return

    save_user(
        update
    )

    text = get_message_text(
        message
    )

    # --------------------------------------------------------
    # AI SAVOLI
    # --------------------------------------------------------

    if context.user_data.get(
        "waiting_ai_question"
    ):
        context.user_data[
            "waiting_ai_question"
        ] = False

        await message.reply_text(
            "🤖 Savolingiz tahlil qilinmoqda..."
        )

        answer = await get_ai_answer(
            text
        )

        if not answer:
            answer = (
                "🤖 <b>AI yordamchi hozir tashqi xizmatga ulanmagan.</b>\n\n"

                "📌 FTD va konversiyani oshirish uchun:\n\n"
                "1️⃣ Auditoriyani GEO va qiziqishiga qarab ajrating.\n"
                "2️⃣ Kamida 3 xil kreativni A/B test qiling.\n"
                "3️⃣ Postda aniq CTA yozing.\n"
                "4️⃣ Promo-kod foydasini yuqorida ko'rsating.\n"
                "5️⃣ CTR, registratsiya va FTD ni alohida tahlil qiling."
            )

        await message.reply_text(
            answer
            + (
                "\n\n💬 Yana savolingiz bo'lsa AI yordamchiga "
                "yozishingiz yoki Tommy bilan bog'lanishingiz mumkin."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=partners_keyboard(),
        )

        return

    # --------------------------------------------------------
    # BANNER SO'ROVI
    # --------------------------------------------------------

    banner_request = context.user_data.pop(
        "banner_request",
        None,
    )

    if banner_request:
        promo = text.strip().upper()

        category = banner_request[
            "category"
        ]

        banner_type = banner_request[
            "type"
        ]

        banner_path = find_banner_path(
            category=category,
            banner_type=banner_type,
        )

        if banner_path:
            try:
                with banner_path.open(
                    "rb"
                ) as banner_file:

                    await context.bot.send_photo(
                        chat_id=message.chat_id,
                        photo=banner_file,
                        caption=(
                            "🖼 <b>Tayyor banner</b>\n\n"
                            f"🔑 Promo-kod: <code>{escape(promo)}</code>\n\n"
                            "📌 Hozirgi versiyada rasm fayli tayyor holatda "
                            "yuboriladi. Promo-kod banner dizaynida oldindan "
                            "joylashtirilgan bo'lishi kerak."
                        ),
                        parse_mode=ParseMode.HTML,
                        reply_markup=partners_keyboard(),
                    )

            except TelegramError as error:
                logger.exception(
                    "Banner yuborilmadi: %s",
                    error,
                )

                await message.reply_text(
                    "⚠️ Bannerni yuborishda xato yuz berdi.",
                    reply_markup=partners_keyboard(),
                )

        else:
            expected_path = (
                ASSET_DIR
                / "banners"
                / category
                / f"{banner_type}.png"
            )

            await message.reply_text(
                (
                    "⚠️ <b>Banner fayli hali joylanmagan.</b>\n\n"
                    "GitHub repository ichida quyidagi manzilga "
                    "tayyor PNG yoki JPG banner joylashtiring:\n\n"
                    f"<code>{escape(expected_path)}</code>\n\n"
                    f"🔑 So'ralgan promo-kod: <code>{escape(promo)}</code>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=partners_keyboard(),
            )

        return

    # --------------------------------------------------------
    # TAYYOR POST SO'ROVI
    # --------------------------------------------------------

    post_request = context.user_data.pop(
        "post_request",
        None,
    )

    if post_request:
        promo = text.strip().upper()

        post_key = (
            f"{post_request['category']}_"
            f"{post_request['type']}"
        )

        prepared_post = format_post(
            post_key=post_key,
            promo=promo,
        )

        await message.reply_text(
            prepared_post,
            parse_mode=ParseMode.HTML,
            reply_markup=partners_keyboard(),
        )

        return

    # --------------------------------------------------------
    # TOMMY BILAN FAOL SUHBAT
    # --------------------------------------------------------

    if is_locked(context):
        user_session = get_session(
            context
        )

        ticket_id = user_session.get(
            "ticket_id"
        )

        if not ticket_id:
            ticket_id = create_ticket(
                user_id=user.id,
                category=(
                    user_session.get(
                        "category"
                    )
                    or "other"
                ),
                text=text,
            )

            user_session[
                "ticket_id"
            ] = ticket_id

        admin_caption = (
            "📩 <b>YANGI MUROJAAT</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            f"👤 <b>Ism:</b> "
            f"{escape(user_full_name(user))}\n"

            f"🔗 <b>Username:</b> "
            f"{escape(user_username(user))}\n"

            f"🆔 <b>Telegram ID:</b> "
            f"<code>{user.id}</code>\n"

            f"📂 <b>Bo'lim:</b> "
            f"{escape(user_session.get('category'))}\n"

            f"🔢 <b>Murojaat №:</b> "
            f"<code>{ticket_id}</code>\n\n"

            f"💬 <b>Xabar:</b>\n"
            f"{escape(text)}\n\n"

            "━━━━━━━━━━━━━━━━━━\n"
            "↩️ <b>Javob berish uchun shu xabarga Reply qiling.</b>"
        )

        try:
            if message.text:
                admin_message = await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=admin_caption,
                    parse_mode=ParseMode.HTML,
                )

            else:
                admin_message = await context.bot.copy_message(
                    chat_id=ADMIN_CHAT_ID,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id,
                    caption=admin_caption,
                    parse_mode=ParseMode.HTML,
                )

            link_admin_message(
                admin_message_id=admin_message.message_id,
                user_id=user.id,
                ticket_id=int(ticket_id),
            )

            await message.reply_text(
                (
                    "✅ <b>Murojaatingiz Tommy'ga yuborildi.</b>\n\n"
                    "Iltimos, kuting. Tommy tez orada "
                    "shu chat orqali javob beradi."
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=active_chat_keyboard(),
            )

        except TelegramError as error:
            logger.exception(
                "Murojaat admin'ga yuborilmadi: %s",
                error,
            )

            await message.reply_text(
                (
                    "⚠️ Murojaatni yuborishda texnik xato yuz berdi.\n"
                    "Iltimos, birozdan keyin yana urinib ko'ring."
                ),
                reply_markup=active_chat_keyboard(),
            )

        return

    # --------------------------------------------------------
    # HECH QANDAY REJIM TANLANMAGAN
    # --------------------------------------------------------

    await message.reply_text(
        (
            "👇 Savol yuborishdan oldin kerakli bo'limni tanlang."
        ),
        reply_markup=main_keyboard(),
    )


# ============================================================
# ADMINNING REPLY ORQALI JAVOB BERISHI
# ============================================================

async def admin_reply_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    message = update.effective_message
    admin_user = update.effective_user

    if not admin_user or not message:
        return

    if admin_user.id != ADMIN_CHAT_ID:
        return

    if not message.reply_to_message:
        return

    original_admin_message_id = (
        message.reply_to_message.message_id
    )

    link = get_admin_link(
        original_admin_message_id
    )

    if not link:
        await message.reply_text(
            (
                "⚠️ <b>Javob yuborilmadi.</b>\n\n"
                "Foydalanuvchiga javob berish uchun bot yuborgan "
                "murojaat yoki yangi hamkor xabariga Reply qiling."
            ),
            parse_mode=ParseMode.HTML,
        )

        return

    user_id = int(
        link["user_id"]
    )

    try:
        if message.text:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "📩 <b>Tommy'dan javob:</b>\n\n"
                    + escape(message.text)
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=active_chat_keyboard(),
            )

        else:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=ADMIN_CHAT_ID,
                message_id=message.message_id,
                caption=(
                    "📩 <b>Tommy'dan javob:</b>\n\n"
                    + escape(
                        message.caption or ""
                    )
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=active_chat_keyboard(),
            )

        await message.reply_text(
            (
                "✅ <b>JAVOB YUBORILDI</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 <b>Foydalanuvchi ID:</b> "
                f"<code>{user_id}</code>\n"
                "📩 <b>Holat:</b> Muvaffaqiyatli yuborildi"
            ),
            parse_mode=ParseMode.HTML,
        )

    except Forbidden:
        await message.reply_text(
            (
                "❌ <b>Javob yuborilmadi.</b>\n\n"
                "Foydalanuvchi botni bloklagan."
            ),
            parse_mode=ParseMode.HTML,
        )

    except TelegramError as error:
        logger.exception(
            "Admin javobi yuborilmadi: %s",
            error,
        )

        await message.reply_text(
            (
                "❌ <b>Javob yuborilmadi.</b>\n\n"
                f"<code>{escape(error)}</code>"
            ),
            parse_mode=ParseMode.HTML,
        )


# ============================================================
# ADMIN PANEL
# ============================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not update.effective_user:
        return

    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    statistics = stats()

    await update.effective_message.reply_text(
        (
            "🛠 <b>TOMMY ADMIN PANEL</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            f"👤 <b>Bot foydalanuvchilari:</b> "
            f"{statistics['users']}\n"

            f"📩 <b>Ochiq murojaatlar:</b> "
            f"{statistics['open']}\n"

            f"✅ <b>Yopilgan murojaatlar:</b> "
            f"{statistics['closed']}\n"

            f"👥 <b>Yangi hamkorlar:</b> "
            f"{statistics['partners']}\n\n"

            "👇 Kerakli bo'limni tanlang:"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


async def admin_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    if query.from_user.id != ADMIN_CHAT_ID:
        await query.answer(
            "Sizga ruxsat berilmagan.",
            show_alert=True,
        )

        return

    await query.answer()

    action = query.data.split(
        ":",
        1,
    )[1]

    if action == "stats":
        statistics = stats()

        await query.message.reply_text(
            (
                "📊 <b>BOT STATISTIKASI</b>\n\n"

                f"👤 Foydalanuvchilar: "
                f"{statistics['users']}\n"

                f"📩 Ochiq murojaatlar: "
                f"{statistics['open']}\n"

                f"✅ Yopilgan murojaatlar: "
                f"{statistics['closed']}\n"

                f"👥 Yangi hamkorlar: "
                f"{statistics['partners']}"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )

        return

    if action == "tickets":
        with db() as con:
            rows = con.execute(
                """
                SELECT
                    tickets.*,
                    users.first_name,
                    users.last_name,
                    users.username
                FROM tickets
                LEFT JOIN users
                    ON users.user_id = tickets.user_id
                WHERE tickets.status = 'open'
                ORDER BY tickets.id DESC
                LIMIT 10
                """
            ).fetchall()

        if not rows:
            await query.message.reply_text(
                "✅ Ochiq murojaatlar mavjud emas.",
                reply_markup=admin_keyboard(),
            )

            return

        text = (
            "📩 <b>OXIRGI 10 TA OCHIQ MUROJAAT</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
        )

        for row in rows:
            name = " ".join(
                part
                for part in [
                    row["first_name"] or "",
                    row["last_name"] or "",
                ]
                if part
            ).strip()

            if not name:
                name = "Noma'lum"

            username_value = (
                f"@{row['username']}"
                if row["username"]
                else "Username yo'q"
            )

            short_text = (
                row["text"]
                or "Media xabar"
            )[:150]

            text += (
                f"🔢 <b>№{row['id']}</b>\n"
                f"👤 {escape(name)}\n"
                f"🔗 {escape(username_value)}\n"
                f"📂 {escape(row['category'])}\n"
                f"💬 {escape(short_text)}\n"
                f"📅 {escape(row['created_at'])}\n\n"
            )

        text += (
            "━━━━━━━━━━━━━━━━━━\n"
            "↩️ Javob berish uchun original murojaat "
            "xabariga Reply qiling."
        )

        await query.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )

        return

    if action == "partners":
        with db() as con:
            rows = con.execute(
                """
                SELECT *
                FROM partners
                ORDER BY id DESC
                LIMIT 10
                """
            ).fetchall()

        if not rows:
            await query.message.reply_text(
                "👥 Hozircha yangi hamkorlar mavjud emas.",
                reply_markup=admin_keyboard(),
            )

            return

        text = (
            "👥 <b>OXIRGI 10 TA YANGI HAMKOR</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
        )

        for row in rows:
            text += (
                f"🔢 <b>№{row['id']}</b>\n"
                f"🔗 {escape(row['telegram_username'])}\n"
                f"📧 {escape(row['email'])}\n"
                f"🌍 {escape(row['geo'])}\n"
                f"💰 {escape(row['model'])}\n"
                f"📢 {escape(row['source'])}\n"
                f"📅 {escape(row['created_at'])}\n\n"
            )

        await query.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )


# ============================================================
# XATOLARNI BOSHQARISH
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    logger.error(
        "Bot xatosi: %s",
        context.error,
        exc_info=context.error,
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "⚠️ <b>BOT XATOSI</b>\n\n"
                f"<code>{escape(context.error)}</code>"
            ),
            parse_mode=ParseMode.HTML,
        )

    except Exception:
        logger.exception(
            "Xato haqida admin'ga xabar yuborilmadi."
        )


# ============================================================
# BOT HANDLERLARI
# ============================================================

def build_application() -> Application:

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    registration_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                registration_start,
                pattern=r"^register:start$",
            )
        ],

        states={
            REG_SOURCE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    registration_source_received,
                )
            ],

            REG_MODEL: [
                CallbackQueryHandler(
                    registration_model_selected,
                    pattern=r"^reg_model:",
                )
            ],

            REG_EMAIL: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    registration_email_received,
                )
            ],

            REG_USERNAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    registration_username_received,
                )
            ],

            REG_GEO: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    registration_geo_received,
                )
            ],

            REG_PROMO: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    registration_promo_received,
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                registration_cancel,
            )
        ],

        allow_reentry=True,
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            registration_cancel,
        )
    )

    application.add_handler(
        registration_handler
    )

    application.add_handler(
        CallbackQueryHandler(
            main_callback,
            pattern=r"^main:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            model_callback,
            pattern=r"^model:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            tip_callback,
            pattern=r"^tip:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            payment_callback,
            pattern=r"^payment:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            partner_callback,
            pattern=r"^partner:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            banner_category_callback,
            pattern=r"^banner_category:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            banner_type_callback,
            pattern=r"^banner_type:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            post_category_callback,
            pattern=r"^post_category:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            post_type_callback,
            pattern=r"^post_type:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            contact_callback,
            pattern=r"^contact:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            contact_start_callback,
            pattern=r"^contact_start:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            chat_cancel_callback,
            pattern=r"^chat:cancel$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern=r"^admin:",
        )
    )

    application.add_handler(
        MessageHandler(
            filters.User(
                user_id=ADMIN_CHAT_ID
            )
            & filters.REPLY
            & (
                filters.TEXT
                | filters.PHOTO
                | filters.VIDEO
                | filters.Document.ALL
                | filters.VOICE
                | filters.AUDIO
            ),
            admin_reply_handler,
        )
    )

    application.add_handler(
        MessageHandler(
            ~filters.COMMAND
            & ~filters.User(
                user_id=ADMIN_CHAT_ID
            )
            & (
                filters.TEXT
                | filters.PHOTO
                | filters.VIDEO
                | filters.Document.ALL
                | filters.VOICE
                | filters.AUDIO
            ),
            user_message_handler,
        )
    )

    application.add_error_handler(
        error_handler
    )

    return application


# ============================================================
# ISHGA TUSHIRISH
# ============================================================

def main() -> None:

    init_db()

    logger.info(
        "Tommy Partners Bot ishga tushdi."
    )

    application = build_application()

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
