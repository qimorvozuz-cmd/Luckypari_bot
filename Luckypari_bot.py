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
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from anthropic import Anthropic

# ============ SOZLAMALAR ============
BOT_TOKEN = "8930140941:AAEFk9YYH9gPANFihOEFTn4_HoIKNhjmRu8"
ADMIN_CHAT_ID = 8211732921          # Tommy yoki admin chat ID
REGISTRATION_URL = "http://Luckyparipartners.com"

ANTHROPIC_API_KEY = "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"   # console.anthropic.com dan olinadi
ai_client = Anthropic(api_key=ANTHROPIC_API_KEY)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

AI_SYSTEM_PROMPT = {
    "uz": (
        "Sen LuckyPari affiliate dasturining AI-yordamchisisan (Tommy jamoasi nomidan). "
        "Hamkorlarga trafik, FTD oshirish, konversiya, reklama kanallari (Telegram, Instagram, "
        "Facebook, Google Ads, TikTok, Push/Native Ads va h.k.), hamkorlik modellari (CPA, RevShare — "
        "50% gacha, Hybrid, Postpay, Fix) va dastur bo'yicha istalgan savolga aniq, amaliy javob ber. "
        "Agar hamkor FTD past yoki reklama natija bermayapti desa, mustaqil ravishda aniq amaliy "
        "takliflar ber: landing sahifa sifatini tekshirish, auditoriya segmentatsiyasini aniqlashtirish, "
        "kreativlarni (banner/matn) A/B testlash, referral bonus yoki konkurs tashkil qilish, "
        "trafik manbasini diversifikatsiya qilish kabi. "
        "Javobing qisqa (3-6 jumla), do'stona va professional bo'lsin. "
        "Har bir javob oxirida foydalanuvchini yana savol berishga tabiiy tarzda taklif qil, "
        "lekin har safar boshqacha so'zlar bilan — bir xil jumlani takrorlama. "
        "Hech qachon aniq daromad, to'lov miqdori yoki kafolatlangan natija va'da qilma — "
        "bunday savol bo'lsa, buni Tommy bilan individual kelishish kerakligini ayt. "
        "Agar savol umuman aloqador bo'lmasa yoki juda maxsus (masalan aniq shartnoma, hisob muammosi) bo'lsa, "
        "buni Tommy'ga yetkazishingni ayt."
    ),
    "ru": (
        "Ты AI-ассистент партнёрской программы LuckyPari (от команды Tommy). "
        "Отвечай партнёрам конкретно и практично на вопросы о трафике, росте FTD, конверсии, рекламных каналах "
        "(Telegram, Instagram, Facebook, Google Ads, TikTok, Push/Native Ads и т.д.), моделях сотрудничества "
        "(CPA, RevShare — до 50%, Hybrid, Postpay, Fix) и любые вопросы о программе. "
        "Если партнёр говорит, что FTD низкий или реклама не даёт результата, самостоятельно предложи "
        "конкретные практические шаги: проверить качество лендинга, уточнить сегментацию аудитории, "
        "протестировать креативы (баннеры/тексты) A/B-методом, запустить реферальный бонус или конкурс, "
        "диверсифицировать источники трафика. "
        "Ответ короткий (3-6 предложений), дружелюбный и профессиональный. "
        "В конце каждого ответа естественно предложи задать ещё вопрос, но каждый раз другими словами — "
        "не повторяй одну и ту же фразу. "
        "Никогда не обещай конкретный доход, суммы выплат или гарантированный результат — "
        "если об этом спрашивают, скажи, что это согласовывается индивидуально с Tommy. "
        "Если вопрос не по теме или слишком специфичен (конкретный договор, проблема с аккаунтом), "
        "скажи, что передашь это Tommy."
    ),
    "en": (
        "You are the AI assistant of the LuckyPari affiliate program (on behalf of Tommy's team). "
        "Give partners concrete, practical answers about traffic, increasing FTDs, conversion, ad channels "
        "(Telegram, Instagram, Facebook, Google Ads, TikTok, Push/Native Ads, etc), cooperation models "
        "(CPA, RevShare — up to 50%, Hybrid, Postpay, Fix), and any question about the program. "
        "If a partner says FTDs are low or ads aren't performing, independently suggest concrete practical "
        "steps: check landing page quality, refine audience targeting, A/B test creatives (banners/copy), "
        "launch a referral bonus or contest, diversify traffic sources. "
        "Keep answers short (3-6 sentences), friendly and professional. "
        "End each answer with a natural invitation to ask more, but phrase it differently each time — "
        "never repeat the same closing line. "
        "Never promise specific income, payment amounts, or guaranteed results — "
        "if asked, say those terms are agreed individually with Tommy. "
        "If the question is unrelated or too specific (a particular contract, account issue), "
        "say you'll pass it on to Tommy."
    ),
}


