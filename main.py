
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_game_time TIMESTAMP,
                    blocked BOOLEAN DEFAULT FALSE
                );
            """)
            
            # 确保 token 字段存在
            c.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                   WHERE table_name='users' AND column_name='token') THEN
                        ALTER TABLE users ADD COLUMN token TEXT;
                    END IF;
                END
                $$;
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

            # ✅ 新增：为每个用户查询被邀请人数
            for user in users:
                c.execute("SELECT COUNT(*) FROM users WHERE inviter = %s", (str(user["user_id"]),))
                user["invited_count"] = c.fetchone()[0]

            # 原来的统计逻辑
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
    
@app.route("/game")
def game():
    return render_template("game.html")

@app.route("/play", methods=["POST"])
def play_game():
    user_id = request.form.get("user_id")
    score = int(request.form.get("score", 0))

    if not user_id:
        return jsonify({"error": "缺少 user_id"}), 400

    with get_conn() as conn:
        with conn.cursor() as c:
            # 查询用户
            c.execute("SELECT points, plays FROM users WHERE user_id = %s", (user_id,))
            result = c.fetchone()
            if not result:
                return jsonify({"error": "用户不存在"}), 404

            old_points, old_plays = result
            new_points = (old_points or 0) + score
            new_plays = (old_plays or 0) + 1

            # ✅ 更新用户积分、次数、时间
            c.execute("UPDATE users SET points = %s, plays = %s, last_game_time = NOW() WHERE user_id = %s",
                      (new_points, new_plays, user_id))

            # ✅ 插入 game_logs 表
            c.execute("""
                INSERT INTO game_logs (user_id, user_roll, bot_roll, result, timestamp)
                VALUES (%s, %s, %s, %s, NOW())
            """, (user_id, score, 0, '游戏结束'))

            conn.commit()

            # 返回用户数据
            c.execute("SELECT username, phone, points FROM users WHERE user_id = %s", (user_id,))
            user = c.fetchone()
            data = {
                "username": user[0],
                "phone": user[1],
                "points": user[2],
                "score": score,
                "result": "提交成功",
                "token": "无"
            }
    return jsonify(data)

@app.template_filter('format_datetime')
def format_datetime(value):
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")

if __name__ == "__main__":
    init_tables()  # 自动建表 ✅
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
