from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def task_buttons(task_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{task_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{task_id}")]
    ])