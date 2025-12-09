"""Telegram bot entrypoint for collecting automotive leads."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from config import Settings
from keyboards import (
    BACK_TO_SERVICES,
    CANCEL_FLOW,
    SERVICE_OPTIONS,
    navigation_inline_keyboard,
    service_inline_keyboard,
)
from leads import format_lead_summary, format_leads_for_admin, load_last_leads, save_lead_to_file
from states import LeadForm

settings = Settings.load()


DETAIL_QUESTIONS = {
    SERVICE_OPTIONS[0]: (
        "Опишите, что ищем: <b>марка/модель</b> или класс авто, <b>год</b>,\n"
        "<b>ориентировочный бюджет</b> и приоритеты (надёжность, комфорт, свежий год и т.п.)."
    ),
    SERVICE_OPTIONS[1]: (
        "Расскажите о машине (марка/модель/год) и что доработать: <b>диски</b>, <b>обвес</b>,"
        " <b>оптика</b>, <b>салон</b>, техника, ориентировочный бюджет и сроки."
    ),
    SERVICE_OPTIONS[2]: (
        "Укажите авто (марка/модель/год) и что нужно: резина (лето/зима/всесезон),"
        " колодки, фильтры и т.п. Нужна установка или только поставка?"
    ),
    SERVICE_OPTIONS[3]: (
        "Опишите авто (марка/модель/цвет/год) и задачи: мойка, химчистка, полировка,"
        " защитные покрытия, подготовка к продаже. Когда желательно выполнить?"
    ),
    SERVICE_OPTIONS[4]: "Напишите ваш вопрос или ситуацию в свободной форме, мы подскажем, как лучше поступить.",
}

GREETING_TEXT = (
    "<b>Привет!</b> Я помогу оформить заявку на: \n"
    "• привоз авто из Азии под ключ 🚗\n"
    "• тюнинг и доработку 🛠\n"
    "• резину и расходники 🛞\n"
    "• детейлинг и подготовку ✨\n\n"
    "Выберите подходящую услугу кнопкой ниже. Это займёт 1–2 минуты, и мы сразу приступим к расчёту."
)

SERVICE_CONFIRMED_TEXT = (
    "Отлично, фиксирую услугу: <b>{service}</b>.\n"
    "Сейчас спрошу пару деталей, чтобы передать вашу задачу специалисту.\n\n"
    "Как к вам обращаться?"
)

THANK_YOU_TEXT = (
    "<b>Спасибо!</b> Заявка отправлена нашему специалисту.\n"
    "Обычно отвечаем в рабочие часы в течение <b>10–30 минут</b>."
)


# === Helpers ===

def _is_blank(text: Optional[str]) -> bool:
    return not text or not text.strip()


# === Dispatcher ===

storage = MemoryStorage()
dp = Dispatcher(storage=storage)


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Reset state and show service selection menu."""
    await state.clear()
    await message.answer(GREETING_TEXT, reply_markup=service_inline_keyboard())
    await state.set_state(LeadForm.choosing_service)


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Cancel the current dialog."""
    await state.clear()
    await message.answer(
        "Сценарий сброшен. Когда будете готовы начать заново — нажмите /start.",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(LeadForm.choosing_service)
async def remind_service_choice(message: Message) -> None:
    """Ask the user to pick a service via inline buttons."""
    await message.answer(
        "Пожалуйста, выберите услугу кнопкой ниже, чтобы я понял ваш запрос.",
        reply_markup=service_inline_keyboard(),
    )


@dp.callback_query(F.data == BACK_TO_SERVICES)
async def navigate_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Return the user to the service menu from any state."""
    await callback.answer("Меню услуг")
    await state.clear()
    await callback.message.answer(
        "Давайте подберём услугу заново. Что вас интересует?",
        reply_markup=service_inline_keyboard(),
    )
    await state.set_state(LeadForm.choosing_service)