def get_ai_advice(question: str, lang: str) -> str:
    """Anthropic API orqali savolga mavzuga mos, real maslahat oladi."""
    try:
        response = ai_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=AI_SYSTEM_PROMPT.get(lang, AI_SYSTEM_PROMPT["uz"]),
            messages=[{"role": "user", "content": question}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"AI xatosi: {e}")
        return None


# Dolzarb/muhim mavzularni aniqlash uchun kalit so'zlar (uz/ru/en)
URGENT_KEYWORDS = [
    # shikoyat, firibgar, muammo
    "shikoyat", "firibgar", "aldash", "fraud", "scam", "жалоба", "мошенник", "обман",
    "complaint", "fraudulent",
    # to'lov muammosi
    "to'lov kelmadi", "pul kelmadi", "to'lov bo'lmadi", "выплата не пришла", "деньги не пришли",
    "payment not received", "didn't receive payment", "haven't received",
    # texnik muammo / hisob bloklandi
    "hisobim bloklandi", "blocklandi", "bloklandi", "ishlamayapti", "kirolmayapman",
    "аккаунт заблокирован", "не могу войти", "не работает", "заблокирован",
    "account blocked", "can't login", "not working", "technical issue", "texnik muammo",
    # yuqori CPA / maxsus shartnoma / VIP / contest byudjeti
    "yuqori cpa", "maxsus shart", "vip", "individual shartnoma", "katta trafik",
    "повышенный cpa", "особые условия", "индивидуальные условия", "крупный трафик",
    "higher cpa", "special terms", "custom deal", "large traffic", "exclusive deal",
    "byudjet so'rov", "contest byudjet", "конкурсный бюджет", "contest budget",
    # umumiy yordam so'rovi / tezkor
    "tezroq yordam", "urgent", "срочно", "asap",
]


def is_urgent(text: str) -> bool:
    """Xabar matnida dolzarb/muhim mavzu belgilari bor-yo'qligini tekshiradi."""
    lowered = text.lower()
    return any(kw in lowered for kw in URGENT_KEYWORDS)


EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def is_valid_email(text: str) -> bool:
    return bool(EMAIL_REGEX.match(text.strip()))


