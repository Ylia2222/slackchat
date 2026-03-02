from werkzeug.security import check_password_hash, generate_password_hash

import sqlite3

from flask import Flask, render_template, session, request, url_for, redirect

app = Flask(__name__)
app.secret_key = "dev-secret"
DB_PATH = "database.db"

def current_user():
    """Возвращает строку текущего пользователя (dict-like) или None."""
    uid = session.get("user_id")
    if uid is None:
        return None
    conn = get_conn()
    user = conn.execute(
        "SELECT id, username, role FROM users WHERE id = ? AND archived_at IS NULL",
        (uid,),
    ).fetchone()
    conn.close()
    return user

@app.route("/", methods=["GET", "POST"])
def home():
    conn = get_conn()
    row = conn.execute("SELECT 1 AS ok").fetchone()
    rows = conn.execute("SELECT * FROM users")
    for r in rows:
        print(dict(r))
    conn.close()
    return render_template(
        "index.html",
        db_ok=row is not None and row["ok"] == 1,
        current_user=current_user,
    )
    
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('registration_open', '0')"
        )
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'admin')),
                archived_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        
def ensure_master():
    """Создать пользователя master (admin), если ещё нет ни одного admin."""
    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    if row is not None:
        conn.close()
        return
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
        ("master", generate_password_hash("master")),
    )
    conn.commit()
    conn.close()
    
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "user_id" in session:
            return redirect("/") 
        next_url = request.args.get("next")
        return render_template("login.html", next=next_url)
    
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    
    if not username or not password:
        return render_template("login.html", error="Введите логин и пароль"), 400
    
    conn = get_conn()
    user = conn.execute(
        "SELECT id, password_hash, role FROM users WHERE username = ? AND archived_at IS NULL",
        (username,)
    ).fetchone()
    conn.close()
    
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Неверный логин или пароль"), 401
    
    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"] 
    
    next_url = request.form.get("next") or request.args.get("next") or ("/")
    return redirect(next_url)
    
    
@app.get("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    init_db()
    ensure_master()
    app.run(debug=True)