
import os
import psycopg2
from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/postgres")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_tables():
    with get_conn() as conn:
        with conn.cursor() as c:
            # 创建 users 表
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    phone TEXT,
                    points INTEGER DEFAULT 0,
                    plays INTEGER DEFAULT 0,
                    inviter TEXT,
                    token TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_game_time TIMESTAMP,
                    blocked BOOLEAN DEFAULT FALSE
                );
            """)
            
            # 创建 game_logs 表
            c.execute("""
                CREATE TABLE IF NOT EXISTS game_logs (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    user_roll INTEGER,
                    bot_roll INTEGER,
                    result TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            conn.commit()
    print("✅ 数据表初始化完成")
    
@app.route("/admin")
def admin():
    keyword = request.args.get("q", "")
    filter_blocked = request.args.get("filter")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    query = "SELECT * FROM users WHERE TRUE"
    params = []

    if keyword:
        query += " AND (username ILIKE %s OR phone ILIKE %s OR inviter ILIKE %s)"
        params += [f"%{keyword}%"] * 3
    if filter_blocked == "1":
        query += " AND blocked = TRUE"
    elif filter_blocked == "0":
        query += " AND blocked IS FALSE"
    if start_date:
        query += " AND created_at >= %s"
        params.append(start_date)
    if end_date:
        query += " AND created_at <= %s"
        params.append(end_date)

    query += " ORDER BY created_at DESC"

    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(query, params)
            rows = c.fetchall()
            users = [dict(zip([desc[0] for desc in c.description], row)) for row in rows]

            c.execute("SELECT COUNT(*) FROM users")
            total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE phone IS NOT NULL")
            verified = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE blocked = TRUE")
            blocked = c.fetchone()[0]
            c.execute("SELECT SUM(points) FROM users")
            points = c.fetchone()[0] or 0

    stats = {"total": total, "verified": verified, "blocked": blocked, "points": points}
    return render_template("admin.html", users=users, stats=stats, request=request, keyword=keyword, page=1, total_pages=1)

@app.route("/user/logs")
def user_logs():
    user_id = request.args.get("user_id")
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT * FROM game_logs WHERE user_id = %s ORDER BY timestamp DESC", (user_id,))
            logs = [dict(zip([desc[0] for desc in c.description], row)) for row in c.fetchall()]
    return render_template("user_logs.html", logs=logs, user_id=user_id)

@app.route("/invitees")
def invitees():
    user_id = request.args.get("user_id")
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT * FROM users WHERE inviter = %s", (user_id,))
            invitees = [dict(zip([desc[0] for desc in c.description], row)) for row in c.fetchall()]
    return render_template("invitees.html", invitees=invitees)

@app.route("/admin/rank/today")
def rank_today():
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT * FROM users ORDER BY points DESC LIMIT 100")
            users = [dict(zip([desc[0] for desc in c.description], row)) for row in c.fetchall()]
    return render_template("rank_today.html", users=users)

@app.route("/user/save", methods=["POST"])
def save_user():
    data = request.get_json()
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET blocked = %s, points = %s, plays = %s WHERE user_id = %s",
                      (data["blocked"], data["points"], data["plays"], data["user_id"]))
            conn.commit()
    return jsonify({"status": "ok"})

@app.route("/user/delete", methods=["POST"])
def delete_user():
    data = request.get_json()
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM users WHERE user_id = %s", (data["user_id"],))
            conn.commit()
    return jsonify({"status": "ok"})

@app.route("/")
def index():
    return redirect(url_for("admin"))

@app.route("/mock")
def insert_mock_users():
    with get_conn() as conn:
        with conn.cursor() as c:
            for i in range(1, 11):
                user_id = 100000 + i
                username = f"user{i}"
                phone = f"04123456{i:02d}"
                points = i * 10
                plays = i % 5
                inviter = f"user{(i-1) if i > 1 else ''}" or None
                created_at = datetime.now()
                last_game_time = datetime.now()
                blocked = (i % 3 == 0)

                c.execute("""
                    INSERT INTO users (user_id, username, phone, points, plays, inviter, created_at, last_game_time, blocked)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id, username, phone, points, plays, inviter, created_at, last_game_time, blocked))
            conn.commit()
    return "✅ 已成功插入 10 个模拟用户"

if __name__ == "__main__":
    init_tables()  # 自动建表 ✅
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
