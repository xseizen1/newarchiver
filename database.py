import sqlite3
import os
from typing import List

DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")

def init_db():
    """Создаёт таблицы, если их нет"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица авторизованных пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS authorized_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")  # Временно для проверки

def is_authorized(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM authorized_users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone() is not None
    conn.close()
    return result

def add_authorized_user(user_id: int, username: str, first_name: str, added_by: int) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO authorized_users (user_id, username, first_name, added_by)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, first_name, added_by))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        print(f"Error adding user: {e}")
        return False

def remove_authorized_user(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM authorized_users WHERE user_id = ?", (user_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success

def get_all_authorized() -> List[int]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM authorized_users")
    result = [row[0] for row in cursor.fetchall()]
    conn.close()
    return result