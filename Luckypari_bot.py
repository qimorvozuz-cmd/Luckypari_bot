"""
LuckyPari Affiliate Support Bot — yagona fayl versiyasi.

- Claude (Anthropic) AI botning asosiy "miyasi": barcha savollarga (shu jumladan
  hamkorlik modellari haqida ham) mustaqil, kontekstni hisobga olgan holda javob beradi.
- Ro'yxatdan o'tish ConversationHandler orqali boshqariladi.
- Dolzarb mavzular (to'lov, VIP, higher CPA, bloklangan hisob va h.k.) avtomatik
  Tommy'ga (adminga) forward qilinadi.
- Uz / Ru / En tillarni qo'llab-quvvatlaydi.

MUHIT O'ZGARUVCHILARI (Railway → Variables, yoki lokal .env fayl):
    BOT_TOKEN          — @BotFather'dan olingan token
    ADMIN_CHAT_ID       — Tommy (admin)ning Telegram chat ID'i
    ANTHROPIC_API_KEY   — console.anthropic.com'dan olingan API kalit
    REGISTRATION_URL    — (ixtiyoriy) rasmiy ro'yxatdan o'tish sayti

O'RNATISH:
    pip install python-telegram-bot anthropic python-dotenv

ISHGA TUSHIRISH:
    python bot.py
"""

import logging
import os
import re
from collections import defaultdict

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from anthropic import Anthropic, APIError, APITimeoutError

# ============================================================
# 1) KONFIGURATSIYA
# ============================================================

load_dotenv()  # .env fayli mavjud bo'lsa, undan o'qiydi (lokal muhitda)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Muhit o'zgaruvchisi topilmadi: {name}. "
            f"Uni Railway'ning 'Variables' bo'limiga yoki lokal .env fayliga qo'shing."
        )
    return value


BOT_TOKEN = _require("BOT_TOKEN")
ADMIN_CHAT_ID = int(_require("ADMIN_CHAT_ID"))
ANTHROPIC_API_KEY = _require("ANTHROPIC_API_KEY")
REGISTRATION_URL = os.environ.get("REGISTRATION_URL", "http://Luckyparipartners.com")

AI_MODEL = "claude-sonnet-4-6"
AI_MAX_TOKENS = 280
AI_REQUEST_TIMEOUT = 20.0
AI_HISTORY_LIMIT = 10

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ============================================================
# 2) VALIDATORLAR VA DOLZARB MAVZU ANIQLASH
# ============================================================

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

URGENT_KEYWORDS = [
    "shikoyat", "firibgar", "aldash", "fraud", "scam", "жалоба", "мошенник", "обман",
    "complaint", "fraudulent",
    "to'lov kelmadi", "pul kelmadi", "to'lov bo'lmadi", "выплата не пришла", "деньги не пришли",
    "payment not received", "didn't receive payment", "haven't received",
    "hisobim bloklandi", "blocklandi", "bloklandi", "ishlamayapti", "kirolmayapman",
    "аккаунт заблокирован", "не могу войти", "не работает", "заблокирован",
    "account blocked", "can't login", "not working", "technical issue", "texnik muammo",
    "yuqori cpa", "maxsus shart", "vip", "individual shartnoma", "katta trafik",
    "повышенный cpa", "особые условия", "индивидуальные условия", "крупный трафик",
    "higher cpa", "special terms", "custom deal", "large traffic", "exclusive deal",
    "byudjet so'rov", "contest byudjet", "конкурсный бюджет", "contest budget",
    "tezroq yordam", "urgent", "срочно", "asap",
]


def is_valid_email(text: str) -> bool:
    return bool(EMAIL_REGEX.match(text.strip()))


def is_valid_username(text: str) -> bool:
    text = text.strip()
    return text.startswith("@") and len(text) > 1 and " " not in text


def is_urgent(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in URGENT_KEYWORDS)


# ============================================================
# 3) MATNLAR VA MODEL FAKTLARI (uz/ru/en)
# ============================================================

