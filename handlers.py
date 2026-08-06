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
from keyboards import contest_keyboard, main_menu, registration_keyboard, subscription_keyboard
from signals import apple_signal, chicken_signal, format_signal
from utils import is_subscribed, user_label


class Registration(StatesGroup):
    player_id = State()


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
    async def start(message: Message, bot: Bot):
        await db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        if not await gate(message, bot):
            return
        user = await db.get_user(message.from_user.id)
        if user["status"] == "approved":
            await message.answer("👋 VIP botga xush kelibsiz!", reply_markup=main_menu())
        else:
            await message.answer(f"Ro'yxatdan o'tishda <b>{settings.promo_code}</b> promo kodidan foydalaning.",
                                 reply_markup=registration_keyboard(settings.registration_url))

    @router.callback_query(F.data == "check_subscription")
    async def check(callback: CallbackQuery, bot: Bot):
        if await is_subscribed(bot, settings.channel_id, callback.from_user.id):
            await callback.message.answer(f"✅ Obuna tasdiqlandi. <b>{settings.promo_code}</b> promo kodi bilan ro'yxatdan o'ting.",
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
        await message.answer("⏳ Ariza adminga yuborildi. Natija bot orqali keladi.")
        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(admin_id, f"🆕 Yangi ariza\n{user_label(message.from_user)}\nPlayer ID: <code>{value}</code>\n/pending")
            except Exception:
                pass

    async def approved(message: Message, bot: Bot) -> bool:
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
        status = await message.answer("🔎 <b>VIP server signalni qidirmoqda...</b>")
        await bot.send_dice(message.chat.id, emoji="🎰")
        await asyncio.sleep(2.5)
        await status.edit_text("✅ <b>Signal topildi!</b>")
        await message.answer(format_signal(factory()))

    @router.message(F.text == "🍎 Apple signal")
    async def apple(message: Message, bot: Bot):
        await animated_signal(message, bot, apple_signal)

    @router.message(F.text == "🐔 Chicken Road signal")
    async def chicken(message: Message, bot: Bot):
        await animated_signal(message, bot, chicken_signal)

    @router.message(F.text == "🏆 Konkurs")
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

    @router.message(F.text == "📥 APK yuklab olish")
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

    @router.message(F.text == "🛟 Yordam")
    async def help_message(message: Message):
        await message.answer("Yordam uchun bot administratoriga murojaat qiling. Player ID va muammo tavsifini yuboring.")

    return router
