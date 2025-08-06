import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from database import AsyncSessionLocal, User, Pair, AssignedTask, Task
from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from keyboards import task_buttons
from utils import safe_send_message
from tasks import send_task_to_pair  # Новая функция для отправки одного задания

router = Router()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_pair_code = State()

class AdminTask(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()

# Список админов (замените на реальные ID)
ADMIN_IDS = [1919847749]  # Добавьте сюда свои ID

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} начал регистрацию")
    await state.set_state(Registration.waiting_for_name)
    await message.answer("Привет! Как тебя зовут?")

@router.message(Registration.waiting_for_name)
async def get_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(Registration.waiting_for_pair_code)
    await message.answer("Введите кодовое слово вашей пары (если вы создаёте новую — придумайте его):")

@router.message(Registration.waiting_for_pair_code)
async def get_pair_code(message: Message, state: FSMContext, bot):
    data = await state.get_data()
    name = data['name']
    code = message.text

    async with AsyncSessionLocal() as session:
        try:
            # Проверяем, существует ли уже пользователь
            existing_user_result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
            existing_user = existing_user_result.scalar_one_or_none()
            
            if existing_user:
                await state.clear()
                await message.answer("Вы уже зарегистрированы! Используйте бота для получения заданий.")
                logger.info(f"Пользователь {message.from_user.id} уже зарегистрирован")
                return

            pair_result = await session.execute(select(Pair).where(Pair.code == code))
            pair = pair_result.scalar_one_or_none()

            if not pair:
                pair = Pair(code=code)
                session.add(pair)
                await session.commit()
                await session.refresh(pair)
                logger.info(f"Создана новая пара с кодом {code}")

            user = User(tg_id=message.from_user.id, name=name, pair_code=code, pair_id=pair.id)
            session.add(user)
            await session.commit()
            logger.info(f"Пользователь {message.from_user.id} зарегистрирован в паре {pair.id}")

        except IntegrityError as e:
            await session.rollback()
            if "users_tg_id_key" in str(e):
                await message.answer("Вы уже зарегистрированы в системе!")
                logger.warning(f"Попытка повторной регистрации пользователя {message.from_user.id}")
            else:
                await message.answer("Произошла ошибка при регистрации. Попробуйте позже.")
                logger.error(f"Ошибка при регистрации пользователя {message.from_user.id}: {e}")
        except Exception as e:
            await session.rollback()
            await message.answer("Произошла ошибка при регистрации. Попробуйте позже.")
            logger.error(f"Неожиданная ошибка при регистрации пользователя {message.from_user.id}: {e}")

    await state.clear()
    await message.answer("Вы успешно зарегистрированы!")

