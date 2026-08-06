from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError


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
