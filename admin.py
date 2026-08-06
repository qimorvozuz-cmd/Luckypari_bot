import asyncio
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from config import Settings
from database import Database
from keyboards import admin_menu, approval_keyboard
from utils import is_subscribed


class AdminState(StatesGroup):
    contest = State()
    freebet = State()
    advert = State()
    promo = State()
    apk = State()


async def send_many(bot: Bot, ids: list[int], text: str) -> tuple[int, int]:
    ok = failed = 0
    for user_id in ids:
        try:
            await bot.send_message(user_id, text)
            ok += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.04)
    return ok, failed


def parse_audience(value: str, approved: list[int]) -> list[int]:
    value = value.strip()
    if value.upper() == "ALL":
        return approved
    try:
        requested = {int(item.strip()) for item in value.split(",") if item.strip()}
    except ValueError:
        return []
    return [user_id for user_id in approved if user_id in requested]


def create_admin_router(settings: Settings, db: Database) -> Router:
    router = Router(name="admin")

    def is_admin(user_id: int) -> bool:
        return user_id in settings.admin_ids

    async def show_pending(message: Message):
        rows = await db.pending()
        if not rows:
            await message.answer("Kutilayotgan ariza yo'q.")
        for row in rows:
            await message.answer(
                f"👤 {row['full_name']}\n@{row['username'] or '-'}\nTelegram ID: <code>{row['user_id']}</code>\n"
                f"Player ID: <code>{row['player_id']}</code>", reply_markup=approval_keyboard(row["user_id"])
            )

    async def show_stats(message: Message):
        total, grouped = await db.stats()
        contest = await db.active_contest()
        participants = await db.contest_count(contest["id"]) if contest else 0
        await message.answer(f"📊 <b>Statistika</b>\n\nJami: {total}\n✅ Tasdiqlangan: {grouped.get('approved', 0)}\n"
                             f"⏳ Kutilmoqda: {grouped.get('pending', 0)}\n❌ Rad etilgan: {grouped.get('rejected', 0)}\n"
                             f"🏆 Konkurs ishtirokchilari: {participants}")

    @router.message(CommandStart(), F.from_user.id.in_(settings.admin_ids))
    async def admin_start(message: Message):
        await message.answer_dice(emoji="🎰")
        await asyncio.sleep(1.5)
        await message.answer("🛠 <b>ADMIN PANEL</b>\nBot boshqaruviga xush kelibsiz!", reply_markup=admin_menu())

    @router.message(Command("admin"))
    async def panel(message: Message):
        if is_admin(message.from_user.id):
            await message.answer("🛠 <b>ADMIN PANEL</b>\nKerakli bo'limni tanlang:", reply_markup=admin_menu())

    @router.message(Command("pending"))
    async def pending_cmd(message: Message):
        if is_admin(message.from_user.id):
            await show_pending(message)

    @router.message(Command("stats"))
    async def stats_cmd(message: Message):
        if is_admin(message.from_user.id):
            await show_stats(message)

    @router.callback_query(F.data == "admin:pending")
    async def pending_cb(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            return
        await show_pending(callback.message)
        await callback.answer()

    @router.callback_query(F.data == "admin:stats")
    async def stats_cb(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            return
        await show_stats(callback.message)
        await callback.answer()

    @router.callback_query(F.data == "admin:contest")
    async def contest_start(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        await state.set_state(AdminState.contest)
        await callback.message.answer("Konkursni bitta xabarda yuboring:\n<code>Nomi | Shartlari va mukofoti</code>")
        await callback.answer()

    @router.message(AdminState.contest)
    async def contest_save(message: Message, state: FSMContext, bot: Bot):
        if not is_admin(message.from_user.id):
            return
        if "|" not in (message.text or ""):
            await message.answer("Format xato. Masalan: <code>Haftalik konkurs | 3 g'olibga FreeBet</code>")
            return
        title, description = [x.strip() for x in message.text.split("|", 1)]
        contest_id = await db.create_contest(title, description)
        await state.clear()
        ids = await db.approved_ids()
        from keyboards import contest_keyboard
        ok = 0
        for user_id in ids:
            try:
                await bot.send_message(user_id, f"🏆 <b>{title}</b>\n\n{description}", reply_markup=contest_keyboard(contest_id))
                ok += 1
            except Exception:
                pass
            await asyncio.sleep(0.04)
        await message.answer(f"✅ Konkurs yaratildi va {ok} foydalanuvchiga yuborildi.", reply_markup=admin_menu())

    @router.callback_query(F.data == "admin:contest_close")
    async def contest_close(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            return
        closed = await db.close_contest()
        await callback.answer("Konkurs yopildi" if closed else "Faol konkurs yo'q", show_alert=True)

    @router.callback_query(F.data == "admin:advert")
    async def advert_start(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        await state.set_state(AdminState.advert)
        await callback.message.answer(
            "📣 <b>Reklama yuborish</b>\n\nHammaga: <code>ALL | Reklama matni</code>\n"
            "Tanlanganlarga: <code>123456,789012 | Reklama matni</code>"
        )
        await callback.answer()

    @router.message(AdminState.advert)
    async def advert_send(message: Message, state: FSMContext, bot: Bot):
        if not is_admin(message.from_user.id):
            return
        if "|" not in (message.text or ""):
            await message.answer("Format xato. Auditoriya va matn orasiga | qo'ying.")
            return
        audience, content = [part.strip() for part in message.html_text.split("|", 1)]
        ids = parse_audience(audience, await db.approved_ids())
        if not ids:
            await message.answer("Foydalanuvchi topilmadi yoki ID noto'g'ri.")
            return
        ok, failed = await send_many(bot, ids, f"📣 <b>REKLAMA</b>\n\n{content}")
        await state.clear()
        await message.answer(f"✅ Yuborildi: {ok}\n❌ Yetmadi: {failed}", reply_markup=admin_menu())

    @router.callback_query(F.data == "admin:promo")
    async def promo_start(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        await state.set_state(AdminState.promo)
        await callback.message.answer(
            "🎟 <b>Promo yuborish</b>\n\nHammaga: <code>ALL | PROMOKOD | Izoh</code>\n"
            "Tanlanganlarga: <code>123456,789012 | PROMOKOD | Izoh</code>"
        )
        await callback.answer()

    @router.message(AdminState.promo)
    async def promo_send(message: Message, state: FSMContext, bot: Bot):
        if not is_admin(message.from_user.id):
            return
        parts = [part.strip() for part in (message.text or "").split("|", 2)]
        if len(parts) != 3:
            await message.answer("Format xato: <code>ALL | PROMOKOD | Izoh</code>")
            return
        ids = parse_audience(parts[0], await db.approved_ids())
        if not ids:
            await message.answer("Foydalanuvchi topilmadi yoki ID noto'g'ri.")
            return
        ok, failed = await send_many(bot, ids, f"🎟 <b>YANGI PROMO</b>\n\nKod: <code>{parts[1]}</code>\n{parts[2]}")
        await state.clear()
        await message.answer(f"✅ Yuborildi: {ok}\n❌ Yetmadi: {failed}", reply_markup=admin_menu())

    @router.callback_query(F.data == "admin:freebet")
    async def freebet_start(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        await state.set_state(AdminState.freebet)
        await callback.message.answer("🎁 <b>FreeBet yuborish</b>\n\nHammaga: <code>ALL | KOD | Izoh</code>\n"
                                      "Tanlanganlarga: <code>123456,789012 | KOD | Izoh</code>")
        await callback.answer()

    @router.message(AdminState.freebet)
    async def freebet_save(message: Message, state: FSMContext, bot: Bot):
        if not is_admin(message.from_user.id):
            return
        parts = [x.strip() for x in (message.text or "").split("|", 2)]
        if len(parts) != 3:
            await message.answer("Format xato: <code>ALL | KOD | Izoh</code>")
            return
        ids = parse_audience(parts[0], await db.approved_ids())
        if not ids:
            await message.answer("Foydalanuvchi topilmadi yoki ID noto'g'ri.")
            return
        for user_id in ids:
            await db.add_freebet(user_id, parts[1], parts[2])
        ok, failed = await send_many(bot, ids, f"🎁 <b>Sizga FreeBet berildi!</b>\n\nKod: <code>{parts[1]}</code>\n{parts[2]}")
        await state.clear()
        await message.answer(f"✅ Yuborildi: {ok}\n❌ Yetmadi: {failed}", reply_markup=admin_menu())

    @router.callback_query(F.data == "admin:subscriptions")
    async def subscriptions(callback: CallbackQuery, bot: Bot):
        if not is_admin(callback.from_user.id):
            return
        await callback.answer("Tekshiruv boshlandi")
        progress = await callback.message.answer("🔍 Obunalar tekshirilmoqda...")
        subscribed = unsubscribed = 0
        for user_id in await db.all_ids():
            if await is_subscribed(bot, settings.channel_id, user_id):
                subscribed += 1
            else:
                unsubscribed += 1
            await asyncio.sleep(0.04)
        await progress.edit_text(f"🔍 <b>Obuna tekshiruvi tugadi</b>\n\n✅ Obuna: {subscribed}\n❌ Obuna emas: {unsubscribed}")

    @router.callback_query(F.data == "admin:apk")
    async def apk_start(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        await state.set_state(AdminState.apk)
        await callback.message.answer("📦 Yangi <b>.apk</b> faylni shu yerga yuboring. U saqlanib, barcha tasdiqlanganlarga tarqatiladi.")
        await callback.answer()

    @router.message(AdminState.apk)
    async def apk_save(message: Message, state: FSMContext, bot: Bot):
        if not is_admin(message.from_user.id):
            return
        document = message.document
        if not document or not (document.file_name or "").lower().endswith(".apk"):
            await message.answer("Faqat .apk fayl yuboring.")
            return
        path = Path(settings.apk_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await bot.download(document, destination=path)
        ids = await db.approved_ids()
        ok = failed = 0
        status = await message.answer("📤 APK foydalanuvchilarga yuborilmoqda...")
        for user_id in ids:
            try:
                await bot.send_document(user_id, FSInputFile(path), caption="📦 Yangi APK versiyasi")
                ok += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.06)
        await state.clear()
        await status.edit_text(f"✅ APK saqlandi va yuborildi: {ok}\n❌ Yetmadi: {failed}", reply_markup=admin_menu())

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