TEXTS = {
    "uz": {
        "welcome": (
            "Assalomu alaykum! 👋\n"
            "Men Tommy jamoasining AI-yordamchisiman — LuckyPari affiliate dasturi bo'yicha "
            "istalgan savolingizga javob beraman va murakkab masalalarni Tommy'ga yetkazaman.\n\n"
            "Nima bilan yordam bera olaman?"
        ),
        "btn_models": "💰 Hamkorlik modellari",
        "btn_register": "📝 Ro'yxatdan o'tish",
        "btn_partner": "📈 Mavjud hamkorlar uchun yordam",
        "btn_payment": "💳 To'lov bo'yicha savol",
        "btn_other": "✉️ Boshqa savol",
        "btn_back": "⬅️ Orqaga",
        "models_intro": "Hamkorlik modelini tanlang:",
        "model_more_questions": "\n\n💬 Savollaringiz bo'lsa, shu yerga yozing — batafsil tushuntirib beraman.",
        "reg_step1": (
            f"Ro'yxatdan o'tishni boshlaymiz! 🎯\n\nAvval rasmiy saytda ro'yxatdan o'ting:\n{REGISTRATION_URL}\n\n"
            "Endi bir necha savolga javob bering.\n\n"
            "Kazino/sport-betting mavzusida Telegram kanal yuritasizmi? Bo'lsa, kanal havolasini yuboring.\n"
            "Agar boshqa bukmeker/kazino bilan hamkorlik qilib kelgan bo'lsangiz, statistikangizni "
            "(screenshot yoki qisqacha tavsif) yuboring.\n"
            "Ikkalasi ham sizga tegishli bo'lmasa, shunchaki \"yo'q\" deb yozing.\n\n"
            "Istalgan vaqtda /cancel yozib bekor qilishingiz mumkin."
        ),
        "reg_thanks": "Rahmat! Ma'lumotlaringiz Tommy'ga yuborildi, u tez orada siz bilan bog'lanadi.",
        "reg_cancelled": "Ro'yxatdan o'tish bekor qilindi.",
        "reg_model_choose": "Rahmat! Endi qaysi hamkorlik modelida ishlashni xohlaysiz?",
        "reg_recommend_rs": "\n\n💡 Tavsiya: ko'pchilik hamkorlarimiz uchun RevShare (RS) eng yuqori uzoq muddatli daromad beradi — birinchi tajriba sifatida shuni sinab ko'rishni tavsiya qilamiz.",
        "reg_please_use_buttons": "Iltimos, yuqoridagi tugmalardan birini tanlang.",
        "offer_rs": "🎯 RS bo'yicha sizga 45% gacha komissiya taklif qilamiz. Birinchi natijalaringizni ko'rgach, Fix va boshqa modellarni ham muhokama qilishimiz mumkin.",
        "offer_other": "📊 Statistikangizni ko'rib chiqamiz. Ro'yxatdan to'liq o'tganingizdan so'ng Tommy shaxsan siz bilan bog'lanib, aniq shartlar va summani muhokama qiladi.",
        "ask_email": "Davom etish uchun emailingizni yuboring:",
        "ask_username": "Telegram username?",
        "ask_geo": "Qaysi davlatlar (GEO) bo'yicha trafik yuritasiz?",
        "ask_promo": "Qanday promo-materiallardan foydalanasiz (banner, promokod va h.k.)? Hali yo'q bo'lsa \"yo'q\" deb yozing.",
        "invalid_email": "⚠️ Email formati noto'g'ri. Iltimos, to'g'ri email manzilingizni yozing (masalan: ism@gmail.com).",
        "invalid_username": "⚠️ Telegram username @ belgisi bilan boshlanishi kerak (masalan: @username). Qayta yozing.",
        "partner_prompt": "Qaysi yo'nalishda yordam kerak? (masalan: FTD oshirish, trafik manbai, konversiya) — yozing, men maslahat beraman.",
        "payment_prompt": "To'lov bilan bog'liq savolingizni yozing. Zarur bo'lsa, Tommy'ga yuboraman.",
        "other_prompt": "Savolingizni yozing, javob beraman yoki Tommy'ga yetkazaman.",
        "reply_prefix": "📩 Tommy'dan javob:\n\n",
        "no_guarantee": "\n\n⚠️ Eslatma: aniq daromad yoki to'lov miqdorini kafolatlay olmayman — bu shartlar individual tarzda Tommy bilan kelishiladi.",
        "ai_unavailable": "⚠️ Hozir AI xizmatiga ulanib bo'lmadi. Xabaringiz Tommy'ga to'g'ridan-to'g'ri yuborildi, tez orada javob beradi.",
    },
    "ru": {
        "welcome": (
            "Здравствуйте! 👋\n"
            "Я AI-ассистент команды Tommy — отвечаю на любые вопросы о партнёрской программе LuckyPari "
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
        "model_more_questions": "\n\n💬 Если есть вопросы, напишите их здесь — отвечу подробнее.",
        "reg_step1": (
            f"Начинаем регистрацию! 🎯\n\nСначала зарегистрируйтесь на официальном сайте:\n{REGISTRATION_URL}\n\n"
            "Теперь ответьте на несколько вопросов.\n\n"
            "Ведёте ли вы Telegram-канал на тему казино/спортивных ставок? Если да, пришлите ссылку на канал.\n"
            "Если вы сотрудничали с другими букмекерами, пришлите вашу статистику (скриншот или краткое описание).\n"
            "Если ни то, ни другое не подходит, просто напишите \"нет\".\n\n"
            "В любой момент можно отменить регистрацию командой /cancel."
        ),
        "reg_thanks": "Спасибо! Данные отправлены Tommy, он свяжется с вами в ближайшее время.",
        "reg_cancelled": "Регистрация отменена.",
        "reg_model_choose": "Спасибо! Какую модель сотрудничества вы хотите выбрать?",
        "reg_recommend_rs": "\n\n💡 Рекомендация: для большинства партнёров RevShare (RS) приносит наибольший долгосрочный доход — рекомендуем попробовать именно эту модель для начала.",
        "reg_please_use_buttons": "Пожалуйста, выберите один из вариантов выше.",
        "offer_rs": "🎯 По RS мы предлагаем вам комиссию до 45%. После первых результатов сможем обсудить также Fix и другие модели.",
        "offer_other": "📊 Мы рассмотрим вашу статистику. После полной регистрации Tommy лично свяжется с вами и обсудит точные условия и сумму.",
        "ask_email": "Для продолжения пришлите ваш email:",
        "ask_username": "Telegram username?",
        "ask_geo": "По каким странам (GEO) вы направляете трафик?",
        "ask_promo": "Какие промо-материалы вы используете (баннеры, промокоды и т.д.)? Если пока нет, напишите \"нет\".",
        "invalid_email": "⚠️ Неверный формат email. Пожалуйста, напишите корректный адрес (например: ivan@gmail.com).",
        "invalid_username": "⚠️ Telegram username должен начинаться с @ (например: @username). Напишите заново.",
        "partner_prompt": "В каком направлении нужна помощь? (например: рост FTD, источники трафика, конверсия) — напишите, я подскажу.",
        "payment_prompt": "Напишите вопрос по выплатам. При необходимости передам Tommy.",
        "other_prompt": "Напишите вопрос, я отвечу или передам Tommy.",
        "reply_prefix": "📩 Ответ от Tommy:\n\n",
        "no_guarantee": "\n\n⚠️ Обратите внимание: я не могу гарантировать доход или размер выплат — эти условия согласовываются индивидуально с Tommy.",
        "ai_unavailable": "⚠️ Не удалось подключиться к AI. Ваше сообщение отправлено напрямую Tommy, он скоро ответит.",
    },
    "en": {
        "welcome": (
            "Hello! 👋\n"
            "I'm Tommy's AI assistant — I answer any question about the LuckyPari affiliate program "
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
        "model_more_questions": "\n\n💬 If you have questions, write them here — I'll explain in more detail.",
        "reg_step1": (
            f"Let's start registration! 🎯\n\nFirst, register on the official site:\n{REGISTRATION_URL}\n\n"
            "Now please answer a few questions.\n\n"
            "Do you run a Telegram channel on casino/sports betting? If so, send the channel link.\n"
            "If you've worked with other bookmakers, send your stats (screenshot or brief description).\n"
            "If neither applies to you, just write \"no\".\n\n"
            "You can cancel anytime with /cancel."
        ),
        "reg_thanks": "Thanks! Your details were sent to Tommy, he'll reach out soon.",
        "reg_cancelled": "Registration cancelled.",
        "reg_model_choose": "Thanks! Which cooperation model would you like to work with?",
        "reg_recommend_rs": "\n\n💡 Recommendation: for most of our partners, RevShare (RS) delivers the highest long-term income — we recommend trying it first.",
        "reg_please_use_buttons": "Please choose one of the options above.",
        "offer_rs": "🎯 For RS we offer you a commission of up to 45%. After your first results, we can also discuss Fix and other models.",
        "offer_other": "📊 We'll review your statistics. After you complete registration, Tommy will personally contact you to discuss exact terms and amount.",
        "ask_email": "To continue, send your email:",
        "ask_username": "Telegram username?",
        "ask_geo": "Which countries (GEO) do you drive traffic to?",
        "ask_promo": "What promo materials do you use (banners, promo codes, etc)? If none yet, write \"no\".",
        "invalid_email": "⚠️ Invalid email format. Please write a correct email address (e.g. name@gmail.com).",
        "invalid_username": "⚠️ Telegram username must start with @ (e.g. @username). Please try again.",
        "partner_prompt": "What area do you need help with? (e.g. increasing FTDs, traffic sources, conversion) — write in, I'll advise.",
        "payment_prompt": "Write your payment-related question. I'll forward it to Tommy if needed.",
        "other_prompt": "Write your question, I'll answer or pass it to Tommy.",
        "reply_prefix": "📩 Reply from Tommy:\n\n",
        "no_guarantee": "\n\n⚠️ Note: I can't guarantee income or payment amounts — those terms are agreed individually with Tommy.",
        "ai_unavailable": "⚠️ Couldn't connect to the AI right now. Your message was sent directly to Tommy, he'll reply soon.",
    },
}

MODEL_NAMES = {
    "uz": ["CPA", "RevShare (RS)", "Hybrid", "Postpay", "Fix"],
    "ru": ["CPA", "RevShare (RS)", "Hybrid", "Postpay", "Fix"],
    "en": ["CPA", "RevShare (RS)", "Hybrid", "Postpay", "Fix"],
}

MODEL_FACTS = {
    "uz": [
        "CPA: har bir sifatli o'yinchi (FTD) uchun qat'iy summa; aniq stavka Tommy bilan individual belgilanadi.",
        "RevShare (RS): referral orqali kelgan o'yinchi daromadidan foiz, hajmi trafik sifatiga qarab 50% gacha; o'yinchi faol bo'lgan har oy davom etadi.",
        "Hybrid: CPA (FTD'da darhol to'lov) + RevShare (doimiy foiz) birikmasi.",
        "Postpay: kelishilgan KPI (masalan, aniq sonli sifatli FTD) bajarilgach to'lanadi; barqaror trafik uchun mos.",
        "Fix: kelishilgan shartlar asosida belgilangan reklama byudjeti; yirik yoki tekshirilgan trafik manbalari uchun, aniq summa Tommy bilan alohida kelishiladi.",
    ],
    "ru": [
        "CPA: фиксированная сумма за каждого качественного игрока (FTD); точная ставка определяется индивидуально с Tommy.",
        "RevShare (RS): процент от дохода игрока, пришедшего по рефералке, до 50% в зависимости от качества трафика; продолжается каждый месяц, пока игрок активен.",
        "Hybrid: комбинация CPA (мгновенная выплата при FTD) + RevShare (постоянный процент).",
        "Postpay: оплата после выполнения согласованных KPI (например, определённого числа качественных FTD); подходит для стабильного трафика.",
        "Fix: фиксированный рекламный бюджет по согласованным условиям; для крупных или проверенных источников трафика, точная сумма обсуждается отдельно с Tommy.",
    ],
    "en": [
        "CPA: a fixed amount for each qualified player (FTD); the exact rate is set individually with Tommy.",
        "RevShare (RS): a percentage of revenue from a referred player, up to 50% depending on traffic quality; continues every month the player stays active.",
        "Hybrid: a combination of CPA (instant payment on FTD) + RevShare (ongoing percentage).",
        "Postpay: paid after agreed KPIs are met (e.g. a specific number of quality FTDs); suited to stable traffic.",
        "Fix: a fixed advertising budget based on agreed terms; for large or verified traffic sources, exact amount discussed separately with Tommy.",
    ],
}


# ============================================================
# 4) AI MEXANIZMI (Claude — botning "miyasi")
# ============================================================

_ai_client = Anthropic(api_key=ANTHROPIC_API_KEY, timeout=AI_REQUEST_TIMEOUT)
_conversation_history: dict[int, list[dict]] = defaultdict(list)

TOMMY_CONTACT = "@Tommy_Luckypar"

SYSTEM_PROMPT = {
    "uz": (
        "Sen LuckyPari affiliate dasturining AI-yordamchisisan (Tommy jamoasi nomidan). "
        "Hamkorlarga trafik, FTD oshirish, konversiya, reklama kanallari (Telegram, Instagram, "
        "Facebook, Google Ads, TikTok, Push/Native Ads va h.k.), hamkorlik modellari (CPA, RevShare, "
        "Hybrid, Postpay, Fix) va dastur bo'yicha istalgan savolga aniq, amaliy javob ber. "
        f"Agar kimdir Tommy bilan bog'lanish, uning Telegram manzili yoki kontaktini so'rasa, "
        f"to'g'ridan-to'g'ri shu username'ni ber: {TOMMY_CONTACT}. "
        "Agar hamkor FTD past yoki reklama natija bermayapti desa, mustaqil ravishda aniq amaliy "
        "takliflar ber: landing sahifa sifatini tekshirish, auditoriya segmentatsiyasini aniqlashtirish, "
        "kreativlarni (banner/matn) A/B testlash, referral bonus yoki konkurs tashkil qilish, "
        "trafik manbasini diversifikatsiya qilish kabi. "
        "Javobing qisqa (3-6 jumla), do'stona va professional bo'lsin. "
        "FORMATLASH: Telegram oddiy matnni ko'rsatadi, Markdown belgilarini emas — shuning uchun "
        "#, ##, ---, ** kabi belgilarni HECH QACHON ishlatma. Sarlavha kerak bo'lsa mos emoji bilan "
        "boshlang'ich jumla qil (masalan '🎯 FTD oshirish uchun:'). Ro'yxat kerak bo'lsa oddiy emoji "
        "yoki raqam bilan boshla (masalan '1)' yoki '✅'), tire (-) yoki yulduzcha ishlatma. "
        "Har bir javob oxirida foydalanuvchini yana savol berishga tabiiy tarzda taklif qil, "
        "lekin har safar boshqacha so'zlar bilan — bir xil jumlani takrorlama. "
        "Hech qachon aniq daromad, to'lov miqdori yoki foizni o'zingdan o'ylab topib aytma — faqat senga "
        "berilgan faktlarga tayan; kafolatlangan natija va'da qilma. Bunday savol bo'lsa, buni Tommy bilan "
        "individual kelishish kerakligini ayt. "
        "Agar savol umuman aloqador bo'lmasa yoki juda maxsus (masalan aniq shartnoma, hisob muammosi) bo'lsa, "
        "buni Tommy'ga yetkazishingni ayt."
    ),
    "ru": (
        "Ты AI-ассистент партнёрской программы LuckyPari (от команды Tommy). "
        "Отвечай партнёрам конкретно и практично на вопросы о трафике, росте FTD, конверсии, рекламных каналах "
        "(Telegram, Instagram, Facebook, Google Ads, TikTok, Push/Native Ads и т.д.), моделях сотрудничества "
        "(CPA, RevShare, Hybrid, Postpay, Fix) и любые вопросы о программе. "
        f"Если кто-то спрашивает контакт Tommy, его Telegram или как с ним связаться, "
        f"сразу дай этот username: {TOMMY_CONTACT}. "
        "Если партнёр говорит, что FTD низкий или реклама не даёт результата, самостоятельно предложи "
        "конкретные практические шаги: проверить качество лендинга, уточнить сегментацию аудитории, "
        "протестировать креативы (баннеры/тексты) A/B-методом, запустить реферальный бонус или конкурс, "
        "диверсифицировать источники трафика. "
        "Ответ короткий (3-6 предложений), дружелюбный и профессиональный. "
        "ФОРМАТИРОВАНИЕ: Telegram показывает обычный текст, а не Markdown — поэтому НИКОГДА не используй "
        "символы #, ##, ---, **. Если нужен заголовок, начни предложение с подходящего эмодзи "
        "(например '🎯 Как повысить FTD:'). Для списка используй эмодзи или цифру с скобкой "
        "(например '1)' или '✅'), не используй тире (-) или звёздочки. "
        "В конце каждого ответа естественно предложи задать ещё вопрос, но каждый раз другими словами — "
        "не повторяй одну и ту же фразу. "
        "Никогда не придумывай конкретный доход, суммы выплат или проценты сам — опирайся только на "
        "предоставленные тебе факты; не обещай гарантированный результат. Если спрашивают об этом, скажи, "
        "что это согласовывается индивидуально с Tommy. "
        "Если вопрос не по теме или слишком специфичен (конкретный договор, проблема с аккаунтом), "
        "скажи, что передашь это Tommy."
    ),
    "en": (
        "You are the AI assistant of the LuckyPari affiliate program (on behalf of Tommy's team). "
        "Give partners concrete, practical answers about traffic, increasing FTDs, conversion, ad channels "
        "(Telegram, Instagram, Facebook, Google Ads, TikTok, Push/Native Ads, etc), cooperation models "
        "(CPA, RevShare, Hybrid, Postpay, Fix), and any question about the program. "
        f"If someone asks for Tommy's contact, Telegram, or how to reach him, "
        f"give them this username directly: {TOMMY_CONTACT}. "
        "If a partner says FTDs are low or ads aren't performing, independently suggest concrete practical "
        "steps: check landing page quality, refine audience targeting, A/B test creatives (banners/copy), "
        "launch a referral bonus or contest, diversify traffic sources. "
        "Keep answers short (3-6 sentences), friendly and professional. "
        "FORMATTING: Telegram displays plain text, not Markdown — so NEVER use symbols like #, ##, ---, **. "
        "If a heading is needed, start a sentence with a fitting emoji instead (e.g. '🎯 To boost FTDs:'). "
        "For lists, use an emoji or a number with a parenthesis (e.g. '1)' or '✅'), never use dashes (-) "
        "or asterisks. "
        "End each answer with a natural invitation to ask more, but phrase it differently each time — "
        "never repeat the same closing line. "
        "Never invent specific income, payment amounts, or percentages yourself — rely only on facts "
        "given to you; never promise a guaranteed result. If asked, say those terms are agreed "
        "individually with Tommy. "
        "If the question is unrelated or too specific (a particular contract, account issue), "
        "say you'll pass it on to Tommy."
    ),
}


def _trim_history(chat_id: int) -> None:
    history = _conversation_history[chat_id]
    if len(history) > AI_HISTORY_LIMIT:
        del history[: len(history) - AI_HISTORY_LIMIT]


def reset_history(chat_id: int) -> None:
    _conversation_history.pop(chat_id, None)


def get_ai_response(chat_id: int, lang: str, user_message: str) -> str | None:
    """Claude API orqali, oldingi suhbat kontekstini hisobga olib javob oladi."""
    history = _conversation_history[chat_id]
    messages = history + [{"role": "user", "content": user_message}]

    try:
        response = _ai_client.messages.create(
            model=AI_MODEL,
            max_tokens=AI_MAX_TOKENS,
            system=SYSTEM_PROMPT.get(lang, SYSTEM_PROMPT["uz"]),
            messages=messages,
        )
        answer = response.content[0].text.strip()
    except APITimeoutError:
        logger.error("AI so'rovi timeout bo'ldi (chat_id=%s)", chat_id)
        return None
    except APIError as e:
        logger.error("AI API xatosi (chat_id=%s): %s", chat_id, e)
        return None
    except Exception as e:
        logger.exception("AI kutilmagan xato (chat_id=%s): %s", chat_id, e)
        return None

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": answer})
    _trim_history(chat_id)
    return answer


def get_model_explanation(chat_id: int, lang: str, model_index: int) -> str | None:
    """Berilgan hamkorlik modelini AI orqali, tasdiqlangan faktlarga tayanib tushuntiradi."""
    name = MODEL_NAMES[lang][model_index]
    facts = MODEL_FACTS[lang][model_index]
    prompt = {
        "uz": f"'{name}' hamkorlik modelini menga qiziqarli va batafsil tushuntiring. "
              f"Faqat quyidagi tasdiqlangan faktlarga tayaning, boshqa raqam o'ylab topmang: {facts}",
        "ru": f"Объясните мне модель сотрудничества '{name}' подробно и интересно. "
              f"Опирайтесь только на следующие подтверждённые факты, не придумывайте другие цифры: {facts}",
        "en": f"Explain the '{name}' cooperation model to me in an engaging, detailed way. "
              f"Rely only on the following confirmed facts, don't invent other numbers: {facts}",
    }[lang]
    return get_ai_response(chat_id, lang, prompt)


# ============================================================
# 5) HOLAT SAQLASH VA KLAVIATURALAR
# ============================================================

user_lang: dict[int, str] = {}
user_mode: dict[int, str] = {}  # "partner" | "payment" | "other" | None

REG_MODEL, REG_EMAIL, REG_USERNAME, REG_GEO, REG_PROMO = range(5)


def main_menu_kb(lang: str) -> InlineKeyboardMarkup:
    t = TEXTS[lang]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t["btn_models"], callback_data="models")],
        [InlineKeyboardButton(t["btn_register"], callback_data="register")],
        [InlineKeyboardButton(t["btn_partner"], callback_data="partner")],
        [InlineKeyboardButton(t["btn_payment"], callback_data="payment")],
        [InlineKeyboardButton(t["btn_other"], callback_data="other")],
    ])


