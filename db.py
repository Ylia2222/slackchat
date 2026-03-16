import sqlite3

DB_PATH = "database.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('registration_open', '0')"
    )

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('user', 'admin')),
        archived_at TEXT,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    )
""")
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL CHECK (type IN ('public', 'private', 'read_only')),
            owner_id INTEGER,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            FOREIGN KEY (owner_id) REFERENCES users(id)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS channel_members (
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('owner', 'member', 'read_only')),
            PRIMARY KEY (channel_id, user_id),
            FOREIGN KEY (channel_id) REFERENCES channels(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            author_id INTEGER,
            parent_id INTEGER,
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            deleted_at TEXT,
            FOREIGN KEY (channel_id) REFERENCES channels(id),
            FOREIGN KEY (author_id) REFERENCES users(id),
            FOREIGN KEY (parent_id) REFERENCES messages(id)
        )
    """)
    
    conn.commit()
    conn.close()
    
def insert_test_user():
    """Добавить одного тестового пользователя (для проверки таблицы)."""
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, 'user')",
        ("testuser", "placeholder_hash"),
    )
    conn.commit()
    conn.close()

def show_table():
    """
    Вернуть содержимое таблицы users как список строк.
    Удобно вызывать из консоли: print(show_table()).
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]    