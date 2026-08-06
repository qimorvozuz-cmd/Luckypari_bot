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
        [KeyboardButton(text="📥 APK yuklab olish"), KeyboardButton(text="👤 Shaxsiy kabinet")],
        [KeyboardButton(text="🛟 Yordam")],
    ])


def approval_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve:{user_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject:{user_id}"),
    ]])
