from auth_utils import (
    create_user,
    ensure_master,
    is_logged_in,
    current_user,
    is_admin,
    get_registration_open,
)

from flask import Flask, render_template, session, abort, request, url_for, redirect, flash

from db import get_conn, init_db, insert_test_user, show_table

def admin_settings_view():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)
    return render_template("admin_settings.html", registration_open=get_registration_open())

def admin_settings_save_view():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)
    open_val = "1" if request.form.get("registration_open") == "on" else "0"
    conn = get_conn()
    conn.execute("REPLACE INTO settings (key, value) VALUES ('registration_open', ?)", (open_val,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_settings"))

def admin_users_view():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)

    conn = get_conn()
    users = conn.execute(
        """
        SELECT id, username, role, archived_at, created_at
        FROM users
        ORDER BY archived_at IS NULL DESC, username
        """
    ).fetchall()
    conn.close()

    return render_template("admin_users.html", users=users)

def admin_user_create_view():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    if not username or not password:
        flash("Введите логин и пароль.")
        return redirect(url_for("admin_users"))

    if len(username) < 2:
        flash("Логин слишком короткий.")
        return redirect(url_for("admin_users"))

    try:
        # В универсальном варианте создаём пользователей с ролью 'user'
        create_user(username, password, "user")
        flash(f"Пользователь {username} создан.")
    except sqlite3.IntegrityError:
        flash("Такой логин уже занят.")

    return redirect(url_for("admin_users"))

def admin_user_archive_view(user_id):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)

    conn = get_conn()
    u = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if u is None:
        conn.close()
        abort(404)

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute("UPDATE users SET archived_at = ? WHERE id = ?", (now, user_id))
    conn.commit()
    conn.close()

    flash("Пользователь заархивирован. Он больше не сможет войти.")
    return redirect(url_for("admin_users"))
def admin_user_restore_view(user_id):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)

    conn = get_conn()
    u = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if u is None:
        conn.close()
        abort(404)

    conn.execute("UPDATE users SET archived_at = NULL WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash("Пользователь восстановлен.")
    return redirect(url_for("admin_users"))

def admin_user_delete_view(user_id):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)

    conn = get_conn()
    u = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if u is None:
        conn.close()
        abort(404)

    if u["role"] == "admin":
        # Мастер‑аккаунт удалять нельзя
        conn.close()
        flash("Нельзя удалить мастер‑аккаунт.")
        return redirect(url_for("admin_users"))

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash(f"Пользователь {u['username']} удалён безвозвратно.")
    return redirect(url_for("admin_users"))