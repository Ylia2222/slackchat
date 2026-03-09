from flask import render_template, request, redirect, url_for, session, abort, flash

from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from auth_utils import is_logged_in, current_user, is_admin, get_registration_open, create_user

from db import get_conn

def login_form_view():
    if is_logged_in():
        return redirect(url_for("home"))
    return render_template("login.html", error=None)
    
def login_view():
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
    
def logout_view():
    session.clear()
    return redirect(url_for("home"))
    
def register_form_view():
    if session.get("user_id") is not None:
        return redirect(url_for("dashboard"))
    if not get_registration_open():
        return render_template("register.html", registration_disabled=True), 403
    return render_template("register.html")
    
def register_view():
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
    
def dashboard_view():    
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login_form"))

    return render_template("dashboard.html", user=user)

