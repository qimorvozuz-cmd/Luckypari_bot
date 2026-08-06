from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import Settings
from database import Database
from keyboards import approval_keyboard


def create_admin_router(settings: Settings, db: Database) -> Router:
    router = Router(name="admin")

    def admin(user_id: int) -> bool:
        return user_id in settings.admin_ids

    @router.message(Command("admin"))
    async def panel(message: Message):
        if not admin(message.from_user.id):
            return
        await message.answer("🛠 Admin panel\n/pending — arizalar\n/stats — statistika")

    @router.message(Command("pending"))
    async def pending(message: Message):
        if not admin(message.from_user.id):
            return
        rows = await db.pending()
        if not rows:
            await message.answer("Kutilayotgan ariza yo'q.")
        for row in rows:
            await message.answer(
                f"👤 {row['full_name']}\n@{row['username'] or '-'}\nTelegram ID: <code>{row['user_id']}</code>\n"
                f"Player ID: <code>{row['player_id']}</code>", reply_markup=approval_keyboard(row["user_id"])
            )

    @router.message(Command("stats"))
    async def stats(message: Message):
        if not admin(message.from_user.id):
            return
        total, grouped = await db.stats()
        await message.answer(f"📊 Jami: {total}\n✅ Tasdiqlangan: {grouped.get('approved', 0)}\n"
                             f"⏳ Kutilmoqda: {grouped.get('pending', 0)}\n❌ Rad etilgan: {grouped.get('rejected', 0)}")

    @router.callback_query(F.data.startswith(("approve:", "reject:")))
    async def decide(callback: CallbackQuery, bot: Bot):
        if not admin(callback.from_user.id):
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return
        action, raw_id = callback.data.split(":", 1)
        user_id = int(raw_id)
        status = "approved" if action == "approve" else "rejected"
        if not await db.set_status(user_id, status):
            await callback.answer("Foydalanuvchi topilmadi", show_alert=True)
            return
        text = "✅ Arizangiz tasdiqlandi. VIP menyudan foydalanishingiz mumkin." if status == "approved" else "❌ Arizangiz rad etildi. Yordam bo'limi orqali bog'laning."
        try:
            await bot.send_message(user_id, text)
        except Exception:
            pass
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Saqlandi")

    return router
