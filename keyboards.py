from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def subscription_keyboard(channel_url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga qo'shilish", url=channel_url)],
        [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_subscription")],
    ])


def membership_keyboard(registration_url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Luckypari'dan ro'yxatdan o'tish", url=registration_url)],
        [InlineKeyboardButton(text="💎 VIP — 50 000 so'm", callback_data="apply:vip")],
        [InlineKeyboardButton(text="👑 MEGA VIP — 100 000 so'm", callback_data="apply:mega")],
    ])


def user_menu(tier: str):
    rows = [
        [KeyboardButton(text="🍎 Apple"), KeyboardButton(text="🐔 Chicken Road")],
        [KeyboardButton(text="💣 Mines"), KeyboardButton(text="🚀 Aviator")],
        [KeyboardButton(text="✈️ Lucky Jet"), KeyboardButton(text="📅 Kunlik stavkalar")],
        [KeyboardButton(text="🏆 Konkurslar"), KeyboardButton(text="🎁 Bonus va promolar")],
        [KeyboardButton(text="🎟 FreeBetlarim"), KeyboardButton(text="👥 Referal tizim")],
        [KeyboardButton(text="📥 Luckypari APK"), KeyboardButton(text="👤 Kabinet")],
    ]
    if tier == "mega":
        rows.insert(3, [KeyboardButton(text="🔥 Yuqori koeffitsiyent"), KeyboardButton(text="🧠 Casino tahlillari")])
        rows.insert(4, [KeyboardButton(text="📈 MEGA hisobotlar"), KeyboardButton(text="👑 MEGA VIP")])
    else:
        rows.insert(3, [KeyboardButton(text="💎 VIP bo'lim"), KeyboardButton(text="⬆️ MEGA VIPga o'tish")])
    rows.append([KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🛟 Yordam")])
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=rows)


def admin_home_menu():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="🛠 Admin panel")],
    ])


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆕 Arizalar", callback_data="admin:pending"),
         InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin:users")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin:stats"),
         InlineKeyboardButton(text="🔍 Obunalarni tekshirish", callback_data="admin:subscriptions")],
        [InlineKeyboardButton(text="💬 Xabar", callback_data="admin:message"),
         InlineKeyboardButton(text="📣 Reklama", callback_data="admin:advert")],
        [InlineKeyboardButton(text="🎟 Promo", callback_data="admin:promo"),
         InlineKeyboardButton(text="🎁 FreeBet", callback_data="admin:freebet")],
        [InlineKeyboardButton(text="🏆 Konkurs", callback_data="admin:contest"),
         InlineKeyboardButton(text="🛑 Konkurslarni yopish", callback_data="admin:contest_close")],
        [InlineKeyboardButton(text="📅 Kunlik stavka", callback_data="admin:daily"),
         InlineKeyboardButton(text="🔥 Yuqori koeff.", callback_data="admin:high_odds")],
        [InlineKeyboardButton(text="🧠 Casino tahlili", callback_data="admin:casino"),
         InlineKeyboardButton(text="📈 MEGA hisobot", callback_data="admin:report")],
        [InlineKeyboardButton(text="➕ Kanal/guruh", callback_data="admin:join_request"),
         InlineKeyboardButton(text="📦 APK yuklash", callback_data="admin:apk")],
        [InlineKeyboardButton(text="💰 Referal bonuslar", callback_data="admin:referrals")],
    ])


def audience_keyboard(kind: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Barcha VIP foydalanuvchilarga", callback_data=f"aud:{kind}:ALL")],
        [InlineKeyboardButton(text="💎 Faqat VIP", callback_data=f"aud:{kind}:VIP"),
         InlineKeyboardButton(text="👑 Faqat MEGA VIP", callback_data=f"aud:{kind}:MEGA")],
        [InlineKeyboardButton(text="🎯 Tanlangan ID'larga", callback_data=f"aud:{kind}:SELECTED")],
        [InlineKeyboardButton(text="⬅️ Admin panel", callback_data="admin:home")],
    ])


def approval_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve:{user_id}"),
         InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"reject:{user_id}")],
        [InlineKeyboardButton(text="👤 To'liq tekshirish", callback_data=f"user:{user_id}")],
    ])


def user_manage_keyboard(user_id: int, blocked: bool = False):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 VIP qilish", callback_data=f"tier:vip:{user_id}"),
         InlineKeyboardButton(text="👑 MEGA VIP qilish", callback_data=f"tier:mega:{user_id}")],
        [InlineKeyboardButton(text="✉️ Alohida xabar", callback_data=f"direct:{user_id}"),
         InlineKeyboardButton(text="🚫 Blokdan chiqarish" if blocked else "🚫 Bloklash",
                              callback_data=f"block:{0 if blocked else 1}:{user_id}")],
        [InlineKeyboardButton(text="⛔ VIPni bekor qilish", callback_data=f"tier:none:{user_id}")],
    ])


def contest_keyboard(contest_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Konkursda qatnashish", callback_data=f"contest_join:{contest_id}")
    ]])


def support_reply_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="↩️ Foydalanuvchiga javob", callback_data=f"support_reply:{user_id}")
    ]])


def join_keyboard(title: str, url: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"➕ {title}", url=url)
    ]])


def bonus_paid_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ To'landi", callback_data=f"bonus_paid:{user_id}")
    ]])
