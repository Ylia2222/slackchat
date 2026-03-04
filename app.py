from werkzeug.security import check_password_hash, generate_password_hash

import sqlite3

from flask import Flask, render_template, session, abort, request, url_for, redirect

app = Flask(__name__)
app.secret_key = "dev-secret"
DB_PATH = "database.db"

def is_master():
    user = current_user()
    return user is not None and user["role"] == "admin"

def is_agent():
    user = current_user()
    return user is not None and user["role"] == "agent"


def is_logged_in():
    return session.get("user_id") is not None

def current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None

    conn = get_conn()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ? AND archived_at IS NULL",
        (user_id,),
    ).fetchone()
    conn.close()

    return user

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
    
    conn.commit()
    conn.close()
    
def get_registration_open():
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'registration_open'").fetchone()
    conn.close()
    return row is not None and row["value"] == "1"
    
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
        
def ensure_master():
    """
    Убедиться, что в системе есть хотя бы один администратор.
    Если нет — создать пользователя master/master с ролью admin.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM users WHERE role = 'admin' AND archived_at IS NULL LIMIT 1"
    ).fetchone()

    if row is None:
        create_user("master", "master", "admin")

    conn.close()
    
def create_user(username, password, role):
    """
    Создать пользователя с указанным логином, паролем и ролью.
    На этом этапе пароль сохраняется как есть (будем улучшать позже).
    """
    password_hash = generate_password_hash(password)
    
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
        (username, password_hash, role),
    )
    conn.commit()
    conn.close()    
    
@app.route("/")
def home():
    if not is_logged_in():
        return redirect(url_for("login_form"))
    conn = get_conn()
    row = conn.execute("SELECT 1 AS ok").fetchone()
    conn.close()

    db_ok = row is not None and row["ok"] == 1
    user = current_user()
    
    return render_template("home.html", db_ok=db_ok)
@app.get("/login")
def login_form():
    if is_logged_in():
        return redirect(url_for("home"))
    return render_template("login.html", error=None)


@app.post("/login")
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        return render_template(
            "login.html",
            error="Введите логин и пароль.",
        )

    conn = get_conn()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? AND archived_at IS NULL LIMIT 1",
        (username,),
    ).fetchone()
    conn.close()

    if user is None:
        return render_template(
            "login.html",
            error="Пользователь не найден.",
        )

    if not check_password_hash(user["password"], password):
        return render_template(
            "login.html",
            error="Неверный пароль.",
        )
    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]

    return redirect(url_for("dashboard"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.get("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login_form"))

    return render_template("dashboard.html", user=user)

@app.get("/admin/settings")
def admin_settings():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_master():
        abort(403)
    return render_template("admin_settings.html", registration_open=get_registration_open())


@app.post("/admin/settings")
def admin_settings_save():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_master():
        abort(403)
    open_val = "1" if request.form.get("registration_open") == "on" else "0"
    conn = get_conn()
    conn.execute("REPLACE INTO settings (key, value) VALUES ('registration_open', ?)", (open_val,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_settings"))

@app.get("/register")
def register_form():
    if session.get("user_id") is not None:
        return redirect(url_for("dashboard"))
    if not get_registration_open():
        return render_template("register.html", registration_disabled=True), 403
    return render_template("register.html")


@app.post("/register")
def register():
    if not get_registration_open():
        return render_template("register.html", registration_disabled=True), 403
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    if not username or not password:
        return render_template("register.html", error="Username and password required."), 400
    if len(username) < 2:
        return render_template("register.html", error="Username too short."), 400
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'agent')",
            (username, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return render_template("register.html", error="Username already taken."), 409
    conn.close()
    return redirect(url_for("login_form"))

@app.context_processor
def inject():
    return {
        "current_user": current_user,
        "is_master": is_master,
        "is_agent": is_agent,
        "registration_open": get_registration_open(),
    }

if __name__ == "__main__":
    init_db()
    insert_test_user()
    print(show_table())
    ensure_master()
    create_user("test1","123","user")
    app.run(debug=True)