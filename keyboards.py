"""Keyboards used in the bot."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

SERVICE_OPTIONS = [
    "🚗 Привезти авто под заказ",
    "🛠 Тюнинг / доработка авто",
    "🛞 Резина и расходники",
    "✨ Детейлинг / подготовка авто",
    "💬 Просто консультация",
]


def service_inline_keyboard() -> InlineKeyboardMarkup:
    """Create inline keyboard for service selection."""
    buttons = [
        [InlineKeyboardButton(text=service, callback_data=f"svc:{idx}")]
        for idx, service in enumerate(SERVICE_OPTIONS)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