@dp.callback_query(F.data == CANCEL_FLOW)
async def navigate_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Stop the dialog via inline navigation."""
    await callback.answer("Диалог остановлен")
    await state.clear()
    await callback.message.answer(
        "Сценарий остановлен. Когда захотите — нажмите /start, чтобы начать заново.",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.callback_query(F.data.startswith("svc:"))
async def process_service_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle service selection callback from any state."""
    await callback.answer()

    data = callback.data or ""
    try:
        _, idx_str = data.split(":", 1)
        idx = int(idx_str)
    except (ValueError, IndexError):
        idx = -1

    if not (0 <= idx < len(SERVICE_OPTIONS)):
        await callback.message.answer(
            "Не удалось определить услугу. Пожалуйста, выберите вариант из списка.",
            reply_markup=service_inline_keyboard(),
        )
        return

    service = SERVICE_OPTIONS[idx]
    await state.clear()
    await state.update_data(service=service)
    await callback.message.answer(
        SERVICE_CONFIRMED_TEXT.format(service=service),
        reply_markup=navigation_inline_keyboard(),
    )
    await state.set_state(LeadForm.getting_name)


@dp.message(LeadForm.getting_name)
async def process_name(message: Message, state: FSMContext) -> None:
    """Ask for the client's name."""
    if _is_blank(message.text):
        await message.answer(
            "Пожалуйста, укажите, как к вам обращаться.",
            reply_markup=navigation_inline_keyboard(),
        )
        return

    await state.update_data(name=message.text.strip())
    await message.answer("Из какого вы города?", reply_markup=navigation_inline_keyboard())
    await state.set_state(LeadForm.getting_city)


@dp.message(LeadForm.getting_city)
async def process_city(message: Message, state: FSMContext) -> None:
    """Ask for the client's city."""
    if _is_blank(message.text):
        await message.answer(
            "Напишите, пожалуйста, ваш город — это важно для логистики.",
            reply_markup=navigation_inline_keyboard(),
        )
        return

    await state.update_data(city=message.text.strip())
    await message.answer(
        "Оставьте контакт для связи: телефон или @ник в Telegram.",
        reply_markup=navigation_inline_keyboard(),
    )
    await state.set_state(LeadForm.getting_contact)


@dp.message(LeadForm.getting_contact)
async def process_contact(message: Message, state: FSMContext) -> None:
    """Ask for the preferred contact method."""
    if _is_blank(message.text):
        await message.answer(
            "Нужен контакт, чтобы связаться: номер телефона или @ник в Telegram.",
            reply_markup=navigation_inline_keyboard(),
        )
        return

    await state.update_data(contact=message.text.strip())
    data = await state.get_data()
    service = data.get("service", SERVICE_OPTIONS[0])
    raw_question = DETAIL_QUESTIONS.get(
        service,
        "Опишите ваш запрос подробнее, чтобы мы подготовили точный ответ.",
    )
    question = "\n".join(raw_question) if isinstance(raw_question, (list, tuple)) else str(raw_question)
    await message.answer(question, reply_markup=navigation_inline_keyboard())
    await state.set_state(LeadForm.getting_details)


@dp.message(LeadForm.getting_details)
async def process_details(message: Message, state: FSMContext) -> None:
    """Collect details, save lead, and send summaries."""
    if _is_blank(message.text):
        await message.answer(
            "Добавьте, пожалуйста, детали запроса, чтобы мы быстро помогли.",
            reply_markup=navigation_inline_keyboard(),
        )
        return

    await state.update_data(details=message.text.strip())
    data = await state.get_data()

    lead = {
        "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "service": data.get("service"),
        "name": data.get("name"),
        "city": data.get("city"),
        "contact": data.get("contact"),
        "details": data.get("details"),
        "tg_id": message.from_user.id if message.from_user else None,
        "username": message.from_user.username if message.from_user else None,
    }

    save_lead_to_file(lead, settings.leads_file)
    summary = format_lead_summary(lead)

    await message.answer(
        f"{summary}\n\n{THANK_YOU_TEXT}",
    )

    if settings.admin_chat_id:
        try:
            await message.bot.send_message(settings.admin_chat_id, summary)
        except Exception:
            logging.exception("Не удалось отправить заявку админу")

    await state.clear()
    await message.answer("Если захотите оформить ещё одну заявку — нажмите /start.")


@dp.message(Command("leads"))
async def cmd_leads(message: Message) -> None:
    """Show last leads to admin."""
    if not settings.admin_chat_id or message.from_user.id != settings.admin_chat_id:
        await message.answer("Команда доступна только администратору.")
        return

    leads = load_last_leads(settings.leads_file, limit=10)
    if not leads:
        await message.answer("Заявок пока нет.")
        return

    chunks = format_leads_for_admin(leads)
    await message.answer("Последние заявки:")
    for chunk in chunks:
        await message.answer(chunk)


async def main() -> None:
    """Entrypoint for running the bot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.info("Starting bot")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
