import logging
from aiogram.exceptions import TelegramForbiddenError
from aiogram import Bot

logger = logging.getLogger(__name__)

async def safe_send_message(bot: Bot, chat_id: int, text: str, reply_markup=None):
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML")
        logger.info(f"Сообщение успешно отправлено пользователю {chat_id}")
    except TelegramForbiddenError:
        logger.warning(f"Пользователь {chat_id} заблокировал бота")
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {chat_id}: {e}")