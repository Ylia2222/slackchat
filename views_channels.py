import sqlite3

from flask import render_template, redirect, url_for, request, abort, flash, session

from db import get_conn

from auth_utils import is_logged_in, current_user, is_admin

from datetime import datetime

def dashboard_view():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login_form"))

    conn = get_conn()

    my_channels = conn.execute("""
        SELECT c.id, c.name, c.type, c.owner_id, cm.role AS my_role
        FROM channels c
        INNER JOIN channel_members cm ON c.id = cm.channel_id
        WHERE cm.user_id = ?
        ORDER BY c.name
    """, (user["id"],)).fetchall()

    public_joinable = conn.execute("""
        SELECT c.id, c.name, c.type
        FROM channels c
        WHERE c.type = 'public'
          AND NOT EXISTS (
              SELECT 1 FROM channel_members cm
              WHERE cm.channel_id = c.id AND cm.user_id = ?
          )
        ORDER BY c.name
    """, (user["id"],)).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        user=user,
        my_channels=my_channels,
        public_joinable=public_joinable,
    )

def channel_new_view():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    return render_template("channel_new.html", error=None)


def channel_create_view():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    name = (request.form.get("name") or "").strip()
    ctype = request.form.get("type") or "public"

    if not name:
        return render_template("channel_new.html", error="Введите имя канала.")

    if ctype not in ("public", "private", "read_only"):
        ctype = "public"

    user = current_user()
    conn = get_conn()

    try:
        cur = conn.execute(
            "INSERT INTO channels (name, type, owner_id) VALUES (?, ?, ?)",
            (name, ctype, user["id"]),
        )
        channel_id = cur.lastrowid
        conn.execute(
            "INSERT INTO channel_members (channel_id, user_id, role) VALUES (?, ?, 'owner')",
            (channel_id, user["id"]),
        )
        conn.commit()
        conn.close()
        
        flash("Канал создан.")
    except sqlite3.IntegrityError:
        flash("Канал с таким именем уже существует.")

    return redirect(url_for("dashboard"))

def channel_view_view(channel_id: int):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    conn = get_conn()

    ch = conn.execute("""
        SELECT
            c.id,
            c.name,
            c.type,
            c.owner_id,
            c.created_at,
            u.username AS owner_name
        FROM channels c
        LEFT JOIN users u ON c.owner_id = u.id
        WHERE c.id = ?
    """, (channel_id,)).fetchone()

    if ch is None:
        conn.close()
        abort(404)

    # Приватный канал — только участники или админ
    if ch["type"] == "private":
        if not is_admin():
            member = conn.execute(
                "SELECT 1 FROM channel_members WHERE channel_id = ? AND user_id = ?",
                (channel_id, user["id"]),
            ).fetchone()
            if not member:
                conn.close()
                abort(403)

    # Роль текущего пользователя в канале (для шаблона: владелец, участник, только чтение, не в канале)
    membership = conn.execute(
        "SELECT role FROM channel_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, user["id"]),
    ).fetchone()
    my_role = membership["role"] if membership else None

    # Список тредов (корневых сообщений) канала — для блока «Сообщения»
    thread_starters = conn.execute("""
        SELECT m.id, m.content, m.author_id, m.created_at, m.deleted_at,
               u.username AS author_name
        FROM messages m
        LEFT JOIN users u ON m.author_id = u.id
        WHERE m.channel_id = ? AND m.parent_id IS NULL
        ORDER BY m.created_at DESC
    """, (channel_id,)).fetchall()

    # Выбранный тред (из query-параметра ?thread=id)
    selected_thread = None
    thread_replies = []
    can_delete_thread = False

    thread_id_param = request.args.get("thread")
    if thread_id_param:
        try:
            tid = int(thread_id_param)
            row = conn.execute("""
                SELECT m.id, m.content, m.author_id, m.created_at, m.deleted_at,
                       u.username AS author_name
                FROM messages m
                LEFT JOIN users u ON m.author_id = u.id
                WHERE m.id = ? AND m.channel_id = ? AND m.parent_id IS NULL
            """, (tid, channel_id)).fetchone()
            if row:
                selected_thread = row
                # Вычисляем can_delete_thread ТУТ, после загрузки selected_thread!
                is_author = (selected_thread["author_id"] == user["id"])
                is_channel_owner = (ch["owner_id"] == user["id"])
                can_delete_thread = is_author or is_channel_owner or is_admin()

                thread_replies = conn.execute("""
                    SELECT m.id, m.content, m.author_id, m.created_at, m.deleted_at,
                           u.username AS author_name
                    FROM messages m
                    LEFT JOIN users u ON m.author_id = u.id
                    WHERE m.parent_id = ?
                    ORDER BY m.created_at ASC
                """, (tid,)).fetchall()
        except (TypeError, ValueError):
            pass

    can_post = my_role in ("member", "owner") or is_admin()
    
      # Список участников канала (id, username, role) — для блока «Участники»
    members = conn.execute("""
        SELECT u.id AS user_id, u.username, cm.role
        FROM channel_members cm
        INNER JOIN users u ON u.id = cm.user_id
        WHERE cm.channel_id = ?
        ORDER BY cm.role = 'owner' DESC, u.username ASC
    """, (channel_id,)).fetchall()

    # Управление участниками доступно владельцу канала или админу
    can_manage_members = (ch["owner_id"] == user["id"]) or is_admin()

    # Для приглашения: активные пользователи, ещё не в канале (только если показываем блок управления)
    invite_candidates = []
    if can_manage_members:
        invite_candidates = conn.execute("""
            SELECT u.id, u.username
            FROM users u
            WHERE u.archived_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM channel_members cm
                  WHERE cm.channel_id = ? AND cm.user_id = u.id
              )
            ORDER BY u.username
        """, (channel_id,)).fetchall()
        
    conn.close()    
        
    return render_template(
        "channel_view.html",
        channel=ch,
        my_role=my_role,
        members=members,
        can_manage_members=can_manage_members,
        invite_candidates=invite_candidates,
        can_post=can_post,
        thread_starters=thread_starters,
        can_delete_thread=can_delete_thread,
        selected_thread=selected_thread
    )
