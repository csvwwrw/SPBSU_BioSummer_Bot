# -*- coding: utf-8 -*-
"""
creating_voting_db.py

Создаёт таблицу голосования в существующей SQLite БД.
Количество колонок (паков) определяется автоматически по числу папок в ENTRIES_DIR.
Имя таблицы синхронизировано с main.py через константу TABLE_NAME.

Запуск: python creating_voting_db.py
"""

import os
import sqlite3
from sqlite3 import Error
from datetime import datetime

# --------------- КОНФИГУРАЦИЯ --------------- #
# Путь должен совпадать с db_path в main.py
DB_PATH = 'mountables/voting.db'

# Имя таблицы должно совпадать с db_name в main.py
TABLE_NAME = f'voting_{datetime.now().year}'

# Путь к папке с паками — используется для подсчёта числа категорий
ENTRIES_DIR = 'mountables/entries'
# -------------------------------------------- #


def count_packs(entries_dir: str) -> int:
    """
    Считает количество папок-паков в директории entries.
    Учитывает только директории, игнорирует файлы.
    """
    if not os.path.isdir(entries_dir):
        raise FileNotFoundError(
            f"Директория с паками не найдена: '{entries_dir}'. "
            "Убедитесь, что rename_all_entries.py был запущен перед этим скриптом."
        )

    packs = [
        entry for entry in os.listdir(entries_dir)
        if os.path.isdir(os.path.join(entries_dir, entry))
    ]

    if not packs:
        raise ValueError(f"В директории '{entries_dir}' не найдено ни одной папки-пака.")

    return len(packs)


def create_voting_table(db_path: str, table_name: str, num_packs: int) -> None:
    """
    Создаёт таблицу голосования в SQLite БД.

    :param db_path:     путь к файлу .db
    :param table_name:  имя таблицы (например, 'voting_2025')
    :param num_packs:   количество паков (колонок PACK_N)
    """
    # Динамически строим список колонок по реальному числу паков
    pack_columns = ',\n    '.join([f'PACK_{i} INTEGER' for i in range(1, num_packs + 1)])

    query = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INTEGER PRIMARY KEY,
        {pack_columns}
    );
    """

    # Используем контекстный менеджер — соединение закроется автоматически
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(query)
            conn.commit()
            print(f"[OK] Таблица '{table_name}' успешно создана в '{db_path}'.")
            print(f"     Колонок с паками: {num_packs} (PACK_1 … PACK_{num_packs})")
            _print_existing_tables(conn)
    except Error as e:
        print(f"[ОШИБКА] Не удалось создать таблицу '{table_name}': {e}")
        raise


def _print_existing_tables(conn: sqlite3.Connection) -> None:
    """Выводит список всех таблиц в БД — для визуальной проверки."""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"     Все таблицы в БД: {tables}")


if __name__ == '__main__':
    print(f"Имя создаваемой таблицы: {TABLE_NAME}")
    print(f"Путь к БД:               {DB_PATH}")
    print(f"Директория с паками:     {ENTRIES_DIR}")
    print("-" * 50)

    num_packs = count_packs(ENTRIES_DIR)
    print(f"Найдено паков: {num_packs}")

    create_voting_table(
        db_path=DB_PATH,
        table_name=TABLE_NAME,
        num_packs=num_packs,
    )