def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang_uz"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
    ]])


def models_kb(lang: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(name, callback_data=f"model_{i}")]
               for i, name in enumerate(MODEL_NAMES[lang])]
    buttons.append([InlineKeyboardButton(TEXTS[lang]["btn_back"], callback_data="back")])
    return InlineKeyboardMarkup(buttons)


def model_detail_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(TEXTS[lang]["btn_back"], callback_data="back")]])


def reg_model_kb(lang: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(name, callback_data=f"regmodel_{i}")]
               for i, name in enumerate(MODEL_NAMES[lang])]
    return InlineKeyboardMarkup(buttons)


def get_lang(chat_id: int) -> str:
    return user_lang.get(chat_id, "uz")


# ============================================================
# 6) ADMINGA FORWARD QILISH
# ============================================================

async def forward_to_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, lang: str, category: str, text: str) -> None:
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


# ============================================================
# 7) ASOSIY BUYRUQLAR
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Tilni tanlang / Выберите язык / Choose language:", reply_markup=lang_kb())


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    lang = get_lang(chat_id)
    context.user_data["reg"] = {}
    user_mode[chat_id] = None
    await update.message.reply_text(TEXTS[lang]["reg_cancelled"], reply_markup=main_menu_kb(lang))
    return ConversationHandler.END