@router.message(Command("stats"))
async def show_stats(message: Message):
    logger.info(f"Пользователь {message.from_user.id} запросил статистику")
    
    async with AsyncSessionLocal() as session:
        try:
            # Проверяем, зарегистрирован ли пользователь
            user_result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
            user = user_result.scalar_one_or_none()
            
            if not user or not user.pair_id:
                await message.answer("Вы не зарегистрированы в паре.")
                return
            
            # Статистика по заданиям
            total_result = await session.execute(
                select(func.count(AssignedTask.id)).where(AssignedTask.pair_id == user.pair_id)
            )
            total_tasks = total_result.scalar_one() or 0
            
            accepted_result = await session.execute(
                select(func.count(AssignedTask.id)).where(
                    and_(AssignedTask.pair_id == user.pair_id, AssignedTask.status == "accepted")
                )
            )
            accepted_tasks = accepted_result.scalar_one() or 0
            
            rejected_result = await session.execute(
                select(func.count(AssignedTask.id)).where(
                    and_(AssignedTask.pair_id == user.pair_id, AssignedTask.status == "rejected")
                )
            )
            rejected_tasks = rejected_result.scalar_one() or 0
            
            pending_result = await session.execute(
                select(func.count(AssignedTask.id)).where(
                    and_(AssignedTask.pair_id == user.pair_id, AssignedTask.status == "pending")
                )
            )
            pending_tasks = pending_result.scalar_one() or 0
            
            stats_text = f"""📊 <b>Статистика вашей пары:</b>

Всего заданий: {total_tasks}
✅ Принято: {accepted_tasks}
❌ Отклонено: {rejected_tasks}
⏳ В ожидании: {pending_tasks}
"""
            
            await message.answer(stats_text, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Ошибка при получении статистики для пользователя {message.from_user.id}: {e}")
            await message.answer("Произошла ошибка при получении статистики. Попробуйте позже.")

# НОВАЯ КОМАНДА: Отправка заданий прямо сейчас
@router.message(Command("sendnow"), F.from_user.id.in_(ADMIN_IDS))
async def send_tasks_now(message: Message, bot):
    logger.info(f"Админ {message.from_user.id} инициировал немедленную отправку заданий")
    
    try:
        sent_count = 0
        async with AsyncSessionLocal() as session:
            # Получаем все пары
            result = await session.execute(select(User.pair_id).distinct())
            pair_ids = [row[0] for row in result.fetchall() if row[0] is not None]

            if not pair_ids:
                await message.answer("❌ Нет зарегистрированных пар для отправки заданий.")
                return

            # Отправляем задания всем парам
            for pair_id in pair_ids:
                try:
                    success = await send_task_to_pair(bot, pair_id, session)
                    if success:
                        sent_count += 1
                except Exception as e:
                    logger.error(f"Ошибка при отправке задания паре {pair_id}: {e}")
            
            await message.answer(f"✅ Задания отправлены {sent_count} парам!")
            logger.info(f"Админ {message.from_user.id} отправил задания {sent_count} парам")
            
    except Exception as e:
        logger.error(f"Ошибка при немедленной отправке заданий админом {message.from_user.id}: {e}")
        await message.answer("❌ Произошла ошибка при отправке заданий.")

@router.message(Command("sendnow"), F.from_user.id.not_in_(ADMIN_IDS))
async def not_admin_send(message: Message):
    await message.answer("❌ У вас нет прав для выполнения этой команды.")

# Обработка кнопок
@router.callback_query(F.data.startswith("accept_"))
async def accept_task(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        # Обновляем статус задания
        task_result = await session.execute(select(AssignedTask).where(AssignedTask.id == task_id))
        assigned_task = task_result.scalar_one_or_none()
        
        if assigned_task:
            old_status = assigned_task.status
            assigned_task.status = "accepted"
            await session.commit()
            logger.info(f"Пользователь {callback.from_user.id} принял задание {task_id}")
            
            # Уведомляем второго участника
            partner_tg_id = await get_partner_tg_id(callback.from_user.id, session)
            if partner_tg_id:
                await safe_send_message(
                    callback.bot,
                    partner_tg_id,
                    "✅ Ваш партнер принял задание!"
                )
            
            await callback.answer("Задание принято!")
        else:
            await callback.answer("Ошибка: задание не найдено.")

@router.callback_query(F.data.startswith("reject_"))
async def reject_task(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        # Обновляем статус задания
        task_result = await session.execute(select(AssignedTask).where(AssignedTask.id == task_id))
        assigned_task = task_result.scalar_one_or_none()
        
        if assigned_task:
            assigned_task.status = "rejected"
            await session.commit()
            logger.info(f"Пользователь {callback.from_user.id} отклонил задание {task_id}")
            
            # Получаем информацию о задании
            task_info_result = await session.execute(
                select(Task).where(Task.id == assigned_task.task_id)
            )
            task_info = task_info_result.scalar_one_or_none()
            
            # Получаем обоих участников пары
            user_result = await session.execute(
                select(User).where(User.pair_id == assigned_task.pair_id)
            )
            users = user_result.scalars().all()
            
            # Уведомляем обоих участников
            for user in users:
                if user.tg_id != callback.from_user.id:  # Уведомляем партнера
                    await safe_send_message(
                        callback.bot,
                        user.tg_id,
                        f"❌ Партнер отклонил задание:\n\n<b>{task_info.title}</b>\n{task_info.description}"
                    )
                else:  # Уведомляем того, кто отклонил
                    await safe_send_message(
                        callback.bot,
                        user.tg_id,
                        "❌ Вы отклонили задание. Партнер тоже уведомлен."
                    )
            
            # Проверяем, отклонили ли оба - если да, отправляем новое задание
            all_rejected = await check_if_both_rejected(assigned_task.pair_id, session)
            if all_rejected:
                logger.info(f"Оба партнера отклонили задание в паре {assigned_task.pair_id}. Отправляем новое.")
                await send_new_task_to_pair(callback.bot, assigned_task.pair_id, session)
            
            await callback.answer("Задание отклонено.")
        else:
            await callback.answer("Ошибка: задание не найдено.")

# Вспомогательная функция для проверки, отклонили ли оба
async def check_if_both_rejected(pair_id: int, session):
    # Получаем последнее задание для этой пары
    task_result = await session.execute(
        select(AssignedTask).where(AssignedTask.pair_id == pair_id).order_by(AssignedTask.date.desc()).limit(1)
    )
    last_task = task_result.scalar_one_or_none()
    
    if not last_task:
        return False
    
    # Проверяем, все ли участники отклонили
    user_result = await session.execute(select(User).where(User.pair_id == pair_id))
    users = user_result.scalars().all()
    
    rejected_count = 0
    for user in users:
        # Здесь можно добавить более сложную логику, но для простоты считаем, что если статус rejected, то отклонил
        if last_task.status == "rejected":
            rejected_count += 1
    
    return rejected_count == len(users)

# Отправка нового задания паре
async def send_new_task_to_pair(bot, pair_id: int, session):
    # Выбираем случайное задание
    task_result = await session.execute(select(Task).order_by(func.random()).limit(1))
    task = task_result.scalar_one_or_none()
    if not task:
        return

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
            f"🔄 Оба партнера отклонили предыдущее задание. Вот новое:\n\n<b>{task.title}</b>\n{task.description}",
            reply_markup=task_buttons(assigned.id)
        )

# Вспомогательная функция для получения ID партнера
async def get_partner_tg_id(user_tg_id: int, session):
    user_result = await session.execute(select(User).where(User.tg_id == user_tg_id))
    user = user_result.scalar_one_or_none()
    
    if user and user.pair_id:
        partner_result = await session.execute(
            select(User.tg_id).where(
                User.pair_id == user.pair_id,
                User.tg_id != user_tg_id
            )
        )
        partner = partner_result.scalar_one_or_none()
        return partner
    return None

# АДМИН ФУНКЦИОНАЛ для добавления заданий
@router.message(Command("addtask"), F.from_user.id.in_(ADMIN_IDS))
async def add_task_start(message: Message, state: FSMContext):
    logger.info(f"Админ {message.from_user.id} начал добавление задания")
    await state.set_state(AdminTask.waiting_for_title)
    await message.answer("Введите название задания:")

@router.message(AdminTask.waiting_for_title)
async def add_task_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdminTask.waiting_for_description)
    await message.answer("Введите описание задания:")

@router.message(AdminTask.waiting_for_description)
async def add_task_description(message: Message, state: FSMContext):
    data = await state.get_data()
    title = data['title']
    description = message.text

    async with AsyncSessionLocal() as session:
        task = Task(title=title, description=description)
        session.add(task)
        await session.commit()
        logger.info(f"Админ {message.from_user.id} добавил новое задание: {title}")
    
    await state.clear()
    await message.answer("✅ Задание успешно добавлено!")

@router.message(Command("addtask"), F.from_user.id.not_in_(ADMIN_IDS))
async def not_admin(message: Message):
    await message.answer("❌ У вас нет прав для выполнения этой команды.")