def is_valid_username(text: str) -> bool:
    text = text.strip()
    return text.startswith("@") and len(text) > 1 and " " not in text


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
        "reg_step1": (
            f"Ro'yxatdan o'tishni boshlaymiz! 🎯\n\nAvval rasmiy saytda ro'yxatdan o'ting:\n{REGISTRATION_URL}\n\n"
            "Endi bir necha savolga javob bering.\n\n"
            "Kazino/sport-betting mavzusida Telegram kanal yuritasizmi? Bo'lsa, kanal havolasini yuboring.\n"
            "Agar boshqa bukmeker/kazino bilan hamkorlik qilib kelgan bo'lsangiz, statistikangizni "
            "(screenshot yoki qisqacha tavsif) yuboring.\n"
            "Ikkalasi ham sizga tegishli bo'lmasa, shunchaki \"yo'q\" deb yozing."
        ),
        "reg_thanks": "Rahmat! Ma'lumotlaringiz Tommy'ga yuborildi, u tez orada siz bilan bog'lanadi.",
        "reg_model_choose": "Rahmat! Endi qaysi hamkorlik modelida ishlashni xohlaysiz?",
        "reg_recommend_rs": "\n\n💡 Tavsiya: ko'pchilik hamkorlarimiz uchun RevShare (RS) eng yuqori uzoq muddatli daromad beradi — birinchi tajriba sifatida shuni sinab ko'rishni tavsiya qilamiz.",
        "reg_please_use_buttons": "Iltimos, yuqoridagi tugmalardan birini tanlang.",
        "offer_rs": "🎯 RS bo'yicha sizga 45% gacha komissiya taklif qilamiz. Birinchi natijalaringizni ko'rgach, Fix va boshqa modellarni ham muhokama qilishimiz mumkin.",
        "offer_other": "📊 Statistikangizni ko'rib chiqamiz. Ro'yxatdan to'liq o'tganingizdan so'ng Tommy shaxsan siz bilan bog'lanib, aniq shartlar va summani muhokama qiladi.",
        "ask_email": "Davom etish uchun emailingizni yuboring:",
        "ask_geo": "Qaysi davlatlar (GEO) bo'yicha trafik yuritasiz?",
        "ask_promo": "Qanday promo-materiallardan foydalanasiz (banner, promokod va h.k.)? Hali yo'q bo'lsa \"yo'q\" deb yozing.",
        "partner_prompt": "Qaysi yo'nalishda yordam kerak? (masalan: FTD oshirish, trafik manbai, konversiya) — yozing, men maslahat beraman.",
        "payment_prompt": "To'lov bilan bog'liq savolingizni yozing. Zarur bo'lsa, Tommy'ga yuboraman.",
        "other_prompt": "Savolingizni yozing, javob beraman yoki Tommy'ga yetkazaman.",
        "msg_sent": "✅ Xabaringiz Tommy'ga yuborildi. Tez orada javob keladi.",
        "reply_prefix": "📩 Tommy'dan javob:\n\n",
        "no_guarantee": "\n\n⚠️ Eslatma: aniq daromad yoki to'lov miqdorini kafolatlay olmayman — bu shartlar individual tarzda Tommy bilan kelishiladi.",
        "ask_username": "Telegram username?",
        "invalid_email": "⚠️ Email formati noto'g'ri. Iltimos, to'g'ri email manzilingizni yozing (masalan: ism@gmail.com).",
        "invalid_username": "⚠️ Telegram username @ belgisi bilan boshlanishi kerak (masalan: @username). Qayta yozing.",
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
        "reg_step1": (
            f"Начинаем регистрацию! 🎯\n\nСначала зарегистрируйтесь на официальном сайте:\n{REGISTRATION_URL}\n\n"
            "Теперь ответьте на несколько вопросов.\n\n"
            "Ведёте ли вы Telegram-канал на тему казино/спортивных ставок? Если да, пришлите ссылку на канал.\n"
            "Если вы сотрудничали с другими букмекерами, пришлите вашу статистику (скриншот или краткое описание).\n"
            "Если ни то, ни другое не подходит, просто напишите \"нет\"."
        ),
        "reg_thanks": "Спасибо! Данные отправлены Tommy, он свяжется с вами в ближайшее время.",
        "reg_model_choose": "Спасибо! Какую модель сотрудничества вы хотите выбрать?",
        "reg_recommend_rs": "\n\n💡 Рекомендация: для большинства партнёров RevShare (RS) приносит наибольший долгосрочный доход — рекомендуем попробовать именно эту модель для начала.",
        "reg_please_use_buttons": "Пожалуйста, выберите один из вариантов выше.",
        "offer_rs": "🎯 По RS мы предлагаем вам комиссию до 45%. После первых результатов сможем обсудить также Fix и другие модели.",
        "offer_other": "📊 Мы рассмотрим вашу статистику. После полной регистрации Tommy лично свяжется с вами и обсудит точные условия и сумму.",
        "ask_email": "Для продолжения пришлите ваш email:",
        "ask_geo": "По каким странам (GEO) вы направляете трафик?",
        "ask_promo": "Какие промо-материалы вы используете (баннеры, промокоды и т.д.)? Если пока нет, напишите \"нет\".",
        "partner_prompt": "В каком направлении нужна помощь? (например: рост FTD, источники трафика, конверсия) — напишите, я подскажу.",
        "payment_prompt": "Напишите вопрос по выплатам. При необходимости передам Tommy.",
        "other_prompt": "Напишите вопрос, я отвечу или передам Tommy.",
        "msg_sent": "✅ Сообщение отправлено Tommy. Скоро получите ответ.",
        "reply_prefix": "📩 Ответ от Tommy:\n\n",
        "no_guarantee": "\n\n⚠️ Обратите внимание: я не могу гарантировать доход или размер выплат — эти условия согласовываются индивидуально с Tommy.",
        "ask_username": "Telegram username?",
        "invalid_email": "⚠️ Неверный формат email. Пожалуйста, напишите корректный адрес (например: ivan@gmail.com).",
        "invalid_username": "⚠️ Telegram username должен начинаться с @ (например: @username). Напишите заново.",
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
        "reg_step1": (
            f"Let's start registration! 🎯\n\nFirst, register on the official site:\n{REGISTRATION_URL}\n\n"
            "Now please answer a few questions.\n\n"
            "Do you run a Telegram channel on casino/sports betting? If so, send the channel link.\n"
            "If you've worked with other bookmakers, send your stats (screenshot or brief description).\n"
            "If neither applies to you, just write \"no\"."
        ),
        "reg_thanks": "Thanks! Your details were sent to Tommy, he'll reach out soon.",
        "reg_model_choose": "Thanks! Which cooperation model would you like to work with?",
        "reg_recommend_rs": "\n\n💡 Recommendation: for most of our partners, RevShare (RS) delivers the highest long-term income — we recommend trying it first.",
        "reg_please_use_buttons": "Please choose one of the options above.",
        "offer_rs": "🎯 For RS we offer you a commission of up to 45%. After your first results, we can also discuss Fix and other models.",
        "offer_other": "📊 We'll review your statistics. After you complete registration, Tommy will personally contact you to discuss exact terms and amount.",
        "ask_email": "To continue, send your email:",
        "ask_geo": "Which countries (GEO) do you drive traffic to?",
        "ask_promo": "What promo materials do you use (banners, promo codes, etc)? If none yet, write \"no\".",
        "partner_prompt": "What area do you need help with? (e.g. increasing FTDs, traffic sources, conversion) — write in, I'll advise.",
        "payment_prompt": "Write your payment-related question. I'll forward it to Tommy if needed.",
        "other_prompt": "Write your question, I'll answer or pass it to Tommy.",
        "msg_sent": "✅ Your message was sent to Tommy. You'll get a reply soon.",
        "reply_prefix": "📩 Reply from Tommy:\n\n",
        "no_guarantee": "\n\n⚠️ Note: I can't guarantee income or payment amounts — those terms are agreed individually with Tommy.",
        "ask_username": "Telegram username?",
        "invalid_email": "⚠️ Invalid email format. Please write a correct email address (e.g. name@gmail.com).",
        "invalid_username": "⚠️ Telegram username must start with @ (e.g. @username). Please try again.",
    },
}

