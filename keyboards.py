from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def subscription_keyboard(channel_url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga qo'shilish", url=channel_url)],
        [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_subscription")],
    ])


def registration_keyboard(url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Ro'yxatdan o'tish", url=url)],
        [InlineKeyboardButton(text="🆔 Player ID yuborish", callback_data="send_player_id")],
    ])


def main_menu():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="🍎 Apple signal"), KeyboardButton(text="🐔 Chicken Road signal")],
        [KeyboardButton(text="💎 VIP bo'lim"), KeyboardButton(text="🏆 Konkurslar")],
        [KeyboardButton(text="🎁 Bonuslar"), KeyboardButton(text="📥 Luckypari APK")],
        [KeyboardButton(text="👤 Shaxsiy kabinet"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="🎁 FreeBetlarim")],
        [KeyboardButton(text="🛟 Yordam")],
    ])


def admin_home_menu():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="🛠 Admin panel")],
        [KeyboardButton(text="🍎 Apple signal"), KeyboardButton(text="🐔 Chicken Road signal")],
        [KeyboardButton(text="🏆 Konkurslar"), KeyboardButton(text="📊 Statistika")],
    ])


def approval_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve:{user_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject:{user_id}"),
    ]])


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Arizalar", callback_data="admin:pending"),
         InlineKeyboardButton(text="📊 Statistika", callback_data="admin:stats")],
        [InlineKeyboardButton(text="📣 Reklama yuborish", callback_data="admin:advert"),
         InlineKeyboardButton(text="🎟 Promo yuborish", callback_data="admin:promo")],
        [InlineKeyboardButton(text="🎁 FreeBet yuborish", callback_data="admin:freebet"),
         InlineKeyboardButton(text="📦 APK yuklash", callback_data="admin:apk")],
        [InlineKeyboardButton(text="🔍 Obunalarni tekshirish", callback_data="admin:subscriptions")],
        [InlineKeyboardButton(text="🏆 Konkurs yaratish", callback_data="admin:contest"),
         InlineKeyboardButton(text="🛑 Konkursni yopish", callback_data="admin:contest_close")],
    ])


def contest_keyboard(contest_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ishtirok etish", callback_data=f"contest_join:{contest_id}")
    ]])


def audience_keyboard(kind: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Hammaga", callback_data=f"audience:{kind}:all")],
        [InlineKeyboardButton(text="🎯 Tanlanganlarga", callback_data=f"audience:{kind}:selected")],
        [InlineKeyboardButton(text="⬅️ Admin panel", callback_data="admin:home")],
    ])


def support_reply_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="↩️ Javob yozish", callback_data=f"support_reply:{user_id}")
    ]])