def channel_join_view(channel_id: int):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    conn = get_conn()

    ch = conn.execute(
        "SELECT id, name, type FROM channels WHERE id = ?",
        (channel_id,),
    ).fetchone()

    if ch is None:
        conn.close()
        abort(404)

    if ch["type"] != "public":
        conn.close()
        flash("Вступить можно только в публичный канал.")
        return redirect(url_for("dashboard"))

    existing = conn.execute(
        "SELECT 1 FROM channel_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, user["id"]),
    ).fetchone()
    if existing:
        conn.close()
        flash("Вы уже в этом канале.")
        return redirect(url_for("channel_view", channel_id=channel_id))

    # Роль при вступлении: в канале типа read_only — read_only, иначе member
    role = "read_only" if ch["type"] == "read_only" else "member"
    conn.execute(
        "INSERT INTO channel_members (channel_id, user_id, role) VALUES (?, ?, ?)",
        (channel_id, user["id"], role),
    )
    conn.commit()
    conn.close()

    flash("Вы вступили в канал.")
    return redirect(url_for("channel_view", channel_id=channel_id))

def channel_leave_view(channel_id: int):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    conn = get_conn()

    ch = conn.execute(
        "SELECT id, name, owner_id FROM channels WHERE id = ?",
        (channel_id,),
    ).fetchone()

    if ch is None:
        conn.close()
        abort(404)

    member = conn.execute(
        "SELECT role FROM channel_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, user["id"]),
    ).fetchone()

    if member is None:
        conn.close()
        flash("Вы не состоите в этом канале.")
        return redirect(url_for("dashboard"))

    # Удаляем пользователя из участников
    conn.execute(
        "DELETE FROM channel_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, user["id"]),
    )

    # Если выходил владелец — передаём владение или обнуляем owner_id
    if ch["owner_id"] == user["id"]:
        new_owner = conn.execute("""
            SELECT user_id FROM channel_members
            WHERE channel_id = ?
            ORDER BY role = 'member' DESC, user_id ASC
            LIMIT 1
        """, (channel_id,)).fetchone()

        if new_owner:
            conn.execute(
                "UPDATE channels SET owner_id = ? WHERE id = ?",
                (new_owner["user_id"], channel_id),
            )
            conn.execute(
                "UPDATE channel_members SET role = 'owner' WHERE channel_id = ? AND user_id = ?",
                (channel_id, new_owner["user_id"]),
            )
        else:
            conn.execute(
                "UPDATE channels SET owner_id = NULL WHERE id = ?",
                (channel_id,),
            )

    conn.commit()
    conn.close()

    flash("Вы вышли из канала.")
    return redirect(url_for("dashboard"))