# ============================================================
# 8) UMUMIY TUGMALAR (registratsiyaga aloqasiz)
# ============================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    if data.startswith("lang_"):
        lang = data.split("_")[1]
        user_lang[chat_id] = lang
        user_mode[chat_id] = None
        reset_history(chat_id)
        await context.bot.send_message(chat_id=chat_id, text=TEXTS[lang]["welcome"], reply_markup=main_menu_kb(lang))
        return

    lang = get_lang(chat_id)
    t = TEXTS[lang]

    if data == "models":
        await context.bot.send_message(chat_id=chat_id, text=t["models_intro"], reply_markup=models_kb(lang))

    elif data.startswith("model_"):
        idx = int(data.split("_")[1])
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        explanation = get_model_explanation(chat_id, lang, idx)
        name = MODEL_NAMES[lang][idx]
        if explanation:
            text = f"💰 {name}\n\n{explanation}{t['model_more_questions']}"
        else:
            text = f"💰 {name}\n\n{t['ai_unavailable']}"
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=model_detail_kb(lang))

    elif data == "partner":
        user_mode[chat_id] = "partner"
        await context.bot.send_message(chat_id=chat_id, text=t["partner_prompt"])

    elif data == "payment":
        user_mode[chat_id] = "payment"
        await context.bot.send_message(chat_id=chat_id, text=t["payment_prompt"] + t["no_guarantee"])

    elif data == "other":
        user_mode[chat_id] = "other"
        await context.bot.send_message(chat_id=chat_id, text=t["other_prompt"])

    elif data == "back":
        user_mode[chat_id] = None
        await context.bot.send_message(chat_id=chat_id, text=t["welcome"], reply_markup=main_menu_kb(lang))


