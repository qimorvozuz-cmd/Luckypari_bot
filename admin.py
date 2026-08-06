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
    bonus_paid_keyboard, contest_keyboard, join_keyboard, subscription_keyboard,
    user_manage_keyboard,
)
from utils import animate_message, is_subscribed


class AdminState(StatesGroup):
    audience_ids = State()
    content = State()
    user_search = State()
    apk = State()
    support_reply = State()


FLOW_NAMES = {
    "message": "💬 Xabar", "advert": "📣 Reklama", "promo": "🎟 Promo-kod",
    "freebet": "🎁 FreeBet", "contest": "🏆 Konkurs", "daily": "📅 Kunlik stavka",
    "high_odds": "🔥 Yuqori koeffitsiyent", "casino": "🧠 Casino tahlili",
    "report": "📈 MEGA hisobot", "join_request": "➕ Kanal/guruh taklifi",
}

CONTENT_PROMPTS = {
    "freebet": "FreeBetni <code>KOD | Batafsil izoh</code> ko'rinishida yuboring.",
    "contest": "Birinchi qatorda konkurs nomi, keyingi qatorlarda shartlari va mukofotini yozing.",
    "join_request": "<code>Tugma nomi | https://t.me/havola | Xabar matni</code> ko'rinishida yozing.",
    "promo": "Promo-kod va batafsil izohni yuboring. Format va premium emojilar saqlanadi.",
}


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def content_body(message: Message) -> str:
    return message.html_text if (message.text or message.caption) else "Media xabar"


