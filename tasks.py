import logging
from database import AsyncSessionLocal, AssignedTask, Task, User
from sqlalchemy import select, func
from keyboards import task_buttons
from utils import safe_send_message

logger = logging.getLogger(__name__)

# Новая функция для отправки одного задания паре
async def send_task_to_pair(bot, pair_id: int, session):
    try:
        # Выбираем случайное задание
        task_result = await session.execute(select(Task).order_by(func.random()).limit(1))
        task = task_result.scalar_one_or_none()
        if not task:
            logger.warning(f"Нет доступных заданий для пары {pair_id}")
            return False

        # Сохраняем назначение
        assigned = AssignedTask(pair_id=pair_id, task_id=task.id)
        session.add(assigned)
        await session.commit()
        await session.refresh(assigned)

        # Отправляем обеим участникам
        user_result = await session.execute(select(User).where(User.pair_id == pair_id))
        users = user_result.scalars().all()
        for user in users:
            await safe_send_message(
                bot,
                user.tg_id,
                f"✨ Новое задание:\n\n<b>{task.title}</b>\n{task.description}",
                reply_markup=task_buttons(assigned.id)
            )
        
        logger.info(f"Задание отправлено паре {pair_id}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при отправке задания паре {pair_id}: {e}")
        return False

async def send_daily_task_to_all_pairs(bot):
    logger.info("Начало отправки ежедневных заданий")
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.pair_id).distinct())
        pair_ids = [row[0] for row in result.fetchall() if row[0] is not None]

        sent_count = 0
        for pair_id in pair_ids:
            success = await send_task_to_pair(bot, pair_id, session)
            if success:
                sent_count += 1
        
        logger.info(f"Завершена отправка заданий. Отправлено {sent_count} парам.")