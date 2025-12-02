"""FSM states for lead collection."""
from aiogram.fsm.state import State, StatesGroup


class LeadForm(StatesGroup):
    choosing_service = State()
    getting_name = State()
    getting_city = State()
    getting_contact = State()
    getting_details = State()