# ============================================================
# 9) RO'YXATDAN O'TISH (ConversationHandler)
# ============================================================

async def reg_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    lang = get_lang(chat_id)
    context.user_data["reg"] = {}
    await context.bot.send_message(chat_id=chat_id, text=TEXTS[lang]["reg_step1"])
    return REG_MODEL


async def reg_channel_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    lang = get_lang(chat_id)
    context.user_data["reg"]["channel"] = update.message.text.strip()
    await update.message.reply_text(
        TEXTS[lang]["reg_model_choose"] + TEXTS[lang]["reg_recommend_rs"],
        reply_markup=reg_model_kb(lang),
    )
    return REG_MODEL


async def reg_model_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    lang = get_lang(chat_id)
    idx = int(query.data.split("_")[1])
    context.user_data["reg"]["model"] = MODEL_NAMES[lang][idx]
    offer = TEXTS[lang]["offer_rs"] if idx == 1 else TEXTS[lang]["offer_other"]
    await context.bot.send_message(chat_id=chat_id, text=offer + "\n\n" + TEXTS[lang]["ask_email"])
    return REG_EMAIL


async def reg_email_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    lang = get_lang(chat_id)
    text = update.message.text.strip()
    if not is_valid_email(text):
        await update.message.reply_text(TEXTS[lang]["invalid_email"])
        return REG_EMAIL
    context.user_data["reg"]["email"] = text
    await update.message.reply_text(TEXTS[lang]["ask_username"])
    return REG_USERNAME


