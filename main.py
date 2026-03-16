# -*- coding: utf-8 -*-
"""
main.py

Telegram-бот для голосования по фотографиям.
Использует pyTelegramBotAPI (telebot) и SQLite.

Основные свойства:
- читает токен из mountables/token.txt
- работает с таблицей voting_{current_year}
- поддерживает /start, /vote, /cancel
- хранит прогресс пользователя в БД
- после перезапуска продолжает голосование с первого незаполненного пака
- использует безопасные SQL-запросы с параметрами
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import telebot
from telebot import types

# -------------------- CONFIG -------------------- #

BASE_DIR = Path("mountables")
TOKEN_PATH = BASE_DIR / "token.txt"
LOG_PATH = BASE_DIR / "logger.log"
DB_PATH = BASE_DIR / "voting.db"
ENTRIES_DIR = BASE_DIR / "entries"

TABLE_NAME = f"voting_{datetime.now().year}"
ITEMS_PER_PAGE = 60
SEND_PHOTO_DELAY_SECONDS = 0.5

# Если список пустой, голосовать могут все.
# Если хотите ограничить доступ, впишите Telegram user_id сюда.
ALLOWED_USER_IDS: set[int] = set()

WELCOME_TEXT = """Привет!

Сейчас вам предстоит выбрать лучшие фотографии с летней практики этого года.
Для этого напишите в чат команду /vote.

Чтобы выбрать фотографию, нажмите на кнопку с соответствующим номером один раз.
Писать в чат ничего не нужно.

