"""Utilities for saving and formatting leads."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, List


def save_lead_to_file(lead: dict, filepath: str) -> None:
    """Append a lead to a JSON Lines file."""
    try:
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "a", encoding="utf-8") as file:
            json.dump(lead, file, ensure_ascii=False)
            file.write("\n")
    except Exception:
        logging.exception("Не удалось сохранить заявку в файл %s", filepath)


def load_last_leads(filepath: str, limit: int = 10) -> List[dict]:
    """Load the last `limit` leads from the file."""
    leads: List[dict] = []
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    leads.append(json.loads(line))
                except json.JSONDecodeError:
                    logging.warning("Пропущена повреждённая строка в %s", filepath)
                    continue
    except FileNotFoundError:
        return []

    return leads[-limit:]


def format_lead_summary(lead: dict, include_meta: bool = True) -> str:
    """Create a nicely formatted lead summary for users or admins."""
    base_info = [
        "<b>📍 Заявка оформлена</b>",
        f"<b>Услуга:</b> {lead.get('service', '—')}",
        f"<b>Имя:</b> {lead.get('name', '—')}",
        f"<b>Город:</b> {lead.get('city', '—')}",
        f"<b>Контакт:</b> {lead.get('contact', '—')}",
        "",
        "<b>Детали запроса:</b>",
        lead.get("details", "—"),
    ]

    if include_meta:
        meta_lines: Iterable[str] = [
            "",
            f"<i>Создано:</i> {lead.get('created_at', '')}",
        ]
        tg_id = lead.get("tg_id")
        username = lead.get("username")
        if tg_id:
            meta_lines = [*meta_lines, f"<i>Telegram ID:</i> {tg_id}"]
        if username:
            meta_lines = [*meta_lines, f"<i>Username:</i> @{username}"]
        base_info.extend(meta_lines)

    return "\n".join(line for line in base_info if line is not None)


def format_leads_for_admin(leads: List[dict]) -> List[str]:
    """Split leads into chunks suitable for Telegram messages."""
    items: List[str] = []
    for index, lead in enumerate(leads, start=1):
        created_at = lead.get("created_at", "")
        header = f"<b>{index}. {lead.get('service', 'Заявка')}</b>"
        time_line = f"<i>Создано:</i> {created_at}" if created_at else None
        body = format_lead_summary(lead, include_meta=False)
        items.append("\n".join(line for line in [header, time_line, body] if line))

    chunks: List[str] = []
    current = ""
    for part in items:
        if not current:
            current = part
            continue
        if len(current) + 2 + len(part) > 3900:
            chunks.append(current)
            current = part
        else:
            current += "\n\n" + part

    if current:
        chunks.append(current)
    return chunks