async def reg_username_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    lang = get_lang(chat_id)
    text = update.message.text.strip()
    if not is_valid_username(text):
        await update.message.reply_text(TEXTS[lang]["invalid_username"])
        return REG_USERNAME
    context.user_data["reg"]["user"] = text
    await update.message.reply_text(TEXTS[lang]["ask_geo"])
    return REG_GEO


async def reg_geo_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    lang = get_lang(chat_id)
    context.user_data["reg"]["geo"] = update.message.text.strip()
    await update.message.reply_text(TEXTS[lang]["ask_promo"])
    return REG_PROMO


async def reg_promo_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    lang = get_lang(chat_id)
    reg = context.user_data.get("reg", {})
    reg["promo"] = update.message.text.strip()

    await forward_to_admin(
        context, chat_id, lang, "🆕 YANGI HAMKOR / NEW PARTNER",
        f"Email: {reg.get('email')}\n"
        f"User: {reg.get('user')}\n"
        f"Kanal: {reg.get('channel')}\n"
        f"Rs: {reg.get('model')}\n"
        f"Geo: {reg.get('geo')}\n"
        f"Promo: {reg.get('promo')}",
    )
    await update.message.reply_text(TEXTS[lang]["reg_thanks"], reply_markup=main_menu_kb(lang))
    context.user_data["reg"] = {}
    return ConversationHandler.END


