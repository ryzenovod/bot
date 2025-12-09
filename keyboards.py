"""Keyboards used in the bot."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

SERVICE_OPTIONS = [
    "🚗 Привезти авто под заказ",
    "🛠 Тюнинг / доработка авто",
    "🛞 Резина и расходники",
    "✨ Детейлинг / подготовка авто",
    "💬 Просто консультация",
]

BACK_TO_SERVICES = "nav:services"
CANCEL_FLOW = "nav:cancel"


def service_inline_keyboard() -> InlineKeyboardMarkup:
    """Create inline keyboard for service selection."""
    buttons = [
        [InlineKeyboardButton(text=service, callback_data=f"svc:{idx}")]
        for idx, service in enumerate(SERVICE_OPTIONS)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def navigation_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for returning to the service menu or cancelling."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ Выбрать другую услугу", callback_data=BACK_TO_SERVICES
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏹ Завершить диалог", callback_data=CANCEL_FLOW
                )
            ],
        ]
    )
