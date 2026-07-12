"""
Tommy Partners Bot — sodda va ishonchli admin panel.

O'RNATISH:
    pip install -U python-telegram-bot python-dotenv

RAILWAY VARIABLES:
    BOT_TOKEN=...
    ADMIN_CHAT_ID=...
    REGISTRATION_URL=https://Luckyparipartners.com

ISHGA TUSHIRISH:
    python bot.py
"""

import html
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
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

# ============================================================
# 1. SOZLAMALAR
# ============================================================

load_dotenv()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"{name} topilmadi. Railway Variables bo'limiga kiriting."
        )

    return value


BOT_TOKEN = required_env("BOT_TOKEN")
ADMIN_CHAT_ID = int(required_env("ADMIN_CHAT_ID"))

REGISTRATION_URL = os.getenv(
    "REGISTRATION_URL",
    "https://Luckyparipartners.com",
).strip()

DB_PATH = Path(
    os.getenv(
        "DB_PATH",
        "tommy_bot.db",
    )
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("tommy_bot")

EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)

USERNAME_RE = re.compile(
    r"^@[A-Za-z0-9_]{3,32}$"
)

# Ro'yxatdan o'tish bosqichlari
REG_SOURCE, REG_MODEL, REG_EMAIL, REG_USERNAME, REG_GEO, REG_PROMO = range(6)


# ============================================================
# 2. MA'LUMOTLAR BAZASI
# ============================================================

def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with db_connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                language TEXT DEFAULT 'uz',
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                message_type TEXT NOT NULL,
                message_text TEXT,
                file_id TEXT,
                admin_message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                answered_at TEXT
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
                admin_message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_links (
                admin_message_id INTEGER PRIMARY KEY,
                target_user_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                item_id INTEGER,
                created_at TEXT NOT NULL
            );
            """
        )


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def save_user(
    update: Update,
    language: str | None = None,
) -> None:
    user = update.effective_user

    if not user:
        return

    timestamp = now_iso()

    with db_connect() as connection:
        row = connection.execute(
            "SELECT language FROM users WHERE user_id = ?",
            (user.id,),
        ).fetchone()

        saved_language = language or (
            row["language"] if row else "uz"
        )

        connection.execute(
            """
            INSERT INTO users (
                user_id,
                first_name,
                last_name,
                username,
                language,
                created_at,
                last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(user_id) DO UPDATE SET
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                username = excluded.username,
                language = excluded.language,
                last_seen_at = excluded.last_seen_at
            """,
            (
                user.id,
                user.first_name or "",
                user.last_name or "",
                user.username or "",
                saved_language,
                timestamp,
                timestamp,
            ),
        )


def get_user_language(user_id: int) -> str:
    with db_connect() as connection:
        row = connection.execute(
            "SELECT language FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if row:
        return row["language"]

    return "uz"


def add_admin_link(
    admin_message_id: int,
    target_user_id: int,
    item_type: str,
    item_id: int | None,
) -> None:
    with db_connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO admin_links (
                admin_message_id,
                target_user_id,
                item_type,
                item_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                admin_message_id,
                target_user_id,
                item_type,
                item_id,
                now_iso(),
            ),
        )


def get_admin_link(
    admin_message_id: int,
) -> sqlite3.Row | None:
    with db_connect() as connection:
        return connection.execute(
            """
            SELECT *
            FROM admin_links
            WHERE admin_message_id = ?
            """,
            (admin_message_id,),
        ).fetchone()


def add_question(
    user_id: int,
    category: str,
    message_type: str,
    message_text: str | None,
    file_id: str | None,
) -> int:
    with db_connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO questions (
                user_id,
                category,
                message_type,
                message_text,
                file_id,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                user_id,
                category,
                message_type,
                message_text,
                file_id,
                now_iso(),
            ),
        )

        return int(cursor.lastrowid)


def set_question_admin_message(
    question_id: int,
    admin_message_id: int,
) -> None:
    with db_connect() as connection:
        connection.execute(
            """
            UPDATE questions
            SET admin_message_id = ?
            WHERE id = ?
            """,
            (
                admin_message_id,
                question_id,
            ),
        )


def mark_question_answered(
    question_id: int,
) -> None:
    with db_connect() as connection:
        connection.execute(
            """
            UPDATE questions
            SET status = 'answered',
                answered_at = ?
            WHERE id = ?
            """,
            (
                now_iso(),
                question_id,
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
    with db_connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO partners (
                user_id,
                source,
                model,
                email,
                telegram_username,
                geo,
                promo,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)
            """,
            (
                user_id,
                source,
                model,
                email,
                telegram_username,
                geo,
                promo,
                now_iso(),
            ),
        )

        return int(cursor.lastrowid)


def set_partner_admin_message(
    partner_id: int,
    admin_message_id: int,
) -> None:
    with db_connect() as connection:
        connection.execute(
            """
            UPDATE partners
            SET admin_message_id = ?
            WHERE id = ?
            """,
            (
                admin_message_id,
                partner_id,
            ),
        )