def create_admin_router(settings: Settings, db: Database) -> Router:
    router = Router(name="admin")

    def is_admin(user_id: int) -> bool:
        return user_id in settings.admin_ids

    async def open_panel(message: Message):
        await message.answer("🛠 <b>PRO ADMIN PANEL</b>\nBarcha bo'limlar shu yerdan boshqariladi:", reply_markup=admin_menu())

    async def user_card(user, bot: Bot) -> tuple[str, bool]:
        subscribed = await is_subscribed(bot, settings.channel_id, user["user_id"])
        tier = {"vip": "💎 VIP", "mega": "👑 MEGA VIP", "none": "➖ Yo'q"}.get(user["tier"], user["tier"])
        card = (
            "👤 <b>FOYDALANUVCHI KARTASI</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"Ism: <b>{user['full_name']}</b>\nUsername: @{user['username'] or '-'}\n"
            f"Telegram ID: <code>{user['user_id']}</code>\nPlayer ID: <code>{user['player_id'] or '-'}</code>\n"
            f"Daraja: <b>{tier}</b>\nSo'ralgan: <b>{str(user['requested_tier']).upper()}</b>\n"
            f"Holat: <b>{user['status']}</b>\nKanal: {'✅ Obuna' if subscribed else '❌ Obuna emas'}\n"
            f"Referal egasi: <code>{user['referred_by'] or '-'}</code>\n"
            f"Referal bonusi: <b>{money(user['bonus_balance'])} so'm</b>\n"
            f"Blok: {'🚫 Ha' if user['is_blocked'] else '✅ Yo‘q'}"
        )
        return card, subscribed

    async def show_pending(message: Message):
        rows = await db.pending()
        if not rows:
            await message.answer("✅ Kutilayotgan ariza yo'q.")
            return
        for user in rows:
            deposit = settings.mega_deposit if user["requested_tier"] == "mega" else settings.vip_deposit
            await message.answer(
                "🆕 <b>TEKSHIRUV JADVALI</b>\n━━━━━━━━━━━━━━━━━━\n"
                f"👤 {user['full_name']}\n🔗 @{user['username'] or '-'}\n"
                f"🆔 TG: <code>{user['user_id']}</code>\n🎮 Player: <code>{user['player_id']}</code>\n"
                f"💠 Bo'lim: <b>{str(user['requested_tier']).upper()}</b>\n"
                f"💳 Talab: <b>{money(deposit)} so'm</b>\n👥 Referal: <code>{user['referred_by'] or '-'}</code>\n"
                "━━━━━━━━━━━━━━━━━━",
                reply_markup=approval_keyboard(user["user_id"]),
            )

    async def show_stats(message: Message):
        total, grouped, tiers, referrals = await db.stats()
        await message.answer(
            "📊 <b>UMUMIY STATISTIKA</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"👥 Jami: {total}\n✅ Tasdiqlangan: {grouped.get('approved', 0)}\n"
            f"⏳ Arizalar: {grouped.get('pending', 0)}\n❌ Rad: {grouped.get('rejected', 0)}\n"
            f"💎 VIP: {tiers.get('vip', 0)}\n👑 MEGA VIP: {tiers.get('mega', 0)}\n"
            f"🔗 Tasdiqlangan referallar: {referrals}"
        )

    @router.message(CommandStart(), F.from_user.id.in_(settings.admin_ids))
    async def admin_start(message: Message, state: FSMContext):
        await state.clear()
        await message.answer_dice(emoji="🎰")
        await asyncio.sleep(1.3)
        await message.answer(
            "✨ <b>PRO ADMIN REJIMI FAOL</b> ✨\nPastdagi tugma orqali panelni istalgan payt oching.",
            reply_markup=admin_home_menu(),
        )
        await open_panel(message)

    @router.message(Command("admin"), F.from_user.id.in_(settings.admin_ids))
    @router.message(F.text == "🛠 Admin panel", F.from_user.id.in_(settings.admin_ids))
    async def panel(message: Message, state: FSMContext):
        await state.clear()
        await open_panel(message)

    @router.message(Command("pending"), F.from_user.id.in_(settings.admin_ids))
    async def pending_command(message: Message):
        await show_pending(message)

    @router.message(Command("stats"), F.from_user.id.in_(settings.admin_ids))
    async def stats_command(message: Message):
        await show_stats(message)

    @router.callback_query(F.data == "admin:home")
    async def home(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        await state.clear()
        await callback.message.edit_text("🛠 <b>PRO ADMIN PANEL</b>", reply_markup=admin_menu())
        await callback.answer()

    @router.callback_query(F.data == "admin:pending")
    async def pending(callback: CallbackQuery):
        if is_admin(callback.from_user.id):
            await show_pending(callback.message)
            await callback.answer()

    @router.callback_query(F.data == "admin:stats")
    async def stats(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            return
        await show_stats(callback.message)
        await callback.answer()

    @router.callback_query(F.data == "admin:users")
    async def users_start(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        await state.set_state(AdminState.user_search)
        await callback.message.answer("🔎 Tekshiriladigan foydalanuvchining Telegram ID raqamini yuboring:")
        await callback.answer()

    @router.message(AdminState.user_search)
    async def user_search(message: Message, state: FSMContext, bot: Bot):
        raw = (message.text or "").strip()
        if not raw.isdigit():
            await message.answer("Faqat Telegram ID raqamini yuboring.")
            return
        user = await db.get_user(int(raw))
        if not user:
            await message.answer("❌ Foydalanuvchi topilmadi.")
            return
        await state.clear()
        card, _ = await user_card(user, bot)
        await message.answer(card, reply_markup=user_manage_keyboard(user["user_id"], bool(user["is_blocked"])))

    @router.callback_query(F.data.startswith("user:"))
    async def user_details(callback: CallbackQuery, bot: Bot):
        if not is_admin(callback.from_user.id):
            return
        user = await db.get_user(int(callback.data.split(":", 1)[1]))
        if not user:
            await callback.answer("Topilmadi", show_alert=True)
            return
        card, _ = await user_card(user, bot)
        await callback.message.answer(card, reply_markup=user_manage_keyboard(user["user_id"], bool(user["is_blocked"])))
        await callback.answer()

    @router.callback_query(F.data.startswith("tier:"))
    async def set_tier(callback: CallbackQuery, bot: Bot):
        if not is_admin(callback.from_user.id):
            return
        _, tier, raw_id = callback.data.split(":", 2)
        user_id = int(raw_id)
        if await db.set_tier(user_id, tier):
            label = {"vip": "💎 VIP", "mega": "👑 MEGA VIP", "none": "bekor qilindi"}[tier]
            try:
                await bot.send_message(user_id, f"🔔 Darajangiz yangilandi: <b>{label}</b>. /start ni bosing.")
            except Exception:
                pass
            await callback.answer("Saqlandi", show_alert=True)

    @router.callback_query(F.data.startswith("block:"))
    async def block_user(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            return
        _, flag, raw_id = callback.data.split(":", 2)
        await db.set_blocked(int(raw_id), flag == "1")
        await callback.answer("Holat yangilandi", show_alert=True)

    @router.callback_query(F.data.startswith("direct:"))
    async def direct(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        user_id = int(callback.data.split(":", 1)[1])
        await state.clear()
        await state.update_data(kind="message", audience=[user_id], audience_name="SELECTED")
        await state.set_state(AdminState.content)
        await callback.message.answer(f"✉️ <code>{user_id}</code> uchun xabarni yuboring:")
        await callback.answer()

    @router.callback_query(F.data.in_({
        "admin:message", "admin:advert", "admin:promo", "admin:freebet", "admin:contest",
        "admin:daily", "admin:high_odds", "admin:casino", "admin:report", "admin:join_request",
    }))
    async def flow_start(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        kind = callback.data.split(":", 1)[1]
        await state.clear()
        await state.update_data(kind=kind)
        await callback.message.answer(f"{FLOW_NAMES[kind]} kimlarga yuborilsin?", reply_markup=audience_keyboard(kind))
        await callback.answer()

    @router.callback_query(F.data.startswith("aud:"))
    async def audience(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        _, kind, choice = callback.data.split(":", 2)
        await state.clear()
        await state.update_data(kind=kind, audience_name=choice)
        if choice == "SELECTED":
            await state.set_state(AdminState.audience_ids)
            await callback.message.answer("🎯 Telegram ID'larni vergul bilan yozing:\n<code>123456, 987654</code>")
        else:
            ids = await db.audience_ids(choice)
            if not ids:
                await callback.answer("Bu auditoriyada foydalanuvchi yo'q", show_alert=True)
                return
            await state.update_data(audience=ids)
            await state.set_state(AdminState.content)
            prompt = CONTENT_PROMPTS.get(kind, "Endi yuboriladigan xabar, rasm, video yoki faylni jo'nating.")
            await callback.message.answer(f"✅ {len(ids)} foydalanuvchi tanlandi.\n{prompt}")
        await callback.answer()

    @router.message(AdminState.audience_ids)
    async def audience_ids(message: Message, state: FSMContext):
        try:
            requested = {int(x.strip()) for x in (message.text or "").split(",") if x.strip()}
        except ValueError:
            requested = set()
        known = set(await db.all_ids())
        ids = sorted(requested & known)
        if not ids:
            await message.answer("❌ ID topilmadi. Raqamlarni vergul bilan qayta yozing.")
            return
        await state.update_data(audience=ids)
        await state.set_state(AdminState.content)
        kind = (await state.get_data())["kind"]
        await message.answer(f"✅ {len(ids)} foydalanuvchi tanlandi.\n{CONTENT_PROMPTS.get(kind, 'Endi xabarni yuboring.')}")

    @router.message(AdminState.content)
    async def publish(message: Message, state: FSMContext, bot: Bot):
        data = await state.get_data()
        kind, ids = data.get("kind"), data.get("audience", [])
        audience_name = data.get("audience_name", "SELECTED")
        if kind not in FLOW_NAMES or not ids:
            await state.clear()
            await message.answer("Jarayon bekor qilindi. Qayta boshlang.", reply_markup=admin_home_menu())
            return
        body = content_body(message)
        contest_id = None
        freebet_code = None
        join_data = None
        if kind == "contest":
            raw = message.text or message.caption or "Yangi konkurs"
            title = html.escape(raw.splitlines()[0][:100])
            contest_id = await db.create_contest(title, body, audience_name)
            if audience_name == "SELECTED":
                await db.set_contest_targets(contest_id, ids)
        elif kind == "join_request":
            parts = [x.strip() for x in (message.text or "").split("|", 2)]
            if len(parts) != 3 or not parts[1].startswith(("https://", "http://")):
                await message.answer("❌ Format: <code>Tugma nomi | https://havola | Xabar</code>")
                return
            join_data = parts
            content_id = await db.add_content(kind, audience_name, html.escape(parts[0]), html.escape(parts[2]))
            if audience_name == "SELECTED":
                await db.set_content_targets(content_id, ids)
        elif kind == "freebet":
            parts = [x.strip() for x in (message.text or "").split("|", 1)]
            freebet_code = parts[0][:100] if parts else "FREEBET"
            body = message.html_text if message.text else body
        elif kind in {"promo", "daily", "high_odds", "casino", "report"}:
            content_id = await db.add_content(kind, audience_name, FLOW_NAMES[kind], body)
            if audience_name == "SELECTED":
                await db.set_content_targets(content_id, ids)
        progress = await animate_message(
            message, ["🔐 Auditoriya tayyorlanmoqda...", "⚡ Premium yuborish serveri ishga tushdi...", "📤 Xabarlar yuborilmoqda..."], 0.4
        )
        ok = failed = 0
        for index, user_id in enumerate(ids, start=1):
            try:
                if kind == "contest":
                    await bot.send_message(user_id, f"🏆 <b>KONKURS BOSHLANDI!</b>\n\n{body}", reply_markup=contest_keyboard(contest_id))
                elif kind == "join_request":
                    await bot.send_message(user_id, f"➕ <b>YANGI TAKLIF</b>\n\n{html.escape(join_data[2])}", reply_markup=join_keyboard(join_data[0], join_data[1]))
                elif kind == "freebet":
                    await db.add_freebet(user_id, freebet_code, body)
                    await bot.send_message(user_id, f"🎁 <b>YANGI FREEBET</b>\n\n{body}")
                elif kind in {"promo", "daily", "high_odds", "casino", "report"} and message.text:
                    await bot.send_message(user_id, f"{FLOW_NAMES[kind]}\n\n{body}")
                else:
                    await bot.copy_message(user_id, message.chat.id, message.message_id)
                ok += 1
            except Exception:
                failed += 1
            if index % 20 == 0:
                await progress.edit_text(f"📤 Yuborildi: {index}/{len(ids)}")
            await asyncio.sleep(0.045)
        await state.clear()
        await progress.edit_text(f"✅ <b>{FLOW_NAMES[kind]} yakunlandi</b>\nYetib bordi: {ok}\nYetmadi: {failed}", reply_markup=admin_menu())

    @router.callback_query(F.data == "admin:contest_close")
    async def close_contests(callback: CallbackQuery):
        if is_admin(callback.from_user.id):
            count = await db.close_contests()
            await callback.answer(f"Yopildi: {count}", show_alert=True)

    @router.callback_query(F.data == "admin:subscriptions")
    async def check_subscriptions(callback: CallbackQuery, bot: Bot):
        if not is_admin(callback.from_user.id):
            return
        await callback.answer("Tekshiruv boshlandi")
        progress = await callback.message.answer("🔍 Obunalar tekshirilmoqda... ░░░░░")
        ids = await db.all_ids()
        yes = no = notified = 0
        for index, user_id in enumerate(ids, start=1):
            if await is_subscribed(bot, settings.channel_id, user_id):
                yes += 1
            else:
                no += 1
                try:
                    await bot.send_message(user_id, "⚠️ VIP kirishni saqlash uchun kanalga qayta obuna bo'ling.", reply_markup=subscription_keyboard(settings.channel_url))
                    notified += 1
                except Exception:
                    pass
            if index % 20 == 0:
                await progress.edit_text(f"🔍 Tekshirildi: {index}/{len(ids)}")
            await asyncio.sleep(0.045)
        await progress.edit_text(f"✅ Obuna: {yes}\n❌ Obuna emas: {no}\n📨 Ogohlantirildi: {notified}", reply_markup=admin_menu())

    @router.callback_query(F.data == "admin:referrals")
    async def referral_bonuses(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            return
        rows = await db.bonus_users()
        if not rows:
            await callback.answer("To'lov navbatida bonus yo'q", show_alert=True)
            return
        for user in rows:
            await callback.message.answer(
                f"💰 <b>REFERAL BONUS TO'LOVI</b>\n👤 {user['full_name']}\n"
                f"TG ID: <code>{user['user_id']}</code>\nPlayer ID: <code>{user['player_id'] or '-'}</code>\n"
                f"Summa: <b>{money(user['bonus_balance'])} so'm</b>",
                reply_markup=bonus_paid_keyboard(user["user_id"]),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("bonus_paid:"))
    async def bonus_paid(callback: CallbackQuery, bot: Bot):
        if not is_admin(callback.from_user.id):
            return
        user_id = int(callback.data.split(":", 1)[1])
        amount = await db.clear_bonus(user_id)
        try:
            await bot.send_message(user_id, f"✅ <b>{money(amount)} so'm</b> referal bonusingiz admin tomonidan to'langan deb belgilandi.")
        except Exception:
            pass
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("To'landi deb belgilandi")

    @router.callback_query(F.data == "admin:apk")
    async def apk_start(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        await state.clear()
        await state.set_state(AdminState.apk)
        await callback.message.answer("📦 Yangi .apk faylni yuboring. U saqlanib barcha VIP va MEGA VIP foydalanuvchilarga tarqatiladi.")
        await callback.answer()

    @router.message(AdminState.apk)
    async def apk_save(message: Message, state: FSMContext, bot: Bot):
        if not message.document or not (message.document.file_name or "").lower().endswith(".apk"):
            await message.answer("❌ Faqat .apk fayl yuboring.")
            return
        progress = await animate_message(message, ["📥 APK olinmoqda...", "🔐 Tekshirilmoqda...", "💾 Saqlanmoqda..."], 0.45)
        path = Path(settings.apk_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await bot.download(message.document, destination=path)
        ids = await db.audience_ids("ALL")
        ok = failed = 0
        for index, user_id in enumerate(ids, start=1):
            try:
                await bot.send_document(user_id, FSInputFile(path), caption="📦 <b>Luckypari APK yangi versiyasi</b>")
                ok += 1
            except Exception:
                failed += 1
            if index % 10 == 0:
                await progress.edit_text(f"📤 APK: {index}/{len(ids)}")
            await asyncio.sleep(0.065)
        await state.clear()
        await progress.edit_text(f"✅ APK yuborildi: {ok}\n❌ Yetmadi: {failed}", reply_markup=admin_menu())

    @router.callback_query(F.data.startswith("support_reply:"))
    async def support_reply(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            return
        user_id = int(callback.data.split(":", 1)[1])
        await state.clear()
        await state.update_data(support_user_id=user_id)
        await state.set_state(AdminState.support_reply)
        await callback.message.answer(f"↩️ <code>{user_id}</code> foydalanuvchiga javobni yuboring:")
        await callback.answer()

    @router.message(AdminState.support_reply)
    async def support_send(message: Message, state: FSMContext, bot: Bot):
        user_id = (await state.get_data()).get("support_user_id")
        try:
            await bot.send_message(user_id, "💬 <b>ADMIN JAVOBI</b>")
            await bot.copy_message(user_id, message.chat.id, message.message_id)
            await message.answer("✅ Javob yuborildi.", reply_markup=admin_home_menu())
        except Exception:
            await message.answer("❌ Javob yuborilmadi.")
        await state.clear()

    @router.callback_query(F.data.startswith(("approve:", "reject:")))
    async def application_decision(callback: CallbackQuery, bot: Bot):
        if not is_admin(callback.from_user.id):
            return
        action, raw_id = callback.data.split(":", 1)
        user_id = int(raw_id)
        if action == "approve":
            tier, referrer_id = await db.approve_application(user_id)
            if not tier:
                await callback.answer("Foydalanuvchi topilmadi", show_alert=True)
                return
            try:
                await bot.send_message(user_id, f"✅ Arizangiz tasdiqlandi! Daraja: <b>{tier.upper()}</b>. /start ni bosing.")
            except Exception:
                pass
            if referrer_id:
                try:
                    await bot.send_message(
                        referrer_id,
                        f"🎉 Referalingiz tasdiqlandi! <b>{money(settings.referral_reward)} so'm</b> bonus to'lov navbatiga qo'shildi."
                    )
                except Exception:
                    pass
                for admin_id in settings.admin_ids:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"💰 Referal bonusi: <code>{referrer_id}</code> foydalanuvchiga "
                            f"<b>{money(settings.referral_reward)} so'm</b> to'lov navbatiga qo'shildi."
                        )
                    except Exception:
                        pass
            result = f"✅ {tier.upper()} tasdiqlandi"
        else:
            await db.reject_application(user_id)
            try:
                await bot.send_message(user_id, "❌ Arizangiz rad etildi. Yordam bo'limi orqali adminga yozishingiz mumkin.")
            except Exception:
                pass
            result = "❌ Ariza rad etildi"
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer(result, show_alert=True)

    return router