def channel_invite_view(channel_id: int):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    conn = get_conn()

    ch = conn.execute(
        "SELECT id, name, type, owner_id FROM channels WHERE id = ?",
        (channel_id,),
    ).fetchone()

    if ch is None:
        conn.close()
        abort(404)

    # Приглашать могут только владелец или админ
    if ch["owner_id"] != user["id"] and not is_admin():
        conn.close()
        abort(403)

    invited_id = request.form.get("user_id")
    if not invited_id:
        conn.close()
        flash("Выберите пользователя.")
        return redirect(url_for("channel_view", channel_id=channel_id))

    try:
        invited_id = int(invited_id)
    except (TypeError, ValueError):
        conn.close()
        flash("Некорректный пользователь.")
        return redirect(url_for("channel_view", channel_id=channel_id))

    # Пользователь должен существовать, быть активным и не состоять в канале
    invited = conn.execute(
        "SELECT id FROM users WHERE id = ? AND archived_at IS NULL",
        (invited_id,),
    ).fetchone()
    if not invited:
        conn.close()
        flash("Пользователь не найден или архивирован.")
        return redirect(url_for("channel_view", channel_id=channel_id))

    existing = conn.execute(
        "SELECT 1 FROM channel_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, invited_id),
    ).fetchone()
    if existing:
        conn.close()
        flash("Пользователь уже в канале.")
        return redirect(url_for("channel_view", channel_id=channel_id))

    role = "read_only" if ch["type"] == "read_only" else "member"
    conn.execute(
        "INSERT INTO channel_members (channel_id, user_id, role) VALUES (?, ?, ?)",
        (channel_id, invited_id, role),
    )
    conn.commit()
    conn.close()

    flash("Пользователь приглашён в канал.")
    return redirect(url_for("channel_view", channel_id=channel_id))

def channel_remove_member_view(channel_id: int, user_id: int):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    current = current_user()
    conn = get_conn()

    ch = conn.execute(
        "SELECT id, name, owner_id FROM channels WHERE id = ?",
        (channel_id,),
    ).fetchone()

    if ch is None:
        conn.close()
        abort(404)

    # Удалять участников могут только владелец или админ
    if ch["owner_id"] != current["id"] and not is_admin():
        conn.close()
        abort(403)

    member = conn.execute(
        "SELECT role FROM channel_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, user_id),
    ).fetchone()

    if member is None:
        conn.close()
        flash("Пользователь не состоит в этом канале.")
        return redirect(url_for("channel_view", channel_id=channel_id))

    conn.execute(
        "DELETE FROM channel_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, user_id),
    )

    # Если удалённый был владельцем — передаём владение или обнуляем owner_id
    if ch["owner_id"] == user_id:
        new_owner = conn.execute("""
            SELECT user_id FROM channel_members
            WHERE channel_id = ?
            ORDER BY role = 'member' DESC, user_id ASC
            LIMIT 1
        """, (channel_id,)).fetchone()

        if new_owner:
            conn.execute(
                "UPDATE channels SET owner_id = ? WHERE id = ?",
                (new_owner["user_id"], channel_id),
            )
            conn.execute(
                "UPDATE channel_members SET role = 'owner' WHERE channel_id = ? AND user_id = ?",
                (channel_id, new_owner["user_id"]),
            )
        else:
            conn.execute(
                "UPDATE channels SET owner_id = NULL WHERE id = ?",
                (channel_id,),
            )

    conn.commit()
    conn.close()

    flash("Участник удалён из канала.")
    return redirect(url_for("channel_view", channel_id=channel_id))