def get_statistics() -> dict[str, int]:
    with db_connect() as connection:
        users_count = connection.execute(
            "SELECT COUNT(*) AS total FROM users"
        ).fetchone()["total"]

        partners_count = connection.execute(
            "SELECT COUNT(*) AS total FROM partners"
        ).fetchone()["total"]

        new_partners_count = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM partners
            WHERE status = 'new'
            """
        ).fetchone()["total"]

        pending_questions = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM questions
            WHERE status = 'pending'
            """
        ).fetchone()["total"]

        answered_questions = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM questions
            WHERE status = 'answered'
            """
        ).fetchone()["total"]

    return {
        "users": users_count,
        "partners": partners_count,
        "new_partners": new_partners_count,
        "pending": pending_questions,
        "answered": answered_questions,
    }


# ============================================================
# 3. TILLAR VA MATNLAR
# ============================================================

TEXTS = {
    "uz": {
        "choose_language": (
            "🌐 <b>Tilni tanlang:</b>"
        ),

        "welcome": (
            "👋 <b>Tommy Partners yordam botiga xush kelibsiz!</b>\n\n"
            "Bu bot orqali hamkorlik bo'yicha ma'lumot olishingiz, "
            "yangi hamkor sifatida ro'yxatdan o'tishingiz yoki Tommy'ga "
            "to'g'ridan-to'g'ri savol yuborishingiz mumkin.\n\n"
            "👇 Kerakli bo'limni tanlang:"
        ),

        "models": "💰 Hamkorlik modellari",
        "register": "📝 Yangi hamkor bo'lish",
        "partner": "📈 Mavjud hamkorlar yordami",
        "payment": "💳 To'lov bo'yicha savol",
        "other": "✉️ Boshqa savol",
        "back": "⬅️ Asosiy menyu",

        "models_text": (
            "💰 <b>HAMKORLIK MODELLARI</b>\n\n"

            "🔹 <b>CPA</b>\n"
            "Har bir tasdiqlangan FTD uchun kelishilgan qat'iy to'lov.\n\n"

            "🔹 <b>RevShare (RS)</b>\n"
            "Jalb qilingan o'yinchilardan tushgan daromadning "
            "kelishilgan foizi.\n\n"

            "🔹 <b>Hybrid</b>\n"
            "CPA va RevShare birgalikda ishlaydigan model.\n\n"

            "🔹 <b>Postpay</b>\n"
            "To'lov kelishilgan KPI bajarilgandan keyin beriladi.\n\n"

            "🔹 <b>Fix</b>\n"
            "Reklama joylashtirish uchun kelishilgan qat'iy summa.\n\n"

            "📌 Aniq shartlar trafik manbasi va statistika "
            "asosida Tommy bilan individual kelishiladi."
        ),

        "ask_partner": (
            "📈 <b>MAVJUD HAMKORLAR YORDAMI</b>\n\n"
            "Savol yoki muammoingizni batafsil yozing.\n\n"

            "Masalan:\n"
            "• FTD yoki konversiya masalasi\n"
            "• Promo-material kerak\n"
            "• Shaxsiy hamkorlik sharti\n"
            "• Affiliate hisob muammosi\n"
            "• Texnik yordam\n\n"

            "📩 Xabaringiz Tommy'ga yuboriladi."
        ),

        "ask_payment": (
            "💳 <b>TO'LOV BO'YICHA MUROJAAT</b>\n\n"
            "Muammoni batafsil yozing.\n\n"

            "Imkon bo'lsa quyidagilarni kiriting:\n\n"
            "🆔 Affiliate ID\n"
            "💵 To'lov summasi\n"
            "📅 To'lov sanasi\n"
            "💳 To'lov usuli\n"
            "📝 Muammo tavsifi\n\n"

            "📩 Xabaringiz Tommy'ga yuboriladi."
        ),

        "ask_other": (
            "✉️ <b>BOSHQA SAVOL</b>\n\n"
            "Savolingizni yoki murojaatingizni batafsil yozing.\n\n"
            "📩 Xabaringiz Tommy'ga yuboriladi va javob shu chatga keladi."
        ),

        "sent": (
            "✅ <b>Xabaringiz Tommy'ga yuborildi.</b>\n\n"
            "Tommy javob berganda javob avtomatik ravishda "
            "shu chatga keladi."
        ),

        "reply": (
            "📩 <b>Tommy'dan javob:</b>\n\n"
        ),

        "reg_source": (
            "📝 <b>YANGI HAMKOR BO'LISH</b>\n\n"
            "Avval rasmiy saytda ro'yxatdan o'ting:\n"
            f"🔗 {REGISTRATION_URL}\n\n"

            "Endi trafik manbangizni yuboring.\n\n"

            "Masalan:\n"
            "• Telegram kanal havolasi\n"
            "• Instagram sahifasi\n"
            "• YouTube kanali\n"
            "• TikTok sahifasi\n"
            "• Sayt yoki boshqa trafik manbasi\n\n"

            "Agar hali trafik manbangiz bo'lmasa, "
            "“yo'q” deb yozishingiz mumkin.\n\n"

            "❌ Bekor qilish: /cancel"
        ),

        "reg_model": (
            "💰 <b>Hamkorlik modelini tanlang:</b>"
        ),

        "reg_email": (
            "📧 <b>Email manzilingizni yuboring:</b>\n\n"
            "Masalan: name@gmail.com"
        ),

        "reg_username": (
            "🔗 <b>Telegram username'ingizni yuboring:</b>\n\n"
            "Masalan: @username"
        ),

        "reg_geo": (
            "🌍 <b>Qaysi davlatlar yoki GEO bo'yicha "
            "trafik olib kelasiz?</b>\n\n"

            "Masalan: Uzbekistan, CIS, Turkey yoki boshqa GEO."
        ),

        "reg_promo": (
            "📢 <b>Qanday reklama usullaridan foydalanasiz?</b>\n\n"

            "Masalan:\n"
            "• Telegram postlar\n"
            "• Instagram Stories/Reels\n"
            "• YouTube\n"
            "• TikTok\n"
            "• Facebook yoki Google Ads\n"
            "• SEO\n\n"

            "Hali aniq bo'lmasa, “yo'q” deb yozing."
        ),

        "invalid_email": (
            "⚠️ <b>Email noto'g'ri yozilgan.</b>\n\n"
            "To'g'ri formatda qayta yuboring.\n"
            "Masalan: name@gmail.com"
        ),

        "invalid_username": (
            "⚠️ <b>Telegram username noto'g'ri.</b>\n\n"
            "Username @ belgisi bilan boshlanishi kerak.\n"
            "Masalan: @username"
        ),

        "registered": (
            "✅ <b>Ma'lumotlaringiz Tommy'ga yuborildi!</b>\n\n"
            "Tommy ma'lumotlaringizni ko'rib chiqib, "
            "Telegram orqali siz bilan bog'lanadi."
        ),

        "cancelled": (
            "❌ Ro'yxatdan o'tish bekor qilindi."
        ),

        "send_text_or_media": (
            "⚠️ Iltimos, savolingizni matn, rasm, video, "
            "ovozli xabar yoki fayl shaklida yuboring."
        ),
    },

    "ru": {
        "choose_language": (
            "🌐 <b>Выберите язык:</b>"
        ),

        "welcome": (
            "👋 <b>Добро пожаловать в бот поддержки Tommy Partners!</b>\n\n"
            "Здесь вы можете получить информацию о сотрудничестве, "
            "зарегистрироваться как новый партнёр или отправить "
            "вопрос напрямую Tommy.\n\n"
            "👇 Выберите нужный раздел:"
        ),

        "models": "💰 Модели сотрудничества",
        "register": "📝 Стать новым партнёром",
        "partner": "📈 Помощь действующим партнёрам",
        "payment": "💳 Вопрос по выплате",
        "other": "✉️ Другой вопрос",
        "back": "⬅️ Главное меню",

        "models_text": (
            "💰 <b>МОДЕЛИ СОТРУДНИЧЕСТВА</b>\n\n"

            "🔹 <b>CPA</b>\n"
            "Фиксированная выплата за каждый подтверждённый FTD.\n\n"

            "🔹 <b>RevShare (RS)</b>\n"
            "Согласованный процент от дохода привлечённых игроков.\n\n"

            "🔹 <b>Hybrid</b>\n"
            "Совместное использование CPA и RevShare.\n\n"

            "🔹 <b>Postpay</b>\n"
            "Оплата после выполнения согласованных KPI.\n\n"

            "🔹 <b>Fix</b>\n"
            "Фиксированная сумма за рекламное размещение.\n\n"

            "📌 Точные условия обсуждаются с Tommy индивидуально "
            "на основе источника и статистики трафика."
        ),

        "ask_partner": (
            "📈 <b>ПОМОЩЬ ДЕЙСТВУЮЩИМ ПАРТНЁРАМ</b>\n\n"
            "Подробно опишите ваш вопрос или проблему.\n\n"

            "Например:\n"
            "• FTD или конверсия\n"
            "• Нужны промоматериалы\n"
            "• Индивидуальные условия\n"
            "• Проблема с affiliate-аккаунтом\n"
            "• Техническая помощь\n\n"

            "📩 Сообщение будет отправлено Tommy."
        ),

        "ask_payment": (
            "💳 <b>ВОПРОС ПО ВЫПЛАТЕ</b>\n\n"
            "Подробно опишите проблему.\n\n"

            "По возможности укажите:\n\n"
            "🆔 Affiliate ID\n"
            "💵 Сумму выплаты\n"
            "📅 Дату выплаты\n"
            "💳 Способ оплаты\n"
            "📝 Описание проблемы\n\n"

            "📩 Сообщение будет отправлено Tommy."
        ),

        "ask_other": (
            "✉️ <b>ДРУГОЙ ВОПРОС</b>\n\n"
            "Подробно напишите ваш вопрос или обращение.\n\n"
            "📩 Сообщение будет отправлено Tommy, "
            "а ответ придёт в этот чат."
        ),

        "sent": (
            "✅ <b>Ваше сообщение отправлено Tommy.</b>\n\n"
            "Когда Tommy ответит, сообщение автоматически "
            "появится в этом чате."
        ),

        "reply": (
            "📩 <b>Ответ от Tommy:</b>\n\n"
        ),

        "reg_source": (
            "📝 <b>РЕГИСТРАЦИЯ НОВОГО ПАРТНЁРА</b>\n\n"
            "Сначала зарегистрируйтесь на официальном сайте:\n"
            f"🔗 {REGISTRATION_URL}\n\n"

            "Теперь отправьте источник трафика.\n\n"

            "Например:\n"
            "• Ссылка на Telegram-канал\n"
            "• Instagram\n"
            "• YouTube\n"
            "• TikTok\n"
            "• Сайт или другой источник\n\n"

            "Если источника пока нет, напишите «нет».\n\n"

            "❌ Отмена: /cancel"
        ),

        "reg_model": (
            "💰 <b>Выберите модель сотрудничества:</b>"
        ),

        "reg_email": (
            "📧 <b>Отправьте ваш email:</b>\n\n"
            "Например: name@gmail.com"
        ),

        "reg_username": (
            "🔗 <b>Отправьте ваш Telegram username:</b>\n\n"
            "Например: @username"
        ),

        "reg_geo": (
            "🌍 <b>По каким странам или GEO "
            "вы направляете трафик?</b>\n\n"

            "Например: Uzbekistan, CIS, Turkey или другое GEO."
        ),

        "reg_promo": (
            "📢 <b>Какие рекламные источники вы используете?</b>\n\n"

            "Например:\n"
            "• Telegram\n"
            "• Instagram Stories/Reels\n"
            "• YouTube\n"
            "• TikTok\n"
            "• Facebook или Google Ads\n"
            "• SEO\n\n"

            "Если пока не определились, напишите «нет»."
        ),

        "invalid_email": (
            "⚠️ <b>Email указан неверно.</b>\n\n"
            "Отправьте адрес в правильном формате.\n"
            "Например: name@gmail.com"
        ),

        "invalid_username": (
            "⚠️ <b>Неверный Telegram username.</b>\n\n"
            "Username должен начинаться с символа @.\n"
            "Например: @username"
        ),

        "registered": (
            "✅ <b>Ваши данные отправлены Tommy!</b>\n\n"
            "Tommy рассмотрит информацию и свяжется "
            "с вами через Telegram."
        ),

        "cancelled": (
            "❌ Регистрация отменена."
        ),

        "send_text_or_media": (
            "⚠️ Отправьте вопрос в виде текста, изображения, "
            "видео, голосового сообщения или файла."
        ),
    },
}

    "en": {
        "choose_language": "🌐 <b>Choose your language:</b>",

        "welcome": (
            "👋 <b>Welcome to Tommy Partners Support Bot!</b>\n\n"
            "Here you can get cooperation information, register as a new "
            "partner or send a question directly to Tommy.\n\n"
            "👇 Choose a section:"
        ),

        "models": "💰 Cooperation models",
        "register": "📝 Become a new partner",
        "partner": "📈 Existing partner support",
        "payment": "💳 Payment question",
        "other": "✉️ Other question",
        "back": "⬅️ Main menu",

        "models_text": (
            "💰 <b>COOPERATION MODELS</b>\n\n"
            "🔹 <b>CPA</b>\n"
            "A fixed payment for each confirmed FTD.\n\n"
            "🔹 <b>RevShare (RS)</b>\n"
            "An agreed percentage of revenue generated by referred players.\n\n"
            "🔹 <b>Hybrid</b>\n"
            "A combination of CPA and RevShare.\n\n"
            "🔹 <b>Postpay</b>\n"
            "Payment after the agreed KPI is completed.\n\n"
            "🔹 <b>Fix</b>\n"
            "A fixed amount for an advertising placement.\n\n"
            "📌 Exact terms are discussed individually with Tommy."
        ),

        "ask_partner": (
            "📈 <b>EXISTING PARTNER SUPPORT</b>\n\n"
            "Describe your question or issue in detail.\n\n"
            "For example:\n"
            "• FTD or conversion issue\n"
            "• Promotional materials\n"
            "• Individual cooperation terms\n"
            "• Affiliate account issue\n"
            "• Technical support\n\n"
            "📩 Your message will be sent to Tommy."
        ),

        "ask_payment": (
            "💳 <b>PAYMENT REQUEST</b>\n\n"
            "Describe the issue in detail.\n\n"
            "Where possible, include:\n\n"
            "🆔 Affiliate ID\n"
            "💵 Payment amount\n"
            "📅 Payment date\n"
            "💳 Payment method\n"
            "📝 Issue description\n\n"
            "📩 Your message will be sent to Tommy."
        ),

        "ask_other": (
            "✉️ <b>OTHER QUESTION</b>\n\n"
            "Write your question or request in detail.\n\n"
            "📩 Your message will be sent to Tommy and the reply "
            "will appear in this chat."
        ),

        "sent": (
            "✅ <b>Your message was sent to Tommy.</b>\n\n"
            "When Tommy replies, his response will automatically "
            "appear in this chat."
        ),

        "reply": "📩 <b>Reply from Tommy:</b>\n\n",

        "reg_source": (
            "📝 <b>NEW PARTNER REGISTRATION</b>\n\n"
            "First, register on the official website:\n"
            f"🔗 {REGISTRATION_URL}\n\n"
            "Now send your traffic source.\n\n"
            "For example:\n"
            "• Telegram channel\n"
            "• Instagram page\n"
            "• YouTube channel\n"
            "• TikTok page\n"
            "• Website or another traffic source\n\n"
            "If you do not have a traffic source yet, write “no”.\n\n"
            "❌ Cancel: /cancel"
        ),

        "reg_model": "💰 <b>Choose a cooperation model:</b>",

        "reg_email": (
            "📧 <b>Send your email address:</b>\n\n"
            "Example: name@gmail.com"
        ),

        "reg_username": (
            "🔗 <b>Send your Telegram username:</b>\n\n"
            "Example: @username"
        ),

        "reg_geo": (
            "🌍 <b>Which countries or GEOs do you target?</b>\n\n"
            "Example: Uzbekistan, CIS, Turkey or another GEO."
        ),

        "reg_promo": (
            "📢 <b>Which advertising sources do you use?</b>\n\n"
            "For example:\n"
            "• Telegram posts\n"
            "• Instagram Stories/Reels\n"
            "• YouTube\n"
            "• TikTok\n"
            "• Facebook or Google Ads\n"
            "• SEO\n\n"
            "If not decided yet, write “no”."
        ),

        "invalid_email": (
            "⚠️ <b>Invalid email address.</b>\n\n"
            "Send it again in the correct format.\n"
            "Example: name@gmail.com"
        ),

        "invalid_username": (
            "⚠️ <b>Invalid Telegram username.</b>\n\n"
            "The username must start with @.\n"
            "Example: @username"
        ),

        "registered": (
            "✅ <b>Your information was sent to Tommy!</b>\n\n"
            "Tommy will review it and contact you through Telegram."
        ),

        "cancelled": "❌ Registration cancelled.",

        "send_text_or_media": (
            "⚠️ Send your question as text, image, video, "
            "voice message or file."
        ),
    },
}


CATEGORY_NAMES = {
    "partner": "📈 Mavjud hamkor yordami",
    "payment": "💳 To'lov bo'yicha savol",
    "other": "✉️ Boshqa savol",
    "free": "💬 Erkin murojaat",
}


MODEL_NAMES = [
    "CPA",
    "RevShare (RS)",
    "Hybrid",
    "Postpay",
    "Fix",
]


# ============================================================
# 4. KLAVIATURALAR
# ============================================================

def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "🇺🇿 O'zbek",
                callback_data="lang:uz",
            ),
            InlineKeyboardButton(
                "🇷🇺 Русский",
                callback_data="lang:ru",
            ),
            InlineKeyboardButton(
                "🇬🇧 English",
                callback_data="lang:en",
            ),
        ]]
    )


def main_keyboard(lang: str) -> InlineKeyboardMarkup:
    t = TEXTS[lang]

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t["models"],
                    callback_data="menu:models",
                )
            ],
            [
                InlineKeyboardButton(
                    t["register"],
                    callback_data="register:start",
                )
            ],
            [
                InlineKeyboardButton(
                    t["partner"],
                    callback_data="menu:partner",
                )
            ],
            [
                InlineKeyboardButton(
                    t["payment"],
                    callback_data="menu:payment",
                )
            ],
            [
                InlineKeyboardButton(
                    t["other"],
                    callback_data="menu:other",
                )
            ],
        ]
    )


def back_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                TEXTS[lang]["back"],
                callback_data="menu:back",
            )
        ]]
    )


def model_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                name,
                callback_data=f"register:model:{name}",
            )
        ]
        for name in MODEL_NAMES
    ]

    rows.append(
        [
            InlineKeyboardButton(
                TEXTS[lang]["back"],
                callback_data="register:cancel",
            )
        ]
    )

    return InlineKeyboardMarkup(rows)


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📩 Kutilayotgan savollar",
                    callback_data="admin:pending",
                ),
            ],
            [
                InlineKeyboardButton(
                    "👥 Yangi hamkorlar",
                    callback_data="admin:partners",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📊 Statistika",
                    callback_data="admin:stats",
                ),
                InlineKeyboardButton(
                    "🔄 Yangilash",
                    callback_data="admin:home",
                ),
            ],
        ]
    )


# ============================================================
# 5. YORDAMCHI FUNKSIYALAR
# ============================================================

def safe(value: object) -> str:
    return html.escape(str(value or "—"))


def full_name(user) -> str:
    parts = [
        user.first_name or "",
        user.last_name or "",
    ]

    name = " ".join(
        part for part in parts
        if part
    ).strip()

    return name or "Noma'lum"


def username_text(user) -> str:
    if user.username:
        return f"@{user.username}"

    return "Username yo'q"


def get_message_content(
    message,
) -> tuple[str, str, str | None]:

    if message.text:
        return (
            "text",
            message.text,
            None,
        )

    if message.photo:
        return (
            "photo",
            message.caption or "📷 Rasm yuborildi",
            message.photo[-1].file_id,
        )

    if message.video:
        return (
            "video",
            message.caption or "🎥 Video yuborildi",
            message.video.file_id,
        )

    if message.document:
        filename = (
            message.document.file_name
            or "Hujjat"
        )

        return (
            "document",
            message.caption or f"📎 {filename}",
            message.document.file_id,
        )

    if message.voice:
        return (
            "voice",
            message.caption or "🎙 Ovozli xabar yuborildi",
            message.voice.file_id,
        )

    if message.audio:
        return (
            "audio",
            message.caption or "🎵 Audio yuborildi",
            message.audio.file_id,
        )

    if message.animation:
        return (
            "animation",
            message.caption or "🎞 GIF yuborildi",
            message.animation.file_id,
        )

    return (
        "unknown",
        "Qo'llab-quvvatlanmaydigan xabar turi",
        None,
    )


async def send_admin_media(
    context: ContextTypes.DEFAULT_TYPE,
    message_type: str,
    file_id: str,
    caption: str,
):
    arguments = {
        "chat_id": ADMIN_CHAT_ID,
        "caption": caption,
        "parse_mode": ParseMode.HTML,
    }

    if message_type == "photo":
        return await context.bot.send_photo(
            photo=file_id,
            **arguments,
        )

    if message_type == "video":
        return await context.bot.send_video(
            video=file_id,
            **arguments,
        )

    if message_type == "document":
        return await context.bot.send_document(
            document=file_id,
            **arguments,
        )

    if message_type == "voice":
        return await context.bot.send_voice(
            voice=file_id,
            **arguments,
        )

    if message_type == "audio":
        return await context.bot.send_audio(
            audio=file_id,
            **arguments,
        )

    if message_type == "animation":
        return await context.bot.send_animation(
            animation=file_id,
            **arguments,
        )

    return None


async def send_admin_reply_to_user(
    context: ContextTypes.DEFAULT_TYPE,
    target_user_id: int,
    admin_message,
) -> None:

    lang = get_user_language(target_user_id)
    prefix = TEXTS[lang]["reply"]

    if admin_message.text:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=prefix + safe(admin_message.text),
            parse_mode=ParseMode.HTML,
        )
        return

    caption = (
        prefix
        + safe(admin_message.caption or "")
    )

    if admin_message.photo:
        await context.bot.send_photo(
            chat_id=target_user_id,
            photo=admin_message.photo[-1].file_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        return

    if admin_message.video:
        await context.bot.send_video(
            chat_id=target_user_id,
            video=admin_message.video.file_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        return

    if admin_message.document:
        await context.bot.send_document(
            chat_id=target_user_id,
            document=admin_message.document.file_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        return

    if admin_message.voice:
        await context.bot.send_voice(
            chat_id=target_user_id,
            voice=admin_message.voice.file_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        return

    if admin_message.audio:
        await context.bot.send_audio(
            chat_id=target_user_id,
            audio=admin_message.audio.file_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        return

    if admin_message.animation:
        await context.bot.send_animation(
            chat_id=target_user_id,
            animation=admin_message.animation.file_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        return

    await context.bot.send_message(
        chat_id=target_user_id,
        text=prefix + "Xabar yuborildi.",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# 6. FOYDALANUVCHI MENYUSI
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    save_user(update)
    context.user_data.pop("mode", None)
    context.user_data.pop("registration", None)

    await update.effective_message.reply_text(
        (
            "🌐 <b>Tilni tanlang</b>\n"
            "🌐 <b>Выберите язык</b>\n"
            "🌐 <b>Choose your language</b>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=language_keyboard(),
    )


async def language_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    lang = query.data.split(":", 1)[1]

    save_user(
        update,
        language=lang,
    )

    context.user_data.pop("mode", None)
    context.user_data.pop("registration", None)

    await query.message.reply_text(
        TEXTS[lang]["welcome"],
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(lang),
    )


async def menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    lang = get_user_language(user_id)
    t = TEXTS[lang]

    action = query.data.split(":", 1)[1]

    if action == "back":
        context.user_data.pop("mode", None)

        await query.message.reply_text(
            t["welcome"],
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(lang),
        )
        return

    if action == "models":
        context.user_data.pop("mode", None)

        await query.message.reply_text(
            t["models_text"],
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(lang),
        )
        return

    context.user_data["mode"] = action

    prompt_key = {
        "partner": "ask_partner",
        "payment": "ask_payment",
        "other": "ask_other",
    }.get(
        action,
        "ask_other",
    )

    await query.message.reply_text(
        t[prompt_key],
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard(lang),
    )


# ============================================================
# 7. FOYDALANUVCHI MUROJAATINI ADMINGA YUBORISH
# ============================================================

async def user_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not update.effective_user:
        return

    if not update.effective_message:
        return

    if update.effective_user.id == ADMIN_CHAT_ID:
        return

    save_user(update)

    user = update.effective_user
    message = update.effective_message

    lang = get_user_language(user.id)

    category = context.user_data.get(
        "mode",
        "free",
    )

    (
        message_type,
        message_text,
        file_id,
    ) = get_message_content(message)

    if message_type == "unknown":
        await message.reply_text(
            TEXTS[lang]["send_text_or_media"],
            parse_mode=ParseMode.HTML,
        )
        return

    question_id = add_question(
        user_id=user.id,
        category=category,
        message_type=message_type,
        message_text=message_text,
        file_id=file_id,
    )

    admin_text = (
        "📩 <b>YANGI MUROJAAT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Ism:</b> {safe(full_name(user))}\n"
        f"🔗 <b>Username:</b> {safe(username_text(user))}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"🌐 <b>Til:</b> {safe(lang.upper())}\n"
        f"📂 <b>Bo'lim:</b> "
        f"{safe(CATEGORY_NAMES.get(category, CATEGORY_NAMES['free']))}\n"
        f"🔢 <b>Murojaat №:</b> <code>{question_id}</code>\n\n"
        "💬 <b>Savol:</b>\n"
        f"{safe(message_text)}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "↩️ <b>Javob berish uchun shu xabarga Reply qiling.</b>"
    )

    try:
        if message_type == "text":
            admin_message = await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_text,
                parse_mode=ParseMode.HTML,
            )
        else:
            admin_message = await send_admin_media(
                context=context,
                message_type=message_type,
                file_id=file_id,
                caption=admin_text,
            )

        if admin_message:
            set_question_admin_message(
                question_id=question_id,
                admin_message_id=admin_message.message_id,
            )

            add_admin_link(
                admin_message_id=admin_message.message_id,
                target_user_id=user.id,
                item_type="question",
                item_id=question_id,
            )

        await message.reply_text(
            TEXTS[lang]["sent"],
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(lang),
        )

    except TelegramError as error:
        logger.exception(
            "Admin'ga murojaat yuborilmadi: %s",
            error,
        )

        await message.reply_text(
            (
                "⚠️ Xabarni yuborishda texnik xato yuz berdi.\n"
                "Iltimos, birozdan keyin qayta urinib ko'ring."
            )
        )

    context.user_data.pop("mode", None)


# ============================================================
# 8. YANGI HAMKOR RO'YXATDAN O'TISHI
# ============================================================

async def registration_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    query = update.callback_query
    await query.answer()

    lang = get_user_language(
        query.from_user.id
    )

    context.user_data["registration"] = {}
    context.user_data.pop("mode", None)

    await query.message.reply_text(
        TEXTS[lang]["reg_source"],
        parse_mode=ParseMode.HTML,
    )

    return REG_SOURCE


async def registration_source_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    lang = get_user_language(
        update.effective_user.id
    )

    registration = context.user_data.setdefault(
        "registration",
        {},
    )

    registration["source"] = (
        update.effective_message.text.strip()
    )

    await update.effective_message.reply_text(
        TEXTS[lang]["reg_model"],
        parse_mode=ParseMode.HTML,
        reply_markup=model_keyboard(lang),
    )

    return REG_MODEL


async def registration_model_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    query = update.callback_query
    await query.answer()

    lang = get_user_language(
        query.from_user.id
    )

    model = query.data.split(
        ":",
        2,
    )[2]

    registration = context.user_data.setdefault(
        "registration",
        {},
    )

    registration["model"] = model

    await query.message.reply_text(
        TEXTS[lang]["reg_email"],
        parse_mode=ParseMode.HTML,
    )

    return REG_EMAIL


async def registration_invalid_model(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    lang = get_user_language(
        update.effective_user.id
    )

    await update.effective_message.reply_text(
        TEXTS[lang]["reg_model"],
        parse_mode=ParseMode.HTML,
        reply_markup=model_keyboard(lang),
    )

    return REG_MODEL


async def registration_email_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    lang = get_user_language(
        update.effective_user.id
    )

    email = update.effective_message.text.strip()

    if not EMAIL_RE.match(email):
        await update.effective_message.reply_text(
            TEXTS[lang]["invalid_email"],
            parse_mode=ParseMode.HTML,
        )

        return REG_EMAIL

    context.user_data["registration"]["email"] = email

    await update.effective_message.reply_text(
        TEXTS[lang]["reg_username"],
        parse_mode=ParseMode.HTML,
    )

    return REG_USERNAME


async def registration_username_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    lang = get_user_language(
        update.effective_user.id
    )

    username = (
        update.effective_message.text.strip()
    )

    if not USERNAME_RE.match(username):
        await update.effective_message.reply_text(
            TEXTS[lang]["invalid_username"],
            parse_mode=ParseMode.HTML,
        )

        return REG_USERNAME

    context.user_data["registration"][
        "telegram_username"
    ] = username

    await update.effective_message.reply_text(
        TEXTS[lang]["reg_geo"],
        parse_mode=ParseMode.HTML,
    )

    return REG_GEO


async def registration_geo_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    lang = get_user_language(
        update.effective_user.id
    )

    context.user_data["registration"]["geo"] = (
        update.effective_message.text.strip()
    )

    await update.effective_message.reply_text(
        TEXTS[lang]["reg_promo"],
        parse_mode=ParseMode.HTML,
    )

    return REG_PROMO


async def registration_promo_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:

    user = update.effective_user
    lang = get_user_language(user.id)

    registration = context.user_data.get(
        "registration",
        {},
    )

    registration["promo"] = (
        update.effective_message.text.strip()
    )

    partner_id = add_partner(
        user_id=user.id,
        source=registration.get("source", "—"),
        model=registration.get("model", "—"),
        email=registration.get("email", "—"),
        telegram_username=registration.get(
            "telegram_username",
            "—",
        ),
        geo=registration.get("geo", "—"),
        promo=registration.get("promo", "—"),
    )

    admin_text = (
        "👥 <b>YANGI HAMKOR</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Ism:</b> {safe(full_name(user))}\n"
        f"🔗 <b>Telegram:</b> "
        f"{safe(registration.get('telegram_username'))}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"📧 <b>Email:</b> {safe(registration.get('email'))}\n"
        f"🌍 <b>GEO:</b> {safe(registration.get('geo'))}\n"
        f"💰 <b>Model:</b> {safe(registration.get('model'))}\n"
        f"📢 <b>Trafik manbasi:</b> "
        f"{safe(registration.get('source'))}\n"
        f"🎯 <b>Reklama usuli:</b> "
        f"{safe(registration.get('promo'))}\n"
        f"🔢 <b>Hamkor №:</b> <code>{partner_id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "↩️ <b>Hamkorga yozish uchun shu xabarga Reply qiling.</b>"
    )

    try:
        admin_message = await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_text,
            parse_mode=ParseMode.HTML,
        )

        set_partner_admin_message(
            partner_id=partner_id,
            admin_message_id=admin_message.message_id,
        )

        add_admin_link(
            admin_message_id=admin_message.message_id,
            target_user_id=user.id,
            item_type="partner",
            item_id=partner_id,
        )

        await update.effective_message.reply_text(
            TEXTS[lang]["registered"],
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(lang),
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

    user_id = update.effective_user.id
    lang = get_user_language(user_id)

    context.user_data.pop(
        "registration",
        None,
    )

    if update.callback_query:
        await update.callback_query.answer()

        await update.callback_query.message.reply_text(
            TEXTS[lang]["cancelled"],
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(lang),
        )
    else:
        await update.effective_message.reply_text(
            TEXTS[lang]["cancelled"],
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(lang),
        )

    return ConversationHandler.END


# ============================================================
# 9. ADMIN REPLY ORQALI JAVOB BERISHI
# ============================================================

async def admin_reply_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    admin_message = update.effective_message
    admin_user = update.effective_user

    if not admin_user:
        return

    if admin_user.id != ADMIN_CHAT_ID:
        return

    if not admin_message:
        return

    if not admin_message.reply_to_message:
        return

    original_admin_message_id = (
        admin_message.reply_to_message.message_id
    )

    link = get_admin_link(
        original_admin_message_id
    )

    if not link:
        await admin_message.reply_text(
            (
                "⚠️ <b>Javob yuborilmadi.</b>\n\n"
                "Foydalanuvchiga javob berish uchun bot yuborgan "
                "murojaat yoki yangi hamkor xabarining ustiga "
                "<b>Reply</b> qilib yozing."
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    target_user_id = int(
        link["target_user_id"]
    )

    try:
        await send_admin_reply_to_user(
            context=context,
            target_user_id=target_user_id,
            admin_message=admin_message,
        )

        if (
            link["item_type"] == "question"
            and link["item_id"]
        ):
            mark_question_answered(
                int(link["item_id"])
            )

        elif (
            link["item_type"] == "partner"
            and link["item_id"]
        ):
            with db_connect() as connection:
                connection.execute(
                    """
                    UPDATE partners
                    SET status = 'contacted'
                    WHERE id = ?
                    """,
                    (
                        int(link["item_id"]),
                    ),
                )

        await admin_message.reply_text(
            (
                "✅ <b>JAVOB YUBORILDI</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 <b>Foydalanuvchi ID:</b> "
                f"<code>{target_user_id}</code>\n"
                "📩 <b>Holat:</b> Muvaffaqiyatli yuborildi"
            ),
            parse_mode=ParseMode.HTML,
        )

    except Forbidden:
        await admin_message.reply_text(
            (
                "❌ <b>Javob yuborilmadi.</b>\n\n"
                "Foydalanuvchi botni bloklagan yoki bot bilan "
                "suhbatni o'chirgan."
            ),
            parse_mode=ParseMode.HTML,
        )

    except TelegramError as error:
        logger.exception(
            "Admin javobi yuborilmadi: %s",
            error,
        )

        await admin_message.reply_text(
            (
                "❌ <b>Javob yuborilmadi.</b>\n\n"
                f"<code>{safe(error)}</code>"
            ),
            parse_mode=ParseMode.HTML,
        )


# ============================================================
# 10. ADMIN PANEL
# ============================================================

def admin_panel_text() -> str:
    stats = get_statistics()

    return (
        "🛠 <b>TOMMY ADMIN PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Bot foydalanuvchilari:</b> "
        f"{stats['users']}\n"
        f"👥 <b>Jami yangi hamkorlar:</b> "
        f"{stats['partners']}\n"
        f"🆕 <b>Ko'rilmagan hamkorlar:</b> "
        f"{stats['new_partners']}\n"
        f"⏳ <b>Javob kutilayotgan savollar:</b> "
        f"{stats['pending']}\n"
        f"✅ <b>Javob berilgan savollar:</b> "
        f"{stats['answered']}\n\n"
        "👇 Kerakli bo'limni tanlang:"
    )


async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not update.effective_user:
        return

    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    await update.effective_message.reply_text(
        admin_panel_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


async def admin_panel_callback(
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

    action = query.data.split(":", 1)[1]

    if action in {
        "home",
        "stats",
    }:
        await query.message.reply_text(
            admin_panel_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
        return

    if action == "pending":
        with db_connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    q.*,
                    u.first_name,
                    u.last_name,
                    u.username
                FROM questions q
                LEFT JOIN users u
                    ON u.user_id = q.user_id
                WHERE q.status = 'pending'
                ORDER BY q.id DESC
                LIMIT 10
                """
            ).fetchall()

        if not rows:
            await query.message.reply_text(
                "✅ Javob kutilayotgan murojaatlar yo'q.",
                reply_markup=admin_keyboard(),
            )
            return

        text = (
            "📩 <b>OXIRGI 10 TA KUTILAYOTGAN SAVOL</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
        )

        for row in rows:
            name_parts = [
                row["first_name"],
                row["last_name"],
            ]

            name = " ".join(
                part
                for part in name_parts
                if part
            ) or "Noma'lum"

            username = (
                f"@{row['username']}"
                if row["username"]
                else "username yo'q"
            )

            question_text = (
                row["message_text"]
                or "Media xabar"
            )

            short_text = question_text[:150]

            text += (
                f"🔢 <b>№{row['id']}</b>\n"
                f"👤 {safe(name)}\n"
                f"🔗 {safe(username)}\n"
                f"📂 "
                f"{safe(CATEGORY_NAMES.get(row['category'], row['category']))}\n"
                f"💬 {safe(short_text)}\n"
                f"📅 {safe(row['created_at'])}\n\n"
            )

        text += (
            "━━━━━━━━━━━━━━━━━━\n"
            "↩️ Javob berish uchun original murojaat "
            "xabarining ustiga Reply qiling."
        )

        await query.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
        return

    if action == "partners":
        with db_connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM partners
                ORDER BY id DESC
                LIMIT 10
                """
            ).fetchall()

        if not rows:
            await query.message.reply_text(
                "👥 Hozircha yangi hamkorlar yo'q.",
                reply_markup=admin_keyboard(),
            )
            return

        text = (
            "👥 <b>OXIRGI 10 TA YANGI HAMKOR</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
        )

        for row in rows:
            if row["status"] == "new":
                status = "🆕 Yangi"
            else:
                status = "✅ Bog'lanilgan"

            text += (
                f"🔢 <b>№{row['id']}</b>\n"
                f"🔗 {safe(row['telegram_username'])}\n"
                f"📧 {safe(row['email'])}\n"
                f"🌍 {safe(row['geo'])}\n"
                f"💰 {safe(row['model'])}\n"
                f"📢 {safe(row['source'])}\n"
                f"📌 {status}\n"
                f"📅 {safe(row['created_at'])}\n\n"
            )

        await query.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )


# ============================================================
# 11. XATOLARNI USHLASH
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    logger.error(
        "Kutilmagan bot xatosi: %s",
        context.error,
        exc_info=context.error,
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "⚠️ <b>BOT XATOSI</b>\n\n"
                f"<code>{safe(context.error)}</code>"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.exception(
            "Xato haqida admin'ga xabar yuborilmadi."
        )


# ============================================================
# 12. BOTNI YIG'ISH VA ISHGA TUSHIRISH
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
                    pattern=r"^register:model:",
                ),

                MessageHandler(
                    filters.ALL
                    & ~filters.COMMAND,
                    registration_invalid_model,
                ),
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
            ),

            CallbackQueryHandler(
                registration_cancel,
                pattern=r"^register:cancel$",
            ),
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
        registration_handler
    )

    application.add_handler(
        CallbackQueryHandler(
            language_selected,
            pattern=r"^lang:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            menu_handler,
            pattern=r"^menu:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_panel_callback,
            pattern=r"^admin:",
        )
    )

    # Adminning Reply xabari oddiy foydalanuvchi xabaridan
    # oldin ushlanishi kerak.
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
                | filters.ANIMATION
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
                | filters.ANIMATION
            ),
            user_message_handler,
        )
    )

    application.add_error_handler(
        error_handler
    )

    return application


def main() -> None:
    init_db()

    application = build_application()

    logger.info(
        "Tommy Partners Bot ishga tushdi."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
