import asyncio
import html
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from config import Settings
from database import Database
from keyboards import (
    admin_home_menu, admin_menu, approval_keyboard, audience_keyboard,
    contest_keyboard,
)
from utils import animate_message, is_subscribed


class AdminState(StatesGroup):
    audience_ids = State()
    content = State()
    apk = State()
    support_reply = State()


FLOW_NAMES = {
    "advert": "📣 Reklama",
    "promo": "🎟 Promo",
    "freebet": "🎁 FreeBet",
    "contest": "🏆 Konkurs",
}


def create_admin_router(settings: Settings, db: Database) -> Router:
    router = Router(name="admin")

    def is_admin(user_id: int) -> bool:
        return user_id in settings.admin_ids

    async def open_panel(message: Message):
        await message.answer("🛠 <b>ADMIN PANEL</b>\nKerakli bo'limni tanlang:", reply_markup=admin_menu())

    async def show_pending(message: Message):
        rows = await db.pending()
        if not rows:
            await message.answer("✅ Kutilayotgan ariza yo'q.")
            return
        for row in rows:
            await message.answer(
                f"👤 {row['full_name']}\n@{row['username'] or '-'}\n"
                f"Telegram ID: <code>{row['user_id']}</code>\nPlayer ID: <code>{row['player_id']}</code>\n"
                f"Minimal depozit: <b>{settings.min_deposit:,} so'm</b>".replace(",", " "),
                reply_markup=approval_keyboard(row["user_id"]),
            )

    async def show_stats(message: Message):
        total, grouped = await db.stats()
        contest = await db.active_contest()
        participants = await db.contest_count(contest["id"]) if contest else 0
        await message.answer(
            "📊 <b>STATISTIKA</b>\n\n"
            f"👥 Jami: {total}\n✅ Tasdiqlangan: {grouped.get('approved', 0)}\n"
            f"⏳ Kutilmoqda: {grouped.get('pending', 0)}\n❌ Rad etilgan: {grouped.get('rejected', 0)}\n"
            f"🏆 Konkurs ishtirokchilari: {participants}"
        )

    @router.message(CommandStart(), F.from_user.id.in_(settings.admin_ids))
    async def admin_start(message: Message, state: FSMContext):
        await state.clear()
        await message.answer_dice(emoji="🎰")
        await asyncio.sleep(1.4)
        await message.answer(
            "✨ <b>ADMIN REJIM FAOLLASHDI</b> ✨\nPastdagi «🛠 Admin panel» tugmasi doim ko'rinadi.",
            reply_markup=admin_home_menu(),
        )
        await open_panel(message)

    @router.message(Command("admin"), F.from_user.id.in_(settings.admin_ids))
    @router.message(F.text == "🛠 Admin panel", F.from_user.id.in_(settings.admin_ids))
    async def panel(message: Message, state: FSMContext):
        await state.clear()
        await open_panel(message)

    @router.callback_query(F.data == "admin:home")
    async def panel_callback(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        await state.clear()
        await callback.message.edit_text("🛠 <b>ADMIN PANEL</b>\nKerakli bo'limni tanlang:", reply_markup=admin_menu())
        await callback.answer()

    @router.message(Command("pending"), F.from_user.id.in_(settings.admin_ids))
    async def pending_cmd(message: Message):
        await show_pending(message)

    @router.message(Command("stats"), F.from_user.id.in_(settings.admin_ids))
    async def stats_cmd(message: Message):
        await show_stats(message)

    @router.callback_query(F.data == "admin:pending")
    async def pending_cb(callback: CallbackQuery):
        if is_admin(callback.from_user.id):
            await show_pending(callback.message)
            await callback.answer()

    @router.callback_query(F.data == "admin:stats")
    async def stats_cb(callback: CallbackQuery):
        if is_admin(callback.from_user.id):
            await show_stats(callback.message)
            await callback.answer()

    @router.callback_query(F.data.in_({"admin:advert", "admin:promo", "admin:freebet", "admin:contest"}))
    async def choose_audience(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        kind = callback.data.split(":", 1)[1]
        await state.clear()
        await state.update_data(kind=kind)
        await callback.message.answer(
            f"{FLOW_NAMES[kind]} kimlarga yuborilsin?",
            reply_markup=audience_keyboard(kind),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("audience:"))
    async def audience_selected(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        _, kind, choice = callback.data.split(":", 2)
        await state.clear()
        await state.update_data(kind=kind)
        if choice == "all":
            ids = await db.approved_ids()
            if not ids:
                await callback.answer("Tasdiqlangan foydalanuvchi yo'q", show_alert=True)
                return
            await state.update_data(audience=ids)
            await state.set_state(AdminState.content)
            await callback.message.answer(
                f"👥 {len(ids)} foydalanuvchi tanlandi.\nEndi yuboriladigan {FLOW_NAMES[kind].lower()} xabarini jo'nating."
            )
        else:
            await state.set_state(AdminState.audience_ids)
            await callback.message.answer(
                "🎯 Telegram ID'larni vergul bilan yozing:\n<code>123456789, 987654321</code>"
            )
        await callback.answer()

    @router.message(AdminState.audience_ids)
    async def receive_ids(message: Message, state: FSMContext):
        try:
            requested = {int(item.strip()) for item in (message.text or "").split(",") if item.strip()}
        except ValueError:
            requested = set()
        known = set(await db.all_ids())
        ids = sorted(requested & known)
        if not ids:
            await message.answer("❌ Mos foydalanuvchi topilmadi. ID'larni tekshirib qayta yozing.")
            return
        await state.update_data(audience=ids)
        await state.set_state(AdminState.content)
        data = await state.get_data()
        await message.answer(
            f"✅ {len(ids)} foydalanuvchi tanlandi.\nEndi yuboriladigan {FLOW_NAMES[data['kind']].lower()} xabarini jo'nating."
        )

    @router.message(AdminState.content)
    async def receive_content(message: Message, state: FSMContext, bot: Bot):
        data = await state.get_data()
        ids: list[int] = data.get("audience", [])
        kind = data.get("kind")
        if kind not in FLOW_NAMES or not ids:
            await state.clear()
            await message.answer("Jarayon bekor qilindi. Admin paneldan qayta boshlang.")
            return
        contest_id = None
        if kind == "contest":
            raw = message.text or message.caption or "Yangi konkurs"
            title = raw.splitlines()[0][:100]
            description = html.escape(raw)
            contest_id = await db.create_contest(title, description)
        progress = await animate_message(
            message,
            ["⏳ Yuborishga tayyorlanmoqda...", "⚡ Serverlar tekshirilmoqda...", "📤 Yuborish boshlandi..."],
            0.35,
        )
        ok = failed = 0
        for index, user_id in enumerate(ids, start=1):
            try:
                markup = contest_keyboard(contest_id) if contest_id else None
                await bot.copy_message(user_id, message.chat.id, message.message_id, reply_markup=markup)
                if kind == "freebet":
                    saved = (message.text or message.caption or "Admin yuborgan FreeBet")[:500]
                    await db.add_freebet(user_id, "FREEBET", saved)
                ok += 1
            except Exception:
                failed += 1
            if index % 20 == 0:
                await progress.edit_text(f"📤 Yuborilmoqda: {index}/{len(ids)}")
            await asyncio.sleep(0.045)
        await state.clear()
        await progress.edit_text(
            f"✅ <b>{FLOW_NAMES[kind]} yuborildi</b>\n\nYetib bordi: {ok}\nYetmadi: {failed}",
            reply_markup=admin_menu(),
        )

    @router.callback_query(F.data == "admin:contest_close")
    async def contest_close(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            return
        closed = await db.close_contest()
        await callback.answer("Konkurs yopildi" if closed else "Faol konkurs yo'q", show_alert=True)

    @router.callback_query(F.data == "admin:subscriptions")
    async def subscriptions(callback: CallbackQuery, bot: Bot):
        if not is_admin(callback.from_user.id):
            return
        await callback.answer("Tekshiruv boshlandi")
        progress = await callback.message.answer("🔍 Obunalar tekshirilmoqda... ░░░░░")
        ids = await db.all_ids()
        subscribed = unsubscribed = 0
        for index, user_id in enumerate(ids, start=1):
            if await is_subscribed(bot, settings.channel_id, user_id):
                subscribed += 1
            else:
                unsubscribed += 1
            if index % 20 == 0:
                await progress.edit_text(f"🔍 Tekshirildi: {index}/{len(ids)}")
            await asyncio.sleep(0.045)
        await progress.edit_text(
            f"🔍 <b>TEKSHIRUV TUGADI</b>\n\n✅ Obuna: {subscribed}\n❌ Obuna emas: {unsubscribed}",
            reply_markup=admin_menu(),
        )

    @router.callback_query(F.data == "admin:apk")
    async def apk_start(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        await state.clear()
        await state.set_state(AdminState.apk)
        await callback.message.answer(
            "📦 Yangi <b>.apk</b> faylni yuboring. Fayl saqlanadi va barcha tasdiqlanganlarga tarqatiladi."
        )
        await callback.answer()

    @router.message(AdminState.apk)
    async def apk_save(message: Message, state: FSMContext, bot: Bot):
        document = message.document
        if not document or not (document.file_name or "").lower().endswith(".apk"):
            await message.answer("❌ Faqat .apk fayl yuboring.")
            return
        status = await animate_message(
            message, ["📥 APK qabul qilinmoqda...", "💾 Fayl saqlanmoqda...", "✅ APK tayyor!"], 0.45
        )
        path = Path(settings.apk_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await bot.download(document, destination=path)
        ids = await db.approved_ids()
        ok = failed = 0
        for index, user_id in enumerate(ids, start=1):
            try:
                await bot.send_document(user_id, FSInputFile(path), caption="📦 <b>Luckypari APK yangi versiyasi</b>")
                ok += 1
            except Exception:
                failed += 1
            if index % 10 == 0:
                await status.edit_text(f"📤 APK yuborilmoqda: {index}/{len(ids)}")
            await asyncio.sleep(0.065)
        await state.clear()
        await status.edit_text(f"✅ APK yuborildi: {ok}\n❌ Yetmadi: {failed}", reply_markup=admin_menu())

    @router.callback_query(F.data.startswith("support_reply:"))
    async def support_reply_start(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        user_id = int(callback.data.split(":", 1)[1])
        await state.clear()
        await state.update_data(support_user_id=user_id)
        await state.set_state(AdminState.support_reply)
        await callback.message.answer(f"↩️ <code>{user_id}</code> foydalanuvchiga javobingizni yuboring:")
        await callback.answer()

    @router.message(AdminState.support_reply)
    async def support_reply_send(message: Message, state: FSMContext, bot: Bot):
        user_id = (await state.get_data()).get("support_user_id")
        try:
            await bot.send_message(user_id, "💬 <b>ADMIN JAVOBI</b>")
            await bot.copy_message(user_id, message.chat.id, message.message_id)
            await message.answer("✅ Javob foydalanuvchiga yuborildi.", reply_markup=admin_menu())
        except Exception:
            await message.answer("❌ Javobni yuborib bo'lmadi.", reply_markup=admin_menu())
        await state.clear()

    @router.callback_query(F.data.startswith(("approve:", "reject:")))
    async def decide(callback: CallbackQuery, bot: Bot):
        if not is_admin(callback.from_user.id):
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return
        action, raw_id = callback.data.split(":", 1)
        user_id = int(raw_id)
        status = "approved" if action == "approve" else "rejected"
        if not await db.set_status(user_id, status):
            await callback.answer("Foydalanuvchi topilmadi", show_alert=True)
            return
        text = "✅ Arizangiz tasdiqlandi. /start ni bosing." if status == "approved" else "❌ Arizangiz rad etildi."
        try:
            await bot.send_message(user_id, text)
        except Exception:
            pass
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Saqlandi")

    return router
