from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import TASK_TIME
from tasks import send_daily_task_to_all_pairs
from aiogram import Bot

scheduler = AsyncIOScheduler()

def setup_scheduler(bot: Bot):
    hour, minute = map(int, TASK_TIME.split(":"))
    scheduler.add_job(
        send_daily_task_to_all_pairs,
        trigger=CronTrigger(hour=hour, minute=minute, timezone="Europe/Moscow"),
        args=[bot]
    )
    scheduler.start()