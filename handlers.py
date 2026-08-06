import asyncio
import time
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from config import Settings
from database import Database
from keyboards import (
    contest_keyboard, main_menu, registration_keyboard, subscription_keyboard,
    support_reply_keyboard,
)
from signals import apple_signal, chicken_signal, format_signal
from utils import animate_message, is_subscribed, user_label


class Registration(StatesGroup):
    player_id = State()


class Support(StatesGroup):
    message = State()


def create_user_router(settings: Settings, db: Database) -> Router:
    router = Router(name="users")
    cooldowns: dict[int, float] = {}

    async def gate(message: Message, bot: Bot) -> bool:
        if not await is_subscribed(bot, settings.channel_id, message.from_user.id):
            await message.answer("Botdan foydalanish uchun kanalga obuna bo'ling.",
                                 reply_markup=subscription_keyboard(settings.channel_url))
            return False
        return True

    @router.message(CommandStart())
    async def start(message: Message, bot: Bot, state: FSMContext):
        await state.clear()
        await db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        if not await gate(message, bot):
            return
        user = await db.get_user(message.from_user.id)
        if user["status"] == "approved":
            await message.answer("👋 VIP botga xush kelibsiz!", reply_markup=main_menu())
        else:
            deposit = f"{settings.min_deposit:,}".replace(",", " ")
            await message.answer(
                f"🚀 Ro'yxatdan o'tishda <b>{settings.promo_code}</b> promo kodidan foydalaning.\n\n"
                f"💳 Minimal depozit: <b>{deposit} so'm</b>\n"
                "Depozitdan keyin Player ID yuboring.",
                                 reply_markup=registration_keyboard(settings.registration_url))

    @router.callback_query(F.data == "check_subscription")
    async def check(callback: CallbackQuery, bot: Bot):
        if await is_subscribed(bot, settings.channel_id, callback.from_user.id):
            deposit = f"{settings.min_deposit:,}".replace(",", " ")
            await callback.message.answer_dice(emoji="🎯")
            await callback.message.answer(
                f"✅ Obuna tasdiqlandi!\n<b>{settings.promo_code}</b> promo kodi bilan ro'yxatdan o'ting.\n"
                f"Minimal depozit: <b>{deposit} so'm</b>",
                                          reply_markup=registration_keyboard(settings.registration_url))
            await callback.answer("Tasdiqlandi")
        else:
            await callback.answer("Hali kanalga obuna emassiz", show_alert=True)

    @router.callback_query(F.data == "send_player_id")
    async def ask_player_id(callback: CallbackQuery, state: FSMContext):
        await state.set_state(Registration.player_id)
        await callback.message.answer("Luckypari Player ID raqamingizni yuboring:")
        await callback.answer()

    @router.message(Registration.player_id)
    async def save_player_id(message: Message, state: FSMContext, bot: Bot):
        value = (message.text or "").strip()
        if not value.isdigit() or not 4 <= len(value) <= 20:
            await message.answer("Player ID 4–20 xonali raqam bo'lishi kerak. Qayta yuboring:")
            return
        await db.submit_player_id(message.from_user.id, value)
        await state.clear()
        await animate_message(
            message,
            ["📨 Ariza tayyorlanmoqda...", "🔐 Ma'lumotlar himoyalanmoqda...", "⏳ Ariza adminga yuborildi!"],
            0.45,
        )
        for admin_id in settings.admin_ids:
            try:
                deposit = f"{settings.min_deposit:,}".replace(",", " ")
                await bot.send_message(
                    admin_id,
                    f"🆕 Yangi ariza\n{user_label(message.from_user)}\nPlayer ID: <code>{value}</code>\n"
                    f"Tekshiriladigan minimal depozit: <b>{deposit} so'm</b>\n/pending",
                )
            except Exception:
                pass

    async def approved(message: Message, bot: Bot) -> bool:
        if message.from_user.id in settings.admin_ids:
            return True
        if not await gate(message, bot):
            return False
        user = await db.get_user(message.from_user.id)
        if not user or user["status"] != "approved":
            await message.answer("VIP kirish faollashtirilmagan. Player ID yuboring.",
                                 reply_markup=registration_keyboard(settings.registration_url))
            return False
        return True

    async def animated_signal(message: Message, bot: Bot, factory):
        if not await approved(message, bot):
            return
        left = 8 - (time.monotonic() - cooldowns.get(message.from_user.id, 0))
        if left > 0:
            await message.answer(f"⏳ Yangi signal uchun {int(left) + 1} soniya kuting.")
            return
        cooldowns[message.from_user.id] = time.monotonic()
        status = await animate_message(
            message,
            ["🔎 VIP serverga ulanmoqda...", "📡 O'yin ma'lumotlari olinmoqda...", "🧠 Signal hisoblanmoqda..."],
            0.45,
        )
        await bot.send_dice(message.chat.id, emoji="🎰")
        await asyncio.sleep(2.5)
        await status.edit_text("✅ <b>VIP SIGNAL TAYYOR!</b>")
        await message.answer(format_signal(factory()))

    @router.message(F.text == "🍎 Apple signal")
    async def apple(message: Message, bot: Bot):
        await animated_signal(message, bot, apple_signal)

    @router.message(F.text == "🐔 Chicken Road signal")
    async def chicken(message: Message, bot: Bot):
        await animated_signal(message, bot, chicken_signal)

    @router.message(F.text == "🏆 Konkurslar")
    async def contest(message: Message, bot: Bot):
        if not await approved(message, bot):
            return
        item = await db.active_contest()
        if not item:
            await message.answer("🏆 Hozircha faol konkurs yo'q.")
            return
        count = await db.contest_count(item["id"])
        await message.answer(f"🏆 <b>{item['title']}</b>\n\n{item['description']}\n\n👥 Ishtirokchilar: {count}",
                             reply_markup=contest_keyboard(item["id"]))

    @router.callback_query(F.data.startswith("contest_join:"))
    async def contest_join(callback: CallbackQuery):
        contest_id = int(callback.data.split(":", 1)[1])
        item = await db.active_contest()
        if not item or item["id"] != contest_id:
            await callback.answer("Bu konkurs yakunlangan", show_alert=True)
            return
        joined = await db.join_contest(contest_id, callback.from_user.id)
        await callback.answer("✅ Ishtirokingiz qabul qilindi!" if joined else "Siz avval qo'shilgansiz", show_alert=True)

    @router.message(F.text == "🎁 FreeBetlarim")
    async def freebets(message: Message, bot: Bot):
        if not await approved(message, bot):
            return
        rows = await db.user_freebets(message.from_user.id)
        if not rows:
            await message.answer("🎁 Sizda hozircha FreeBet yo'q.")
            return
        text = "🎁 <b>Sizning FreeBetlaringiz</b>\n\n" + "\n\n".join(
            f"Kod: <code>{row['code']}</code>\n{row['description']}" for row in rows
        )
        await message.answer(text)

    @router.message(F.text == "💎 VIP bo'lim")
    async def vip(message: Message, bot: Bot):
        if await approved(message, bot):
            await message.answer_dice(emoji="🎰")
            await message.answer(
                "💎 <b>VIP BO'LIM FAOL</b>\n\n"
                "✅ Animatsiyali Apple signallari\n✅ Chicken Road signallari\n"
                "✅ Maxsus konkurslar\n✅ Promo va FreeBet xabarlari"
            )

    @router.message(F.text == "🎁 Bonuslar")
    async def bonuses(message: Message, bot: Bot):
        if not await gate(message, bot):
            return
        deposit = f"{settings.min_deposit:,}".replace(",", " ")
        await message.answer_dice(emoji="🎲")
        await message.answer(
            f"🎁 <b>BONUSLAR</b>\n\nPromo-kod: <code>{settings.promo_code}</code>\n"
            f"Minimal depozit: <b>{deposit} so'm</b>\n\n"
            "Shaxsiy promo va FreeBetlar bot orqali alohida yuboriladi.",
            reply_markup=registration_keyboard(settings.registration_url),
        )

    @router.message(F.text == "📥 Luckypari APK")
    async def apk(message: Message, bot: Bot):
        if not await gate(message, bot):
            return
        path = Path(settings.apk_path)
        if path.is_file():
            await message.answer_document(FSInputFile(path), caption="📥 Luckypari APK")
        else:
            await message.answer("APK hozircha yuklanmagan. Administratorga murojaat qiling.")

    @router.message(F.text == "👤 Shaxsiy kabinet")
    async def cabinet(message: Message):
        user = await db.get_user(message.from_user.id)
        labels = {"approved": "✅ Tasdiqlangan", "pending": "⏳ Kutilmoqda", "rejected": "❌ Rad etilgan", "new": "🆕 Yangi"}
        await message.answer(f"👤 {message.from_user.full_name}\nID: <code>{message.from_user.id}</code>\n"
                             f"Player ID: <code>{user['player_id'] or '-'}</code>\nHolat: {labels.get(user['status'], user['status'])}")

    @router.message(F.text == "📊 Statistika")
    async def user_stats(message: Message):
        total, grouped = await db.stats()
        await message.answer(
            f"📊 <b>BOT STATISTIKASI</b>\n\n👥 Jami foydalanuvchilar: {total}\n"
            f"💎 VIP foydalanuvchilar: {grouped.get('approved', 0)}"
        )

    @router.message(F.text == "🛟 Yordam")
    async def help_message(message: Message, state: FSMContext):
        await state.set_state(Support.message)
        await message.answer(
            "🛟 <b>YORDAM MARKAZI</b>\n\nAdminga yuboriladigan xabaringizni yozing. "
            "Matn, rasm yoki hujjat yuborishingiz mumkin."
        )

    @router.message(Support.message)
    async def support_message(message: Message, state: FSMContext, bot: Bot):
        delivered = 0
        for admin_id in settings.admin_ids:
            try:
                await bot.forward_message(admin_id, message.chat.id, message.message_id)
                await bot.send_message(
                    admin_id,
                    f"🛟 <b>YANGI YORDAM XABARI</b>\n{user_label(message.from_user)}",
                    reply_markup=support_reply_keyboard(message.from_user.id),
                )
                delivered += 1
            except Exception:
                pass
        await state.clear()
        if delivered:
            await animate_message(
                message,
                ["📨 Xabar yuborilmoqda...", "🔐 Admin panelga uzatilmoqda...", "✅ Xabaringiz adminga yetkazildi!"],
                0.4,
            )
        else:
            await message.answer("❌ Xabarni adminga yuborib bo'lmadi. Keyinroq urinib ko'ring.")

    return router
