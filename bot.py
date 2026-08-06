import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from admin import create_admin_router
from config import load_settings
from database import Database
from handlers import create_user_router


async def main():
    settings = load_settings()
    db = Database(settings.database_path, settings.referral_reward)
    await db.init()
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(create_admin_router(settings, db))
    dp.include_router(create_user_router(settings, db))
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