MODELS = {
    "uz": [
        ("CPA", "Har bir sifatli o'yinchi uchun belgilangan qat'iy to'lov. O'yinchi sizning referral havolangiz orqali ro'yxatdan o'tib, birinchi depozitni (FTD) amalga oshirsa, siz shu zahoti belgilangan summani olasiz. Aniq CPA miqdori trafik sifati va hajmiga qarab Tommy bilan individual belgilanadi."),
        ("RevShare (RS)", "Siz orqali (referral havolangiz orqali) kelgan o'yinchilarning o'ynash jarayonida hosil bo'lgan kompaniya daromadidan foiz olasiz — bu foiz hajmi va traffik sifatiga qarab 50% gacha yetishi mumkin. O'yinchi sizning hamkoringiz sifatida qolar ekan, u faol o'ynagan har oy sizga daromad keltiraveradi — bu uzoq muddatda CPA'dan sezilarli ko'proq daromad berishi mumkin."),
        ("Hybrid", "CPA + RevShare birikmasi: o'yinchi FTD qilganda darhol belgilangan summani olasiz (CPA qismi), shu bilan birga o'sha o'yinchining kelajakdagi faolligidan ham doimiy foiz olishda davom etasiz (RevShare qismi). Bu ikkala modelning afzalliklarini birlashtiradi — tezkor daromad + uzoq muddatli barqaror foyda."),
        ("Postpay", "Kelishilgan KPI'lar (masalan, aniq sonli sifatli FTD) bajarilgach to'lanadi. Barqaror va bashorat qilinadigan trafikka ega hamkorlar uchun mos — Tommy bilan aniq shartlar oldindan kelishiladi."),
        ("Fix", "Kelishilgan KPI va shartlar asosida belgilangan reklama byudjeti taqdim etiladi — siz oldindan belgilangan summani olasiz va shu byudjet doirasida ishlaysiz. Bu asosan yirik yoki tekshirilgan trafik manbalariga ega, barqaror natija ko'rsatgan hamkorlar uchun mo'ljallangan; aniq summa va shartlar Tommy bilan alohida muhokama qilinadi."),
    ],
    "ru": [
        ("CPA", "Фиксированная выплата за каждого квалифицированного игрока. Как только игрок регистрируется по вашей реферальной ссылке и делает первый депозит (FTD), вы сразу получаете установленную сумму. Точный размер CPA определяется индивидуально с Tommy, в зависимости от качества и объёма трафика."),
        ("RevShare (RS)", "Вы получаете процент от дохода компании, который генерируют игроки, пришедшие по вашей реферальной ссылке — этот процент может достигать 50% в зависимости от качества трафика. Пока игрок остаётся вашим рефералом и активно играет, вы продолжаете получать доход каждый месяц — в долгосрочной перспективе это может приносить значительно больше, чем CPA."),
        ("Hybrid", "Комбинация CPA + RevShare: вы сразу получаете фиксированную сумму при FTD игрока (часть CPA), и одновременно продолжаете получать процент от его дальнейшей активности (часть RevShare). Это сочетает быстрый доход с долгосрочной стабильной прибылью."),
        ("Postpay", "Оплата производится после достижения согласованных KPI (например, определённого числа качественных FTD). Подходит партнёрам со стабильным и предсказуемым трафиком — точные условия согласовываются с Tommy заранее."),
        ("Fix", "Предоставляется фиксированный рекламный бюджет на основе согласованных KPI и условий — вы получаете заранее определённую сумму и работаете в рамках этого бюджета. Предназначено в основном для партнёров с крупными или проверенными источниками трафика, показавших стабильный результат; точная сумма и условия обсуждаются отдельно с Tommy."),
    ],
    "en": [
        ("CPA", "Fixed payment for each qualified player. As soon as a player registers through your referral link and makes their first deposit (FTD), you receive the set amount immediately. The exact CPA rate is agreed individually with Tommy, based on traffic quality and volume."),
        ("RevShare (RS)", "You earn a percentage of the company's revenue generated by players who came through your referral link — this percentage can reach up to 50% depending on traffic quality. As long as the player remains your referral and stays active, you keep earning every month — long-term this can significantly exceed CPA earnings."),
        ("Hybrid", "CPA + RevShare combined: you get a fixed amount immediately when a player makes their FTD (CPA part), while also continuing to earn a percentage from their ongoing activity (RevShare part). This combines quick income with long-term stable profit."),
        ("Postpay", "Paid after agreed KPIs are met (e.g. a specific number of quality FTDs). Suited to partners with stable, predictable traffic — exact terms are agreed with Tommy in advance."),
        ("Fix", "A fixed advertising budget is provided based on agreed KPIs and conditions — you receive a predetermined amount and operate within that budget. Mainly intended for partners with large or verified traffic sources who have shown stable results; the exact amount and terms are discussed separately with Tommy."),
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


def reg_model_kb(lang):
    buttons = [[InlineKeyboardButton(name, callback_data=f"regmodel_{i}")]
               for i, (name, desc) in enumerate(MODELS[lang])]
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
        reg_data[chat_id] = {"step": "channel"}
        await query.edit_message_text(t["reg_step1"])

    elif data.startswith("regmodel_"):
        idx = int(data.split("_")[1])
        model_name = MODELS[lang][idx][0]
        reg_data.setdefault(chat_id, {})["model"] = model_name
        offer = t["offer_rs"] if idx == 1 else t["offer_other"]
        reg_data[chat_id]["step"] = "email"
        await query.edit_message_text(offer + "\n\n" + t["ask_email"])

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
        data = reg_data.setdefault(chat_id, {"step": "channel"})
        step = data.get("step")

        if step == "channel":
            data["channel"] = text.strip()
            data["step"] = "awaiting_model"
            await update.message.reply_text(
                t["reg_model_choose"] + t["reg_recommend_rs"],
                reply_markup=reg_model_kb(lang),
            )
            return

        if step == "awaiting_model":
            await update.message.reply_text(t["reg_please_use_buttons"])
            return

        if step == "email":
            if not is_valid_email(text):
                await update.message.reply_text(t["invalid_email"])
                return
            data["email"] = text.strip()
            data["step"] = "username"
            await update.message.reply_text(t["ask_username"])
            return

        if step == "username":
            if not is_valid_username(text):
                await update.message.reply_text(t["invalid_username"])
                return
            data["user"] = text.strip()
            data["step"] = "geo"
            await update.message.reply_text(t["ask_geo"])
            return

        if step == "geo":
            data["geo"] = text.strip()
            data["step"] = "promo"
            await update.message.reply_text(t["ask_promo"])
            return

        if step == "promo":
            data["promo"] = text.strip()
            await forward_to_admin(
                context, chat_id, lang, "🆕 YANGI HAMKOR / NEW PARTNER",
                f"Email: {data.get('email')}\n"
                f"User: {data.get('user')}\n"
                f"Kanal: {data.get('channel')}\n"
                f"Rs: {data.get('model')}\n"
                f"Geo: {data.get('geo')}\n"
                f"Promo: {data.get('promo')}",
            )
            await update.message.reply_text(t["reg_thanks"], reply_markup=main_menu_kb(lang))
            user_mode[chat_id] = None
            reg_data[chat_id] = {}
        return

    if mode in ("partner", "payment", "other"):
        category = {
            "partner": "HAMKOR SO'ROVI / PARTNER REQUEST",
            "payment": "TO'LOV SAVOLI / PAYMENT QUESTION",
            "other": "BOSHQA SAVOL / OTHER QUESTION",
        }[mode]

        # Foydalanuvchiga "yozyapman" statusi ko'rsatiladi
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        ai_answer = get_ai_advice(text, lang)
        urgent = is_urgent(text)

        if ai_answer:
            await update.message.reply_text(ai_answer, reply_markup=main_menu_kb(lang))
            if urgent:
                await forward_to_admin(
                    context, chat_id, lang, f"🚨 DOLZARB / URGENT — {category}",
                    f"Savol: {text}\n\nAI javobi: {ai_answer}",
                )
        else:
            # AI ishlamasa, ehtiyot chorasi sifatida har doim adminga yuboriladi
            await forward_to_admin(context, chat_id, lang, f"⚠️ AI JAVOB BERMADI — {category}", text)
            await update.message.reply_text(t["msg_sent"], reply_markup=main_menu_kb(lang))

        user_mode[chat_id] = None
        return

    # Aks holda — erkin yozilgan savol, AI orqali mavzuga mos javob beriladi
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    ai_answer = get_ai_advice(text, lang)

    if ai_answer:
        await update.message.reply_text(ai_answer, reply_markup=main_menu_kb(lang))
        if is_urgent(text):
            await forward_to_admin(
                context, chat_id, lang, "🚨 DOLZARB / URGENT — ERKIN SAVOL",
                f"Savol: {text}\n\nAI javobi: {ai_answer}",
            )
    else:
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