async def reg_invalid_model_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    lang = get_lang(chat_id)
    reg = context.user_data.setdefault("reg", {})
    if "channel" not in reg:
        return await reg_channel_received(update, context)
    await update.message.reply_text(TEXTS[lang]["reg_please_use_buttons"], reply_markup=reg_model_kb(lang))
    return REG_MODEL


registration_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(reg_entry, pattern="^register$")],
    states={
        REG_MODEL: [
            CallbackQueryHandler(reg_model_chosen, pattern="^regmodel_"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, reg_invalid_model_step),
        ],
        REG_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_email_received)],
        REG_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_username_received)],
        REG_GEO: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_geo_received)],
        REG_PROMO: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_promo_received)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)


# ============================================================
# 10) ERKIN XABARLAR (AI orqali javob)
# ============================================================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    lang = get_lang(chat_id)
    t = TEXTS[lang]
    text = update.message.text

    if chat_id == ADMIN_CHAT_ID and update.message.reply_to_message:
        original = update.message.reply_to_message.text or ""
        if "user_id:" in original:
            try:
                target_id = int(original.split("user_id:")[1].split()[0])
                target_lang = get_lang(target_id)
                await context.bot.send_message(
                    chat_id=target_id,
                    text=TEXTS[target_lang]["reply_prefix"] + text,
                )
            except (ValueError, IndexError):
                pass
        return

    mode = user_mode.get(chat_id)
    category_map = {
        "partner": "HAMKOR SO'ROVI / PARTNER REQUEST",
        "payment": "TO'LOV SAVOLI / PAYMENT QUESTION",
        "other": "BOSHQA SAVOL / OTHER QUESTION",
    }

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    ai_answer = get_ai_response(chat_id, lang, text)
    urgent = is_urgent(text)
    category = category_map.get(mode, "ERKIN SAVOL / FREE QUESTION")

    if ai_answer:
        await update.message.reply_text(ai_answer, reply_markup=model_detail_kb(lang))
        if urgent:
            await forward_to_admin(
                context, chat_id, lang, f"🚨 DOLZARB / URGENT — {category}",
                f"Savol: {text}\n\nAI javobi: {ai_answer}",
            )
    else:
        await forward_to_admin(context, chat_id, lang, f"⚠️ AI JAVOB BERMADI — {category}", text)
        await update.message.reply_text(t["ai_unavailable"], reply_markup=model_detail_kb(lang))

    if mode is not None:
        user_mode[chat_id] = None


# ============================================================
# 11) XATOLARNI BOSHQARISH VA ISHGA TUSHIRISH
# ============================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Kutilmagan xato: %s", context.error, exc_info=context.error)


def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(registration_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)

    logger.info("LuckyPari support bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
