from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message
import asyncio


async def is_subscribed(bot: Bot, channel_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        if member.status in {
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER,
        }:
            return True
        return member.status == ChatMemberStatus.RESTRICTED and bool(getattr(member, "is_member", False))
    except (TelegramBadRequest, TelegramForbiddenError):
        return False


def user_label(user) -> str:
    username = f"@{user.username}" if user.username else "username yo'q"
    return f"{user.full_name} ({username}, ID: {user.id})"


async def animate_message(message: Message, frames: list[str], delay: float = 0.4) -> Message:
    sent = await message.answer(frames[0])
    for frame in frames[1:]:
        await asyncio.sleep(delay)
        try:
            await sent.edit_text(frame)
        except TelegramBadRequest:
            pass
    return sent
