import asyncio
import logging
import os
import json
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage


# === Настройки ===

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN в переменных окружения")

# ID админа (куда слать заявки и кому разрешён /leads)
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID", "0")
try:
    ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_RAW)
except ValueError:
    ADMIN_CHAT_ID = 0

# файл, куда будут складываться все заявки (по одной JSON-строке)
LEADS_FILE = "leads.jsonl"

# варианты услуг (тексты кнопок)
SERVICE_OPTIONS = [
    "Привезти авто под заказ",
    "Тюнинг / доработка авто",
    "Резина и расходники",
    "Детейлинг / подготовка авто",
    "Просто консультация",
]


# === FSM-состояния ===

class LeadForm(StatesGroup):
    choosing_service = State()
    getting_name = State()
    getting_city = State()
    getting_contact = State()
    getting_details = State()


# === Вспомогательные функции ===

def service_inline_keyboard() -> InlineKeyboardMarkup:
    """
    Инлайн-меню с выбором услуги.
    callback_data вида: svc:0, svc:1, ...
    """
    buttons = [
        [InlineKeyboardButton(text=service, callback_data=f"svc:{idx}")]
        for idx, service in enumerate(SERVICE_OPTIONS)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def save_lead_to_file(lead: dict) -> None:
    """
    Сохраняем одну заявку в файл LEADS_FILE в формате JSONL (1 строка = 1 JSON).
    """
    try:
        with open(LEADS_FILE, "a", encoding="utf-8") as f:
            json.dump(lead, f, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        logging.exception("Не удалось сохранить заявку в файл: %r", e)


def load_last_leads(limit: int = 10) -> list[dict]:
    """
    Читаем последние limit заявок из LEADS_FILE.
    Если файла нет — возвращаем пустой список.
    """
    leads: list[dict] = []
    try:
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    leads.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []

    if not leads:
        return []

    return leads[-limit:]


def format_leads_for_admin(leads: list[dict]) -> list[str]:
    """
    Формируем текст для /leads, разбивая на куски <= 4000 символов.
    Возвращаем список строк, которые можно по очереди отправить.
    """
    parts = []
    for i, lead in enumerate(leads, start=1):
        created_at = lead.get("created_at", "")
        service = lead.get("service", "")
        name = lead.get("name", "")
        city = lead.get("city", "")
        contact = lead.get("contact", "")
        details = lead.get("details", "")
        tg_id = lead.get("tg_id", "")
        username = lead.get("username", "")

        line = (
            f"{i}. {created_at}\n"
            f"   Услуга: {service}\n"
            f"   Имя: {name}\n"
            f"   Город: {city}\n"
            f"   Контакт: {contact}\n"
            f"   Описание: {details}\n"
            f"   TG ID: {tg_id}"
        )
        if username:
            line += f" (@{username})"
        parts.append(line)

    chunks: list[str] = []
    current = ""

    for part in parts:
        if not current:
            current = part
            continue
        # +2 на два перевода строки между блоками
        if len(current) + 2 + len(part) > 4000:
            chunks.append(current)
            current = part
        else:
            current += "\n\n" + part

    if current:
        chunks.append(current)

    return chunks


# === Инициализация ===

storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# === Хендлеры ===

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """
    /start — начало диалога, показываем инлайн-меню с услугами.
    """
    await state.clear()
    await message.answer(
        "Привет! Я помогу оформить заявку на услуги:\n"
        "• пригон авто в РФ\n"
        "• тюнинг / доработку\n"
        "• резину и расходники\n"
        "• детейлинг / подготовку авто\n\n"
        "Выберите нужный вариант кнопкой ниже:",
        reply_markup=service_inline_keyboard(),
    )
    await state.set_state(LeadForm.choosing_service)


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """
    /cancel — сброс текущего сценария.
    """
    await state.clear()
    await message.answer(
        "Окей, всё отменил. Чтобы начать заново — отправьте /start.",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.callback_query(LeadForm.choosing_service, F.data.startswith("svc:"))
async def process_service_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Пользователь выбрал услугу из инлайн-меню.
    """
    await callback.answer()

    data = callback.data or ""
    _, idx_str = data.split(":", 1)
    try:
        idx = int(idx_str)
    except ValueError:
        idx = 0

    if not (0 <= idx < len(SERVICE_OPTIONS)):
        await callback.message.answer(
            "Не удалось определить услугу. Попробуйте ещё раз: /start."
        )
        await state.clear()
        return

    service = SERVICE_OPTIONS[idx]
    await state.update_data(service=service)

    await callback.message.answer(
        f"Вы выбрали: <b>{service}</b>\n\n"
        "Как к вам обращаться?",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(LeadForm.getting_name)


@dp.message(LeadForm.getting_name)
async def process_name(message: Message, state: FSMContext) -> None:
    """
    Имя клиента.
    """
    name = (message.text or "").strip()
    await state.update_data(name=name)

    await message.answer("Из какого вы города?")
    await state.set_state(LeadForm.getting_city)


@dp.message(LeadForm.getting_city)
async def process_city(message: Message, state: FSMContext) -> None:
    """
    Город клиента.
    """
    city = (message.text or "").strip()
    await state.update_data(city=city)

    await message.answer("Оставьте контакт для связи (телефон или @ник в Telegram).")
    await state.set_state(LeadForm.getting_contact)


@dp.message(LeadForm.getting_contact)
async def process_contact(message: Message, state: FSMContext) -> None:
    """
    Контакт клиента.
    """
    contact = (message.text or "").strip()
    await state.update_data(contact=contact)

    data = await state.get_data()
    service = data.get("service", "")

    # Уточняющий вопрос по услуге
    if service == SERVICE_OPTIONS[0]:
        question = (
            "Опишите, какой автомобиль вы хотите: "
            "марка/модель, год, ориентировочный бюджет, важные опции."
        )
    elif service == SERVICE_OPTIONS[1]:
        question = (
            "Кратко опишите, что хотите доработать по тюнингу и на каком авто "
            "(диски, обвес, оптика, салон и т.п.)."
        )
    elif service == SERVICE_OPTIONS[2]:
        question = (
            "Напишите, какая резина или какие расходники нужны и для какого авто. "
            "Если важны бренды — укажите их."
        )
    elif service == SERVICE_OPTIONS[3]:
        question = (
            "Расскажите, что нужно по детейлингу (химчистка, полировка, "
            "защитные покрытия и т.п.) и к какому сроку."
        )
    else:  # "Просто консультация"
        question = "Напишите, пожалуйста, ваш вопрос или задачу в свободной форме."

    await message.answer(question)
    await state.set_state(LeadForm.getting_details)


@dp.message(LeadForm.getting_details)
async def process_details(message: Message, state: FSMContext) -> None:
    """
    Финальное описание задачи + сохранение и отправка заявки.
    """
    details = (message.text or "").strip()
    await state.update_data(details=details)

    data = await state.get_data()
    created_at = datetime.now().isoformat(sep=" ", timespec="seconds")

    lead = {
        "created_at": created_at,
        "service": data.get("service"),
        "name": data.get("name"),
        "city": data.get("city"),
        "contact": data.get("contact"),
        "details": data.get("details"),
        "tg_id": message.from_user.id if message.from_user else None,
        "username": message.from_user.username if message.from_user else None,
    }

    # Сохраняем в файл
    save_lead_to_file(lead)

    # Формируем сводку для пользователя/админа
    text_lines = [
        "Новая заявка:",
        f"Время: {lead['created_at']}",
        f"Услуга: {lead['service']}",
        f"Имя: {lead['name']}",
        f"Город: {lead['city']}",
        f"Контакт: {lead['contact']}",
        "",
        "Описание запроса:",
        lead["details"],
        "",
        f"Telegram ID: {lead['tg_id']}",
    ]
    if lead["username"]:
        text_lines.append(f"Username: @{lead['username']}")

    summary = "\n".join(line for line in text_lines if line)

    # Отправляем сводку пользователю
    await message.answer(
        "Спасибо! Я записал вашу заявку. Ниже — сводка:\n\n" + summary
    )

    # Отправляем сводку админу (если указан ADMIN_CHAT_ID)
    if ADMIN_CHAT_ID:
        try:
            await message.bot.send_message(chat_id=ADMIN_CHAT_ID, text=summary)
        except Exception as e:
            logging.exception("Не удалось отправить заявку админу: %r", e)

    # Сбрасываем состояние
    await state.clear()
    await message.answer(
        "Если захотите оформить ещё одну заявку — отправьте /start."
    )


@dp.message(Command("leads"))
async def cmd_leads(message: Message) -> None:
    """
    /leads — показывает админу последние заявки из файла.
    """
    if not ADMIN_CHAT_ID or message.from_user.id != ADMIN_CHAT_ID:
        await message.answer("Эта команда доступна только администратору.")
        return

    leads = load_last_leads(limit=10)
    if not leads:
        await message.answer("Заявок пока нет.")
        return

    chunks = format_leads_for_admin(leads)
    await message.answer("Последние заявки:")
    for chunk in chunks:
        await message.answer(chunk)


# === Точка входа ===

async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