Чтобы начать голосование заново, используйте /cancel, а затем снова /vote.
"""

VOTE_PROMPT_TEXT = (
    'Выберите фотографию. '
    'Если фотографий больше 60, используйте кнопки "Назад" и "Вперед".'
)

GENERIC_ERROR_TEXT = (
    "Упс! Что-то пошло не так при обработке вашего запроса. Попробуйте ещё раз."
)

# -------------------- LOGGING -------------------- #

BASE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s: %(message)s",
    filename=str(LOG_PATH),
    filemode="a",
    encoding="utf-8",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# -------------------- BOT INIT -------------------- #

if not TOKEN_PATH.exists():
    raise FileNotFoundError(
        f"Файл с токеном не найден: '{TOKEN_PATH}'. "
        f"Создайте его и поместите туда токен Telegram-бота."
    )

TG_TOKEN = TOKEN_PATH.read_text(encoding="utf-8").strip()
if not TG_TOKEN:
    raise ValueError(f"Файл '{TOKEN_PATH}' пустой.")

bot = telebot.TeleBot(TG_TOKEN)

# -------------------- HELPERS -------------------- #


def exception_message(chat_id: int) -> None:
    bot.send_message(chat_id, GENERIC_ERROR_TEXT)


def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


def ensure_authorized(message) -> bool:
    if is_authorized(message.from_user.id):
        return True

    bot.send_message(
        message.chat.id,
        "Извините, у вас нет доступа к этому голосованию.",
    )
    logger.warning("Пользователь %s не авторизован.", message.from_user.id)
    return False


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def validate_pack_number(pack: int) -> None:
    if not isinstance(pack, int) or pack < 1:
        raise ValueError(f"Некорректный номер пака: {pack}")


def get_existing_pack_numbers() -> list[int]:
    if not ENTRIES_DIR.exists():
        raise FileNotFoundError(f"Директория с паками не найдена: '{ENTRIES_DIR}'")

    pack_numbers = []
    pattern = re.compile(r"^PACK_(\d+)$")

    for item in ENTRIES_DIR.iterdir():
        if not item.is_dir():
            continue
        match = pattern.match(item.name)
        if match:
            pack_numbers.append(int(match.group(1)))

    if not pack_numbers:
        raise ValueError(f"В '{ENTRIES_DIR}' не найдено ни одной папки вида PACK_N.")

    return sorted(pack_numbers)


def get_total_packs() -> int:
    return len(get_existing_pack_numbers())


def get_pack_dir(pack: int) -> Path:
    validate_pack_number(pack)
    pack_dir = ENTRIES_DIR / f"PACK_{pack}"
    if not pack_dir.is_dir():
        raise FileNotFoundError(f"Папка пака не найдена: '{pack_dir}'")
    return pack_dir


def get_images_for_pack(pack: int) -> list[Path]:
    pack_dir = get_pack_dir(pack)

    allowed_ext = {".jpg", ".jpeg", ".png", ".webp"}
    images = [
        path for path in pack_dir.iterdir()
        if path.is_file() and path.suffix.lower() in allowed_ext
    ]

    def sort_key(path: Path):
        stem = path.stem
        return (0, int(stem)) if stem.isdigit() else (1, stem.lower())

    images = sorted(images, key=sort_key)

    if not images:
        raise ValueError(f"В паке PACK_{pack} не найдено изображений.")

    return images


def validate_table_exists() -> None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (TABLE_NAME,),
        ).fetchone()

    if row is None:
        raise RuntimeError(
            f"Таблица '{TABLE_NAME}' не найдена в '{DB_PATH}'. "
            f"Сначала создайте её через creating_voting_db.py."
        )


def validate_pack_column(pack: int) -> str:
    validate_pack_number(pack)
    total_packs = get_total_packs()
    if pack > total_packs:
        raise ValueError(
            f"Пак PACK_{pack} не существует. Всего паков: {total_packs}."
        )
    return f"PACK_{pack}"


# -------------------- DB LOGIC -------------------- #


def user_exists(user_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT EXISTS(SELECT 1 FROM {TABLE_NAME} WHERE id = ?)",
            (user_id,),
        ).fetchone()
    return bool(row[0])


def get_user_votes(user_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT * FROM {TABLE_NAME} WHERE id = ?",
            (user_id,),
        ).fetchone()
    return row


def delete_user_votes(user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            f"DELETE FROM {TABLE_NAME} WHERE id = ?",
            (user_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def save_vote(user_id: int, pack: int, image_number: int) -> None:
    column_name = validate_pack_column(pack)

    if image_number < 1:
        raise ValueError(f"Некорректный номер изображения: {image_number}")

    with get_connection() as conn:
        exists = conn.execute(
            f"SELECT EXISTS(SELECT 1 FROM {TABLE_NAME} WHERE id = ?)",
            (user_id,),
        ).fetchone()[0]

        if exists:
            conn.execute(
                f"UPDATE {TABLE_NAME} SET {column_name} = ? WHERE id = ?",
                (image_number, user_id),
            )
        else:
            conn.execute(
                f"INSERT INTO {TABLE_NAME} (id, {column_name}) VALUES (?, ?)",
                (user_id, image_number),
            )

        conn.commit()


def find_next_unvoted_pack(user_id: int) -> Optional[int]:
    total_packs = get_total_packs()
    row = get_user_votes(user_id)

    if row is None:
        return 1

    for pack in range(1, total_packs + 1):
        if row[f"PACK_{pack}"] is None:
            return pack

    return None


# -------------------- UI / MARKUP -------------------- #


def create_pagination_markup(
    total_items: int,
    items_per_page: int,
    current_page: int,
    pack: int,
) -> types.InlineKeyboardMarkup:
    start_index = (current_page - 1) * items_per_page
    end_index = min(start_index + items_per_page, total_items)

    markup = types.InlineKeyboardMarkup(row_width=3)

    buttons = [
        types.InlineKeyboardButton(
            text=str(i + 1),
            callback_data=f"vote:{pack}:{i + 1}",
        )
        for i in range(start_index, end_index)
    ]
    markup.add(*buttons)

    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(
            types.InlineKeyboardButton(
                text="⬅ Назад",
                callback_data=f"nav:{pack}:{current_page - 1}",
            )
        )
    if end_index < total_items:
        nav_buttons.append(
            types.InlineKeyboardButton(
                text="Вперед ➡",
                callback_data=f"nav:{pack}:{current_page + 1}",
            )
        )

    if nav_buttons:
        markup.add(*nav_buttons)

    return markup


def send_pack_for_voting(chat_id: int, pack: int) -> None:
    images = get_images_for_pack(pack)

    for image_num, image_path in enumerate(images, start=1):
        with image_path.open("rb") as photo:
            bot.send_photo(
                chat_id,
                photo,
                caption=str(image_num),
            )
        time.sleep(SEND_PHOTO_DELAY_SECONDS)

    markup = create_pagination_markup(
        total_items=len(images),
        items_per_page=ITEMS_PER_PAGE,
        current_page=1,
        pack=pack,
    )

    bot.send_message(chat_id, VOTE_PROMPT_TEXT, reply_markup=markup)


# -------------------- COMMAND HANDLERS -------------------- #


@bot.message_handler(commands=["start"])
def start_message(message):
    try:
        if not ensure_authorized(message):
            return

        bot.reply_to(message, WELCOME_TEXT)
        logger.info("Пользователь %s вызвал /start.", message.from_user.id)
    except Exception as e:
        logger.exception("Ошибка в /start для пользователя %s: %s", message.from_user.id, e)
        exception_message(message.chat.id)


@bot.message_handler(commands=["vote"])
def voting_message(message):
    try:
        if not ensure_authorized(message):
            return

        next_pack = find_next_unvoted_pack(message.from_user.id)

        if next_pack is None:
            bot.send_message(
                message.chat.id,
                "Кажется, вы уже проголосовали во всех категориях. "
                "Если хотите начать заново, используйте /cancel, а затем /vote.",
            )
            logger.info(
                "Пользователь %s попытался проголосовать повторно после завершения.",
                message.from_user.id,
            )
            return

        if user_exists(message.from_user.id):
            bot.send_message(
                message.chat.id,
                f"Продолжаем голосование с категории PACK_{next_pack}.",
            )
            logger.info(
                "Пользователь %s продолжает голосование с PACK_%s.",
                message.from_user.id,
                next_pack,
            )
        else:
            logger.info(
                "Пользователь %s начинает голосование с PACK_1.",
                message.from_user.id,
            )

        send_pack_for_voting(message.chat.id, next_pack)

    except Exception as e:
        logger.exception("Ошибка в /vote для пользователя %s: %s", message.from_user.id, e)
        exception_message(message.chat.id)


@bot.message_handler(commands=["cancel"])
def cancel_message(message):
    try:
        if not ensure_authorized(message):
            return

        deleted = delete_user_votes(message.from_user.id)

        if deleted:
            bot.send_message(
                message.chat.id,
                "Готово! Ваши голоса удалены. Чтобы проголосовать снова, введите /vote.",
            )
            logger.info("Пользователь %s удалил свои голоса.", message.from_user.id)
        else:
            bot.send_message(
                message.chat.id,
                "Кажется, у нас нет вашего голоса. Чтобы начать голосование, введите /vote.",
            )
            logger.info(
                "Пользователь %s попытался удалить несуществующий голос.",
                message.from_user.id,
            )

    except Exception as e:
        logger.exception("Ошибка в /cancel для пользователя %s: %s", message.from_user.id, e)
        exception_message(message.chat.id)


# -------------------- CALLBACK HANDLERS -------------------- #


@bot.callback_query_handler(func=lambda call: call.data.startswith("nav:"))
def handle_navigation(call):
    try:
        bot.answer_callback_query(call.id)

        if not is_authorized(call.from_user.id):
            bot.send_message(
                call.message.chat.id,
                "Извините, у вас нет доступа к этому голосованию.",
            )
            logger.warning("Неавторизованный callback nav от %s.", call.from_user.id)
            return

        _, pack_str, page_str = call.data.split(":")
        pack = int(pack_str)
        page = int(page_str)

        images = get_images_for_pack(pack)
        markup = create_pagination_markup(
            total_items=len(images),
            items_per_page=ITEMS_PER_PAGE,
            current_page=page,
            pack=pack,
        )

        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
        )

        logger.info(
            "Пользователь %s перешёл на страницу %s в PACK_%s.",
            call.from_user.id,
            page,
            pack,
        )

    except Exception as e:
        logger.exception(
            "Ошибка навигации callback для пользователя %s: %s",
            call.from_user.id,
            e,
        )
        exception_message(call.message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("vote:"))
def handle_vote_callback(call):
    try:
        bot.answer_callback_query(call.id)

        if not is_authorized(call.from_user.id):
            bot.send_message(
                call.message.chat.id,
                "Извините, у вас нет доступа к этому голосованию.",
            )
            logger.warning("Неавторизованный callback vote от %s.", call.from_user.id)
            return

        _, pack_str, image_str = call.data.split(":")
        pack = int(pack_str)
        image_number = int(image_str)

        images = get_images_for_pack(pack)
        if image_number > len(images):
            raise ValueError(
                f"Пользователь {call.from_user.id} выбрал image_number={image_number}, "
                f"но в PACK_{pack} только {len(images)} изображений."
            )

        save_vote(call.from_user.id, pack, image_number)

        bot.edit_message_text(
            text=f"Вы выбрали фотографию {image_number}.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None,
        )

        logger.info(
            "Пользователь %s проголосовал за фото %s в PACK_%s.",
            call.from_user.id,
            image_number,
            pack,
        )

        next_pack = find_next_unvoted_pack(call.from_user.id)
        if next_pack is None:
            bot.send_message(
                call.message.chat.id,
                "Готово! Ваши голоса учтены. "
                "Чтобы переголосовать, используйте /cancel, а затем /vote.",
            )
            logger.info("Пользователь %s завершил голосование.", call.from_user.id)
            return

        send_pack_for_voting(call.message.chat.id, next_pack)

    except Exception as e:
        logger.exception(
            "Ошибка обработки vote callback для пользователя %s: %s",
            call.from_user.id,
            e,
        )
        exception_message(call.message.chat.id)


# -------------------- STARTUP VALIDATION -------------------- #


def validate_startup() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Файл БД не найден: '{DB_PATH}'. "
            f"Сначала создайте БД и таблицу голосования."
        )

    validate_table_exists()
    total_packs = get_total_packs()

    with get_connection() as conn:
        table_info = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        existing_columns = {row["name"] for row in table_info}

    required_columns = {"id"} | {f"PACK_{i}" for i in range(1, total_packs + 1)}
    missing_columns = required_columns - existing_columns

    if missing_columns:
        raise RuntimeError(
            f"В таблице '{TABLE_NAME}' отсутствуют колонки: {sorted(missing_columns)}"
        )

    logger.info(
        "Проверка запуска успешна. Таблица=%s, паков=%s, БД=%s",
        TABLE_NAME,
        total_packs,
        DB_PATH,
    )


# -------------------- ENTRYPOINT -------------------- #

if __name__ == "__main__":
    validate_startup()
    logger.info("Бот запущен.")
    bot.infinity_polling(timeout=120, long_polling_timeout=120, skip_pending=False)