def thread_create_view(channel_id: int):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    conn = get_conn()

    ch = conn.execute(
        "SELECT id, name, type, owner_id FROM channels WHERE id = ?",
        (channel_id,),
    ).fetchone()

    if ch is None:
        conn.close()
        abort(404)

    # Доступ к каналу: приватный — только участник или админ
    if ch["type"] == "private" and not is_admin():
        member = conn.execute(
            "SELECT 1 FROM channel_members WHERE channel_id = ? AND user_id = ?",
            (channel_id, user["id"]),
        ).fetchone()
        if not member:
            conn.close()
            abort(403)

    # Писать могут member, owner или админ
    membership = conn.execute(
        "SELECT role FROM channel_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, user["id"]),
    ).fetchone()
    if not membership and not is_admin():
        conn.close()
        flash("Вы не состоите в канале.")
        return redirect(url_for("channel_view", channel_id=channel_id))
    if membership and membership["role"] == "read_only" and not is_admin():
        conn.close()
        abort(403)

    content = (request.form.get("content") or "").strip()
    if not content:
        conn.close()
        flash("Введите текст сообщения.")
        return redirect(url_for("channel_view", channel_id=channel_id))

    cur = conn.execute(
        "INSERT INTO messages (channel_id, author_id, parent_id, content) VALUES (?, ?, NULL, ?)",
        (channel_id, user["id"], content),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()

    flash("Тред создан.")
    return redirect(url_for("channel_view", channel_id=channel_id, thread=new_id))

def message_delete_view(channel_id: int, message_id: int):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    conn = get_conn()

    ch = conn.execute(
        "SELECT id, owner_id FROM channels WHERE id = ?",
        (channel_id,),
    ).fetchone()

    if ch is None:
        conn.close()
        abort(404)

    msg = conn.execute(
        "SELECT id, author_id, parent_id FROM messages WHERE id = ? AND channel_id = ?",
        (message_id, channel_id),
    ).fetchone()

    if msg is None:
        conn.close()
        abort(404)

    # Удалять могут автор, владелец канала или админ
    if msg["author_id"] != user["id"] and ch["owner_id"] != user["id"] and not is_admin():
        conn.close()
        abort(403)

    conn.execute(
        "UPDATE messages SET deleted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), content = '' WHERE id = ?",
        (message_id,),
    )
    conn.commit()
    conn.close()

    flash("Сообщение удалено.")
    return redirect(url_for("channel_view", channel_id=channel_id))

def message_delete_view(channel_id: int, message_id: int):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    conn = get_conn()

    ch = conn.execute(
        "SELECT id, owner_id FROM channels WHERE id = ?",
        (channel_id,),
    ).fetchone()

    if ch is None:
        conn.close()
        abort(404)

    msg = conn.execute(
        "SELECT id, author_id, parent_id FROM messages WHERE id = ? AND channel_id = ?",
        (message_id, channel_id),
    ).fetchone()

    if msg is None:
        conn.close()
        abort(404)

    # Удалять могут автор, владелец канала или админ
    if msg["author_id"] != user["id"] and ch["owner_id"] != user["id"] and not is_admin():
        conn.close()
        abort(403)

    conn.execute(
        "UPDATE messages SET deleted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), content = '' WHERE id = ?",
        (message_id,),
    )
    conn.commit()
    conn.close()

    flash("Сообщение удалено.")
    return redirect(url_for("channel_view", channel_id=channel_id))

def reply_create_view(channel_id: int, parent_id: int):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    conn = get_conn()

    ch = conn.execute(
        "SELECT id, name, type, owner_id FROM channels WHERE id = ?",
        (channel_id,),
    ).fetchone()

    if ch is None:
        conn.close()
        abort(404)

    # Доступ к каналу: приватный — только участник или админ
    if ch["type"] == "private" and not is_admin():
        member = conn.execute(
            "SELECT 1 FROM channel_members WHERE channel_id = ? AND user_id = ?",
            (channel_id, user["id"]),
        ).fetchone()
        if not member:
            conn.close()
            abort(403)

    # Писать могут member, owner или админ
    membership = conn.execute(
        "SELECT role FROM channel_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, user["id"]),
    ).fetchone()
    if not membership and not is_admin():
        conn.close()
        flash("Вы не состоите в канале.")
        return redirect(url_for("channel_view", channel_id=channel_id, thread=parent_id))
    if membership and membership["role"] == "read_only" and not is_admin():
        conn.close()
        abort(403)

    # Родительское сообщение должно быть корневым в этом канале
    parent = conn.execute(
        "SELECT id FROM messages WHERE id = ? AND channel_id = ? AND parent_id IS NULL",
        (parent_id, channel_id),
    ).fetchone()
    if not parent:
        conn.close()
        abort(404)

    content = (request.form.get("content") or "").strip()
    if not content:
        conn.close()
        flash("Введите текст ответа.")
        return redirect(url_for("channel_view", channel_id=channel_id, thread=parent_id))

    conn.execute(
        "INSERT INTO messages (channel_id, author_id, parent_id, content) VALUES (?, ?, ?, ?)",
        (channel_id, user["id"], parent_id, content),
    )
    conn.commit()
    conn.close()

    flash("Ответ добавлен.")
    return redirect(url_for("channel_view", channel_id=channel_id, thread=parent_id))