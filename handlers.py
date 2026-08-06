import asyncio
import time
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from config import Settings
from database import Database
from keyboards import (
    approval_keyboard, contest_keyboard, membership_keyboard, subscription_keyboard,
    support_reply_keyboard, user_menu,
)
from signals import (
    apple_signal, aviator_signal, chicken_signal, format_signal, luckyjet_signal,
    mines_signal,
)
from utils import animate_message, is_subscribed, user_label


class Registration(StatesGroup):
    player_id = State()


class Support(StatesGroup):
    message = State()


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def create_user_router(settings: Settings, db: Database) -> Router:
    router = Router(name="users")
    cooldowns: dict[int, float] = {}

    async def gate(message: Message, bot: Bot) -> bool:
        if not await is_subscribed(bot, settings.channel_id, message.from_user.id):
            await message.answer(
                "🔐 <b>Majburiy obuna</b>\nBotdan foydalanish uchun asosiy kanalga qo'shiling.",
                reply_markup=subscription_keyboard(settings.channel_url),
            )
            return False
        return True

    async def access(message: Message, bot: Bot, mega: bool = False):
        if message.from_user.id in settings.admin_ids:
            return "mega"
        if not await gate(message, bot):
            return None
        user = await db.get_user(message.from_user.id)
        if not user or user["status"] != "approved" or user["is_blocked"]:
            await message.answer(
                "🔒 VIP kirish hali faollashtirilmagan. Darajani tanlab Player ID yuboring.",
                reply_markup=membership_keyboard(settings.registration_url),
            )
            return None
        if mega and user["tier"] != "mega":
            await message.answer(
                f"👑 Bu bo'lim faqat <b>MEGA VIP</b> uchun.\n"
                f"Talab: bizning havoladan ro'yxatdan o'tish va {money(settings.mega_deposit)} so'm depozit.",
                reply_markup=membership_keyboard(settings.registration_url),
            )
            return None
        return user["tier"]

    async def show_registration(message: Message):
        await message.answer(
            "💎 <b>VIP</b>\n"
            f"• Minimal depozit: <b>{money(settings.vip_deposit)} so'm</b>\n"
            "• VIP signallar, kunlik stavkalar, konkurs va bonuslar\n\n"
            "👑 <b>MEGA VIP</b>\n"
            f"• Minimal depozit: <b>{money(settings.mega_deposit)} so'm</b>\n"
            "• VIP imkoniyatlari + yuqori koeffitsiyent, casino tahlillari, MEGA hisobotlar\n"
            "• Ko'proq maxsus konkurs va FreeBetlar\n\n"
            f"🎟 Promo-kod: <code>{settings.promo_code}</code>",
            reply_markup=membership_keyboard(settings.registration_url),
        )

    @router.message(CommandStart())
    async def start(message: Message, bot: Bot, state: FSMContext, command: CommandObject):
        await state.clear()
        referrer_id = None
        if command.args and command.args.startswith("ref_u"):
            raw = command.args.removeprefix("ref_u")
            referrer_id = int(raw) if raw.isdigit() else None
        referral_added = await db.upsert_user(
            message.from_user.id, message.from_user.username, message.from_user.full_name, referrer_id
        )
        if referral_added and referrer_id:
            referrer = await db.get_user(referrer_id)
            for admin_id in settings.admin_ids:
                try:
                    await bot.send_message(
                        admin_id,
                        "👥 <b>YANGI REFERAL</b>\n\n"
                        f"Taklif qilgan: {referrer['full_name'] if referrer else referrer_id} "
                        f"(<code>{referrer_id}</code>)\n"
                        f"Yangi foydalanuvchi: {user_label(message.from_user)}\n\n"
                        "Bonus yangi foydalanuvchi tasdiqlangandan keyin hisoblanadi.",
                    )
                except Exception:
                    pass
        if not await gate(message, bot):
            return
        user = await db.get_user(message.from_user.id)
        if user["is_blocked"]:
            await message.answer("🚫 Sizning botdan foydalanishingiz cheklangan.")
        elif user["status"] == "approved":
            await message.answer_dice(emoji="🎰")
            await asyncio.sleep(1.2)
            label = "👑 MEGA VIP" if user["tier"] == "mega" else "💎 VIP"
            await message.answer(f"✨ <b>{label} KABINET OCHILDI</b> ✨", reply_markup=user_menu(user["tier"]))
        elif user["status"] == "pending":
            await message.answer("⏳ Arizangiz admin tekshiruvida. Natija bot orqali yuboriladi.")
        else:
            await show_registration(message)

    @router.callback_query(F.data == "check_subscription")
    async def check_subscription(callback: CallbackQuery, bot: Bot):
        if await is_subscribed(bot, settings.channel_id, callback.from_user.id):
            await callback.message.answer_dice(emoji="🎯")
            await callback.message.answer("✅ <b>Obuna tasdiqlandi!</b>")
            await show_registration(callback.message)
            await callback.answer("Tasdiqlandi")
        else:
            await callback.answer("Siz hali kanalga obuna emassiz", show_alert=True)

    @router.callback_query(F.data.startswith("apply:"))
    async def apply(callback: CallbackQuery, state: FSMContext, bot: Bot):
        if not await is_subscribed(bot, settings.channel_id, callback.from_user.id):
            await callback.answer("Avval kanalga obuna bo'ling", show_alert=True)
            return
        tier = callback.data.split(":", 1)[1]
        deposit = settings.mega_deposit if tier == "mega" else settings.vip_deposit
        await state.update_data(tier=tier)
        await state.set_state(Registration.player_id)
        await callback.message.answer(
            f"{'👑 MEGA VIP' if tier == 'mega' else '💎 VIP'} arizasi\n\n"
            f"1. Bizning havoladan ro'yxatdan o'ting.\n2. <code>{settings.promo_code}</code> promo-kodini ishlating.\n"
            f"3. Kamida <b>{money(deposit)} so'm</b> depozit qiling.\n"
            "4. Luckypari Player ID raqamingizni hozir yuboring.\n\n"
            "Admin Player ID va depozitni tekshirgandan keyin bo'limni ochadi."
        )
        await callback.answer()

    @router.message(Registration.player_id)
    async def save_player_id(message: Message, state: FSMContext, bot: Bot):
        player_id = (message.text or "").strip()
        if not player_id.isdigit() or not 4 <= len(player_id) <= 20:
            await message.answer("❌ Player ID 4–20 xonali raqam bo'lishi kerak. Qayta yuboring:")
            return
        tier = (await state.get_data()).get("tier", "vip")
        await db.submit_application(message.from_user.id, player_id, tier)
        await state.clear()
        deposit = settings.mega_deposit if tier == "mega" else settings.vip_deposit
        await animate_message(
            message,
            ["🔐 Ma'lumotlar tekshirilmoqda...", "📨 Ariza himoyalangan holda yuborilmoqda...", "✅ Ariza adminga yuborildi!"],
            0.45,
        )
        user = await db.get_user(message.from_user.id)
        referrer = f"<code>{user['referred_by']}</code>" if user["referred_by"] else "Yo'q"
        table = (
            "🆕 <b>YANGI VIP ARIZA</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 Ism: <b>{message.from_user.full_name}</b>\n"
            f"🔗 Username: @{message.from_user.username or '-'}\n"
            f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n"
            f"🎮 Player ID: <code>{player_id}</code>\n"
            f"💠 Bo'lim: <b>{'MEGA VIP' if tier == 'mega' else 'VIP'}</b>\n"
            f"💳 Talab: <b>{money(deposit)} so'm</b>\n"
            f"👥 Referal egasi: {referrer}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Player ID va depozitni tekshiring."
        )
        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(admin_id, table, reply_markup=approval_keyboard(message.from_user.id))
            except Exception:
                pass

    async def animated_signal(message: Message, bot: Bot, factory):
        if not await access(message, bot):
            return
        left = 9 - (time.monotonic() - cooldowns.get(message.from_user.id, 0))
        if left > 0:
            await animate_message(message, ["⏳ Server band...", f"⚡ {int(left)+1} soniyadan keyin qayta urinib ko'ring."], 0.35)
            return
        cooldowns[message.from_user.id] = time.monotonic()
        progress = await animate_message(
            message,
            ["🔌 VIP serverga ulanmoqda...", "📡 Jonli raundlar tahlil qilinmoqda...", "🧠 Ehtiyotkor taxmin hisoblanmoqda..."],
            0.45,
        )
        await bot.send_dice(message.chat.id, emoji="🎰")
        await asyncio.sleep(2.1)
        await progress.edit_text("✅ <b>SIGNAL TAYYOR!</b>")
        await message.answer(format_signal(factory()))

    @router.message(F.text == "🍎 Apple")
    async def apple(message: Message, bot: Bot):
        await animated_signal(message, bot, apple_signal)

    @router.message(F.text == "🐔 Chicken Road")
    async def chicken(message: Message, bot: Bot):
        await animated_signal(message, bot, chicken_signal)

    @router.message(F.text == "💣 Mines")
    async def mines(message: Message, bot: Bot):
        await animated_signal(message, bot, mines_signal)

    @router.message(F.text == "🚀 Aviator")
    async def aviator(message: Message, bot: Bot):
        await animated_signal(message, bot, aviator_signal)

    @router.message(F.text == "✈️ Lucky Jet")
    async def luckyjet(message: Message, bot: Bot):
        await animated_signal(message, bot, luckyjet_signal)

    async def show_content(message: Message, bot: Bot, kind: str, title: str, mega=False):
        tier = await access(message, bot, mega=mega)
        if not tier:
            return
        rows = await db.latest_content(kind, message.from_user.id, tier)
        if not rows:
            await message.answer(f"{title}\n\nHozircha yangi ma'lumot joylanmagan.")
            return
        await message.answer_dice(emoji="🎯")
        for row in rows[:5]:
            await message.answer(f"{title}\n\n{row['body']}")

    @router.message(F.text == "📅 Kunlik stavkalar")
    async def daily(message: Message, bot: Bot):
        await show_content(message, bot, "daily", "📅 <b>KUNLIK STAVKALAR</b>")

    @router.message(F.text == "🔥 Yuqori koeffitsiyent")
    async def high_odds(message: Message, bot: Bot):
        await show_content(message, bot, "high_odds", "🔥 <b>YUQORI KOEFFITSIYENT</b>", mega=True)

    @router.message(F.text == "🧠 Casino tahlillari")
    async def casino(message: Message, bot: Bot):
        await show_content(message, bot, "casino", "🧠 <b>CASINO TAHLILI</b>\n⚠️ Natija kafolatlanmaydi.", mega=True)

    @router.message(F.text == "📈 MEGA hisobotlar")
    async def reports(message: Message, bot: Bot):
        await show_content(message, bot, "report", "📈 <b>MEGA VIP HISOBOT</b>", mega=True)

    @router.message(F.text == "🏆 Konkurslar")
    async def contests(message: Message, bot: Bot):
        tier = await access(message, bot)
        if not tier:
            return
        rows = await db.active_contests(message.from_user.id, tier)
        if not rows:
            await message.answer("🏆 Hozircha faol konkurs yo'q.")
            return
        for row in rows:
            count = await db.contest_count(row["id"])
            await message.answer(
                f"🏆 <b>{row['title']}</b>\n\n{row['description']}\n\n👥 Ishtirokchilar: {count}",
                reply_markup=contest_keyboard(row["id"]),
            )

    @router.callback_query(F.data.startswith("contest_join:"))
    async def contest_join(callback: CallbackQuery):
        joined = await db.join_contest(int(callback.data.split(":", 1)[1]), callback.from_user.id)
        await callback.answer("✅ Ishtirokingiz qabul qilindi!" if joined else "Avval qo'shilgansiz yoki konkurs yopilgan", show_alert=True)

    @router.message(F.text == "🎁 Bonus va promolar")
    async def bonuses(message: Message, bot: Bot):
        tier = await access(message, bot)
        if not tier:
            return
        rows = await db.latest_content("promo", message.from_user.id, tier)
        await message.answer_dice(emoji="🎲")
        intro = f"🎁 <b>BONUS VA PROMOLAR</b>\n\nAsosiy promo-kod: <code>{settings.promo_code}</code>"
        await message.answer(intro)
        for row in rows[:5]:
            await message.answer(row["body"])

    @router.message(F.text == "🎟 FreeBetlarim")
    async def freebets(message: Message, bot: Bot):
        if not await access(message, bot):
            return
        rows = await db.user_freebets(message.from_user.id)
        if not rows:
            await message.answer("🎟 Sizga hali shaxsiy FreeBet berilmagan.")
            return
        await message.answer("🎟 <b>SIZNING FREEBETLARINGIZ</b>\n\n" + "\n\n".join(
            f"Kod: <code>{r['code']}</code>\n{r['description']}" for r in rows
        ))

    @router.message(F.text == "👥 Referal tizim")
    async def referrals(message: Message, bot: Bot):
        if not await access(message, bot):
            return
        total, approved, user = await db.referral_stats(message.from_user.id)
        me = await bot.get_me()
        link = f"https://t.me/{me.username}?start=ref_{user['referral_code']}"
        await message.answer(
            "👥 <b>REFERAL TIZIM</b>\n\n"
            f"Har bir tasdiqlangan do'st uchun: <b>{money(settings.referral_reward)} so'm</b>\n"
            f"Taklif qilingan: {total}\nTasdiqlangan: {approved}\n"
            f"To'lov navbatidagi bonus: <b>{money(user['bonus_balance'])} so'm</b>\n\n"
            f"Shaxsiy havolangiz:\n<code>{link}</code>\n\n"
            "Bonus admin tekshiruvi va tasdig'idan keyin Player ID hisobiga qo'lda o'tkaziladi."
        )

    @router.message(F.text == "💎 VIP bo'lim")
    async def vip_section(message: Message, bot: Bot):
        if await access(message, bot):
            await message.answer("💎 <b>VIP FAOL</b>\nSignallar, kunlik stavkalar, konkurslar, promo va FreeBetlar ochiq.")

    @router.message(F.text == "👑 MEGA VIP")
    async def mega_section(message: Message, bot: Bot):
        if await access(message, bot, mega=True):
            await message.answer_dice(emoji="🎰")
            await message.answer("👑 <b>MEGA VIP FAOL</b>\nBarcha yuqori darajadagi bo'limlar ochiq.")

    @router.message(F.text == "⬆️ MEGA VIPga o'tish")
    async def upgrade(message: Message):
        await message.answer(
            f"👑 MEGA VIP uchun bizning havoladan kamida <b>{money(settings.mega_deposit)} so'm</b> depozit qiling "
            "va MEGA VIP arizasini yuboring.", reply_markup=membership_keyboard(settings.registration_url)
        )

    @router.message(F.text == "📥 Luckypari APK")
    async def apk(message: Message, bot: Bot):
        if not await access(message, bot):
            return
        path = Path(settings.apk_path)
        if not path.is_file():
            await message.answer("📦 APK hali admin tomonidan yuklanmagan.")
            return
        status = await animate_message(message, ["📦 APK tayyorlanmoqda...", "🔐 Fayl tekshirilmoqda...", "📤 Yuborilmoqda..."], 0.4)
        await message.answer_document(FSInputFile(path), caption="📥 <b>Luckypari APK</b>")
        await status.edit_text("✅ APK yuborildi.")

    @router.message(F.text == "👤 Kabinet")
    async def cabinet(message: Message):
        user = await db.get_user(message.from_user.id)
        if not user:
            return
        total, approved, _ = await db.referral_stats(message.from_user.id)
        await message.answer(
            "👤 <b>SHAXSIY KABINET</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"Ism: {message.from_user.full_name}\nTelegram ID: <code>{message.from_user.id}</code>\n"
            f"Player ID: <code>{user['player_id'] or '-'}</code>\n"
            f"Daraja: <b>{user['tier'].upper()}</b>\nHolat: <b>{user['status']}</b>\n"
            f"Referallar: {approved}/{total}\nBonus: <b>{money(user['bonus_balance'])} so'm</b>"
        )

    @router.message(F.text == "📊 Statistika")
    async def public_stats(message: Message, bot: Bot):
        if not await access(message, bot):
            return
        total, grouped, tiers, referrals = await db.stats()
        await message.answer(
            "📊 <b>BOT STATISTIKASI</b>\n\n"
            f"👥 Jami foydalanuvchilar: {total}\n💎 VIP: {tiers.get('vip', 0)}\n"
            f"👑 MEGA VIP: {tiers.get('mega', 0)}\n🔗 Tasdiqlangan referallar: {referrals}"
        )

    @router.message(F.text == "🛟 Yordam")
    async def help_start(message: Message, state: FSMContext):
        await state.set_state(Support.message)
        await message.answer("🛟 <b>YORDAM MARKAZI</b>\nAdminga yuboriladigan matn, rasm yoki faylni jo'nating.")

    @router.message(Support.message)
    async def help_send(message: Message, state: FSMContext, bot: Bot):
        sent = 0
        for admin_id in settings.admin_ids:
            try:
                await bot.forward_message(admin_id, message.chat.id, message.message_id)
                await bot.send_message(
                    admin_id, f"🛟 <b>YORDAM XABARI</b>\n{user_label(message.from_user)}",
                    reply_markup=support_reply_keyboard(message.from_user.id),
                )
                sent += 1
            except Exception:
                pass
        await state.clear()
        if sent:
            await animate_message(message, ["📨 Xabar yuborilmoqda...", "🔐 Admin panelga uzatilmoqda...", "✅ Adminga yetkazildi!"], 0.4)
        else:
            await message.answer("❌ Xabarni yuborib bo'lmadi.")

    return router
