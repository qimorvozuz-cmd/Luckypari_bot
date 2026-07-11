"""
LuckyPari Affiliate Support Bot
- O'zini ochiq AI-yordamchi sifatida tanishtiradi (Tommy nomidan emas, Tommy jamoasining AI yordamchisi sifatida)
- Cooperation modellarini tushuntiradi (CPA, RevShare, Hybrid, Postpay, Fix)
- Yangi hamkorlarni ro'yxatdan o'tkazish jarayonini boshqaradi
- Mavjud hamkorlarga trafik/o'sish bo'yicha maslahat beradi
- Muhim so'rovlarni Tommy'ga (adminga) forward qiladi
- Uz / Ru / En tillarni qo'llab-quvvatlaydi

O'RNATISH:
    pip install python-telegram-bot --upgrade

ISHGA TUSHIRISH:
    1. BOT_TOKEN ga o'z tokeningizni qo'ying (@BotFather)
    2. ADMIN_CHAT_ID ga Tommy (yoki admin)ning chat ID'ini qo'ying
    3. python luckypari_bot.py
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============ SOZLAMALAR ============
BOT_TOKEN = "8930140941:AAEFk9YYH9gPANFihOEFTn4_HoIKNhjmRu8"
ADMIN_CHAT_ID = 8211732921          # Tommy yoki admin chat ID
REGISTRATION_URL = "http://Luckyparipartners.com"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============ MATNLAR ============
TEXTS = {
    "uz": {
        "welcome": (
            "Assalomu alaykum! 👋\n"
            "Men Tommy jamoasining AI-yordamchisiman — LuckyPari affiliate dasturi bo'yicha "
            "savollaringizga javob beraman va murakkab masalalarni Tommy'ga yetkazaman.\n\n"
            "Nima bilan yordam bera olaman?"
        ),
        "btn_models": "💰 Hamkorlik modellari",
        "btn_register": "📝 Ro'yxatdan o'tish",
        "btn_partner": "📈 Mavjud hamkorlar uchun yordam",
        "btn_payment": "💳 To'lov bo'yicha savol",
        "btn_other": "✉️ Boshqa savol",
        "btn_back": "⬅️ Orqaga",
        "models_intro": "Hamkorlik modelini tanlang:",
        "reg_step1": f"Ro'yxatdan o'tish uchun quyidagi havolaga o'ting:\n{REGISTRATION_URL}\n\nRo'yxatdan o'tgach, menga quyidagilarni yuboring:\n1️⃣ Ro'yxatdan o'tgan email\n2️⃣ Telegram username",
        "reg_thanks": "Rahmat! Ma'lumotlaringiz Tommy'ga yuborildi, u tez orada siz bilan bog'lanadi.",
        "partner_prompt": "Qaysi yo'nalishda yordam kerak? (masalan: FTD oshirish, trafik manbai, konversiya) — yozing, men maslahat beraman.",
        "payment_prompt": "To'lov bilan bog'liq savolingizni yozing. Zarur bo'lsa, Tommy'ga yuboraman.",
        "other_prompt": "Savolingizni yozing, javob beraman yoki Tommy'ga yetkazaman.",
        "msg_sent": "✅ Xabaringiz Tommy'ga yuborildi. Tez orada javob keladi.",
        "reply_prefix": "📩 Tommy'dan javob:\n\n",
        "no_guarantee": "\n\n⚠️ Eslatma: aniq daromad yoki to'lov miqdorini kafolatlay olmayman — bu shartlar individual tarzda Tommy bilan kelishiladi.",
        "ask_username": "Telegram username?",
    },
    "ru": {
        "welcome": (
            "Здравствуйте! 👋\n"
            "Я AI-ассистент команды Tommy — отвечаю на вопросы по партнёрской программе LuckyPari "
            "и передаю сложные вопросы Tommy напрямую.\n\n"
            "Чем могу помочь?"
        ),
        "btn_models": "💰 Модели сотрудничества",
        "btn_register": "📝 Регистрация",
        "btn_partner": "📈 Помощь действующим партнёрам",
        "btn_payment": "💳 Вопрос по выплатам",
        "btn_other": "✉️ Другой вопрос",
        "btn_back": "⬅️ Назад",
        "models_intro": "Выберите модель сотрудничества:",
        "reg_step1": f"Для регистрации перейдите по ссылке:\n{REGISTRATION_URL}\n\nПосле регистрации пришлите мне:\n1️⃣ Email регистрации\n2️⃣ Telegram username",
        "reg_thanks": "Спасибо! Данные отправлены Tommy, он свяжется с вами в ближайшее время.",
        "partner_prompt": "В каком направлении нужна помощь? (например: рост FTD, источники трафика, конверсия) — напишите, я подскажу.",
        "payment_prompt": "Напишите вопрос по выплатам. При необходимости передам Tommy.",
        "other_prompt": "Напишите вопрос, я отвечу или передам Tommy.",
        "msg_sent": "✅ Сообщение отправлено Tommy. Скоро получите ответ.",
        "reply_prefix": "📩 Ответ от Tommy:\n\n",
        "no_guarantee": "\n\n⚠️ Обратите внимание: я не могу гарантировать доход или размер выплат — эти условия согласовываются индивидуально с Tommy.",
        "ask_username": "Telegram username?",
    },
    "en": {
        "welcome": (
            "Hello! 👋\n"
            "I'm Tommy's AI assistant — I help with questions about the LuckyPari affiliate program "
            "and forward more complex requests directly to Tommy.\n\n"
            "How can I help you?"
        ),
        "btn_models": "💰 Cooperation models",
        "btn_register": "📝 Register",
        "btn_partner": "📈 Support for existing partners",
        "btn_payment": "💳 Payment question",
        "btn_other": "✉️ Other question",
        "btn_back": "⬅️ Back",
        "models_intro": "Choose a cooperation model:",
        "reg_step1": f"To register, go to:\n{REGISTRATION_URL}\n\nAfter registering, send me:\n1️⃣ Your registered email\n2️⃣ Your Telegram username",
        "reg_thanks": "Thanks! Your details were sent to Tommy, he'll reach out soon.",
        "partner_prompt": "What area do you need help with? (e.g. increasing FTDs, traffic sources, conversion) — write in, I'll advise.",
        "payment_prompt": "Write your payment-related question. I'll forward it to Tommy if needed.",
        "other_prompt": "Write your question, I'll answer or pass it to Tommy.",
        "msg_sent": "✅ Your message was sent to Tommy. You'll get a reply soon.",
        "reply_prefix": "📩 Reply from Tommy:\n\n",
        "no_guarantee": "\n\n⚠️ Note: I can't guarantee income or payment amounts — those terms are agreed individually with Tommy.",
        "ask_username": "Telegram username?",
    },
}

MODELS = {
    "uz": [
        ("CPA", "Har bir sifatli o'yinchi uchun belgilangan qat'iy to'lov."),
        ("RevShare (RS)", "O'zingiz jalb qilgan o'yinchilar daromadidan foiz olasiz. Uzoq muddatda CPA'dan ko'proq daromad berishi mumkin."),
        ("Hybrid", "CPA + RevShare birikmasi: oldindan to'lov + doimiy foiz."),
        ("Postpay", "Kelishilgan KPI'lar bajarilgach to'lanadi. Barqaror trafikka ega hamkorlar uchun mos."),
        ("Fix", "Kelishilgan KPI va shartlar asosida belgilangan reklama byudjeti."),
    ],
    "ru": [
        ("CPA", "Фиксированная выплата за каждого квалифицированного игрока."),
        ("RevShare (RS)", "Процент от дохода привлечённых игроков. В долгосрочной перспективе может приносить больше, чем CPA."),
        ("Hybrid", "Комбинация CPA + RevShare: аванс + постоянный процент."),
        ("Postpay", "Оплата после достижения согласованных KPI. Подходит партнёрам со стабильным трафиком."),
        ("Fix", "Фиксированный рекламный бюджет по согласованным KPI и условиям."),
    ],
    "en": [
        ("CPA", "Fixed payment for each qualified player."),
        ("RevShare (RS)", "A percentage of revenue from players you refer. Can exceed CPA earnings long-term."),
        ("Hybrid", "CPA + RevShare combined: upfront payment plus ongoing share."),
        ("Postpay", "Paid after agreed KPIs are met. Suited to partners with stable traffic."),
        ("Fix", "Fixed advertising budget based on agreed KPIs and conditions."),
    ],
}

user_lang = {}
user_mode = {}  # chat_id -> "register" | "partner" | "payment" | "other" | None
reg_data = {}   # chat_id -> {"email": ..., "telegram": ...}


def main_menu_kb(lang):
    t = TEXTS[lang]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t["btn_models"], callback_data="models")],
        [InlineKeyboardButton(t["btn_register"], callback_data="register")],
        [InlineKeyboardButton(t["btn_partner"], callback_data="partner")],
        [InlineKeyboardButton(t["btn_payment"], callback_data="payment")],
        [InlineKeyboardButton(t["btn_other"], callback_data="other")],
    ])


def lang_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang_uz"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
    ]])


def models_kb(lang):
    buttons = [[InlineKeyboardButton(name, callback_data=f"model_{i}")]
               for i, (name, desc) in enumerate(MODELS[lang])]
    buttons.append([InlineKeyboardButton(TEXTS[lang]["btn_back"], callback_data="back")])
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Tilni tanlang / Выберите язык / Choose language:", reply_markup=lang_kb())


async def forward_to_admin(context, chat_id, lang, category, text):
    user = None
    try:
        user = await context.bot.get_chat(chat_id)
    except Exception:
        pass
    username = f"@{user.username}" if user and user.username else "no username"
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"📌 {category}\nuser_id: {chat_id}\nUsername: {username}\nTil: {lang}\n\n{text}",
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    if data.startswith("lang_"):
        lang = data.split("_")[1]
        user_lang[chat_id] = lang
        user_mode[chat_id] = None
        await query.edit_message_text(TEXTS[lang]["welcome"], reply_markup=main_menu_kb(lang))
        return

    lang = user_lang.get(chat_id, "uz")
    t = TEXTS[lang]

    if data == "models":
        await query.edit_message_text(t["models_intro"], reply_markup=models_kb(lang))

    elif data.startswith("model_"):
        idx = int(data.split("_")[1])
        name, desc = MODELS[lang][idx]
        await query.edit_message_text(f"💰 {name}\n\n{desc}", reply_markup=models_kb(lang))

    elif data == "register":
        user_mode[chat_id] = "register"
        reg_data[chat_id] = {}
        await query.edit_message_text(t["reg_step1"])

    elif data == "partner":
        user_mode[chat_id] = "partner"
        await query.edit_message_text(t["partner_prompt"])

    elif data == "payment":
        user_mode[chat_id] = "payment"
        await query.edit_message_text(t["payment_prompt"] + t["no_guarantee"])

    elif data == "other":
        user_mode[chat_id] = "other"
        await query.edit_message_text(t["other_prompt"])

    elif data == "back":
        user_mode[chat_id] = None
        await query.edit_message_text(t["welcome"], reply_markup=main_menu_kb(lang))


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    lang = user_lang.get(chat_id, "uz")
    t = TEXTS[lang]
    text = update.message.text

    # Admin javob yozganda (forward qilingan xabarga reply orqali)
    if chat_id == ADMIN_CHAT_ID and update.message.reply_to_message:
        original = update.message.reply_to_message.text or ""
        if "user_id:" in original:
            try:
                target_id = int(original.split("user_id:")[1].split()[0])
                target_lang = user_lang.get(target_id, "uz")
                await context.bot.send_message(
                    chat_id=target_id,
                    text=TEXTS[target_lang]["reply_prefix"] + text,
                )
            except (ValueError, IndexError):
                pass
        return

    mode = user_mode.get(chat_id)

    if mode == "register":
        data = reg_data.setdefault(chat_id, {})
        if "email" not in data:
            data["email"] = text
            await update.message.reply_text(t["ask_username"])
        else:
            data["telegram"] = text
            await forward_to_admin(
                context, chat_id, lang, "YANGI RO'YXATDAN O'TISH / NEW REGISTRATION",
                f"Email: {data['email']}\nTelegram: {data['telegram']}",
            )
            await update.message.reply_text(t["reg_thanks"])
            user_mode[chat_id] = None
        return

    if mode in ("partner", "payment", "other"):
        category = {
            "partner": "HAMKOR SO'ROVI / PARTNER REQUEST",
            "payment": "TO'LOV SAVOLI / PAYMENT QUESTION",
            "other": "BOSHQA SAVOL / OTHER QUESTION",
        }[mode]
        await forward_to_admin(context, chat_id, lang, category, text)
        await update.message.reply_text(t["msg_sent"])
        user_mode[chat_id] = None
        return

    # Aks holda menyu
    await update.message.reply_text(t["welcome"], reply_markup=main_menu_kb(lang))


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    logger.info("LuckyPari support bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
