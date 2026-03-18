from auth_utils import (
    create_user,
    ensure_master,
    is_logged_in,
    current_user,
    is_admin,
    get_registration_open,
)

from views_auth import (
    login_form_view,
    login_view,
    logout_view,
    register_form_view,
    register_view,
)

from views_channels import (
    dashboard_view,
    channel_new_view,
    channel_create_view,
    channel_view_view,
    channel_join_view,
    channel_leave_view,
    channel_invite_view,
    channel_remove_member_view,
    thread_create_view,
    message_delete_view,
    reply_create_view,
)

from views_admin import (
    admin_settings_view,
    admin_settings_save_view,
    admin_users_view,
    admin_user_create_view,
    admin_user_archive_view,
    admin_user_restore_view,
    admin_user_delete_view,
)

from werkzeug.security import check_password_hash, generate_password_hash

import sqlite3

from flask import Flask, render_template, session, abort, request, url_for, redirect, flash

from datetime import datetime

from db import get_conn, init_db, insert_test_user, show_table

app = Flask(__name__)
app.secret_key = "dev-secret"

def is_agent():
    user = current_user()
    return user is not None and user["role"] == "agent"

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
    return login_form_view()

@app.post("/login")
def login():
    return login_view()

@app.get("/logout")
def logout():
    return logout_view()

@app.get("/dashboard")
def dashboard():
    return  dashboard_view()

@app.get("/channels/new")
def channel_new():
    return channel_new_view()


@app.post("/channels/new")
def channel_create():
    return channel_create_view()


@app.get("/channels/<int:channel_id>")
def channel_view(channel_id):
    return channel_view_view(channel_id)

@app.post("/channels/<int:channel_id>/join")
def channel_join(channel_id):
    return channel_join_view(channel_id)

@app.post("/channels/<int:channel_id>/leave")
def channel_leave(channel_id):
    return channel_leave_view(channel_id)

@app.post("/channels/<int:channel_id>/invite")
def channel_invite(channel_id):
    return channel_invite_view(channel_id)

@app.post("/channels/<int:channel_id>/members/<int:user_id>/remove")
def channel_remove_member(channel_id, user_id):
    return channel_remove_member_view(channel_id, user_id)

@app.post("/channels/<int:channel_id>/threads")
def thread_create(channel_id):
    return thread_create_view(channel_id)

@app.post("/channels/<int:channel_id>/messages/<int:message_id>/delete")
def message_delete(channel_id, message_id):
    return message_delete_view(channel_id, message_id)

@app.post("/channels/<int:channel_id>/threads/<int:parent_id>/reply")
def reply_create(channel_id, parent_id):
    return reply_create_view(channel_id, parent_id)

@app.get("/admin/settings")
def admin_settings():
    return admin_settings_view()

@app.post("/admin/settings")
def admin_settings_save():
    return admin_settings_save_view()

@app.get("/register")
def register_form():
    return register_form_view()

@app.post("/register")
def register():
    return register_view()
    
@app.context_processor
def inject():
    return {
        "current_user": current_user,
        "is_admin": is_admin,
        #"is_agent": is_agent,
        "registration_open": get_registration_open(),
    }

@app.get("/admin/users")
def admin_users():
    return admin_users_view()

@app.post("/admin/users/create")
def admin_user_create():
    return admin_user_create_view()

@app.post("/admin/users/<int:user_id>/archive")
def admin_user_archive(user_id):
    return admin_user_archive_view(user_id)

@app.post("/admin/users/<int:user_id>/restore")
def admin_user_restore(user_id):
    return admin_user_restore_view(user_id)

@app.post("/admin/users/<int:user_id>/delete")
def admin_user_delete(user_id):
    return admin_user_delete_view(user_id)

if __name__ == "__main__":
    init_db()
    insert_test_user()
    print(show_table())
    ensure_master()
    create_user("test1","123","user")
    app.run(debug=True)