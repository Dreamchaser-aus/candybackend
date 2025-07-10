import os
import psycopg2
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime
from dotenv import load_dotenv
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps
from flask_babel import Babel, _

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True)

ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS = os.getenv("ADMIN_PASS")
app.secret_key = os.getenv("SECRET_KEY")
app.config['BABEL_DEFAULT_LOCALE'] = 'zh'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'

babel = Babel(app)

# ---- 兼容 Railway 的多语言选择器 ----
@babel.localeselector
def get_locale():
    # 优先 URL 参数 ?lang=，其次浏览器请求头，默认中文
    return request.args.get('lang') or request.accept_languages.best_match(['zh', 'en']) or 'zh'
# ------------------------------------

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

            # 确保 token 字段存在，并且为 INTEGER 类型，默认 5
            c.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='users' AND column_name='token'
                    ) THEN
                        ALTER TABLE users ADD COLUMN token INTEGER DEFAULT 5;
                    END IF;
                END
                $$;
            """)

            # 确保 invited_rewarded 字段存在
            c.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='users' AND column_name='invited_rewarded'
                    ) THEN
                        ALTER TABLE users ADD COLUMN invited_rewarded BOOLEAN DEFAULT FALSE;
                    END IF;
                END
                $$;
            """)

            # 创建 game_logs 表（含 game_name 字段）
            c.execute("""
                CREATE TABLE IF NOT EXISTS game_logs (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    user_roll INTEGER,
                    bot_roll INTEGER,
                    result TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    game_name TEXT
                );
            """)

            # 确保 game_logs 表中 game_name 字段存在
            c.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='game_logs' AND column_name='game_name'
                    ) THEN
                        ALTER TABLE game_logs ADD COLUMN game_name TEXT;
                    END IF;
                END
                $$;
            """)

            # ✅ 创建 token_logs 表
            c.execute("""
                CREATE TABLE IF NOT EXISTS token_logs (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    change INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            conn.commit()
    print("✅ 数据表初始化完成")

def daily_token_update():
    with get_conn() as conn:
        with conn.cursor() as c:
            # 加锁，确保同一时间只执行一次
            c.execute("SELECT pg_try_advisory_lock(123456789)")
            locked = c.fetchone()[0]
            if not locked:
                print("⚠️ 已有其他任务在执行，跳过本次 token 更新")
                return

            c.execute("SELECT user_id, COALESCE(token, 0) FROM users")
            users = c.fetchall()

            for user_id, current_token in users:
                new_token = min(current_token + 2, 20)
                c.execute("UPDATE users SET token = %s WHERE user_id = %s", (new_token, user_id))
                c.execute("""
                    INSERT INTO token_logs (user_id, change, reason)
                    VALUES (%s, %s, %s)
                """, (user_id, 2, 'daily_bonus'))

            conn.commit()
            print("✅ 每日 token 补充完成并记录日志")

# 定时任务（只在主进程中启动）
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
scheduler.add_job(daily_token_update, 'cron', hour=0, minute=0)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USER and password == ADMIN_PASS:
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        else:
            error = "用户名或密码错误"
    return render_template("admin_login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))
    
@app.route("/admin")
@admin_required
def admin():
    keyword = request.args.get("q", "")
    filter_blocked = request.args.get("filter")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    # 分页参数
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))

    # 拼装WHERE
    where_clauses = ["TRUE"]
    params = []
    if keyword:
        where_clauses.append("(username ILIKE %s OR phone ILIKE %s OR inviter ILIKE %s)")
        params += [f"%{keyword}%"] * 3
    if filter_blocked == "1":
        where_clauses.append("blocked = TRUE")
    elif filter_blocked == "0":
        where_clauses.append("blocked IS FALSE")
    if start_date:
        where_clauses.append("created_at >= %s")
        params.append(start_date)
    if end_date:
        where_clauses.append("created_at <= %s")
        params.append(end_date)
    where = " AND ".join(where_clauses)

    # 查询总数
    count_query = f"SELECT COUNT(*) FROM users WHERE {where}"
    user_query = f"SELECT * FROM users WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s"

    with get_conn() as conn:
        with conn.cursor() as c:
            # 获取总用户数
            c.execute(count_query, params)
            total = c.fetchone()[0]
            total_pages = (total + page_size - 1) // page_size if total else 1
            # 分页查询用户
            c.execute(user_query, params + [page_size, (page-1)*page_size])
            rows = c.fetchall()
            users = [dict(zip([desc[0] for desc in c.description], row)) for row in rows]
            # 查询被邀请人数和当日最高分
            for user in users:
                c.execute("SELECT COUNT(*) FROM users WHERE inviter = %s", (str(user["user_id"]),))
                user["invited_count"] = c.fetchone()[0]
                c.execute("""
                    SELECT MAX(user_roll)
                    FROM game_logs
                    WHERE user_id = %s AND timestamp::date = CURRENT_DATE
                """, (user["user_id"],))
                user["daily_max_score"] = c.fetchone()[0] or 0

            # 数据统计
            c.execute("SELECT COUNT(*) FROM users")
            total_all = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE phone IS NOT NULL")
            verified = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE blocked = TRUE")
            blocked = c.fetchone()[0]
            c.execute("SELECT SUM(points) FROM users")
            points = c.fetchone()[0] or 0

    stats = {"total": total_all, "verified": verified, "blocked": blocked, "points": points}

    # 拼接保留的搜索参数用于分页跳转
    qstr = ""
    for k in ["q", "start_date", "end_date", "filter"]:
        v = request.args.get(k, "")
        if v:
            qstr += f"&{k}={v}"

    return render_template(
        "admin.html",
        users=users,
        stats=stats,
        request=request,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        qstr=qstr,
        keyword=keyword,
    )
    
@app.route("/api/user_info", methods=["GET"])
def user_info():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "缺少 user_id"}), 400
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT username, phone, points, COALESCE(token, '0'), COALESCE(plays, 0) FROM users WHERE user_id = %s", (user_id,))
            row = c.fetchone()
            if row:
                return jsonify({
                    "status": "ok",
                    "user_id": user_id,
                    "username": row[0],
                    "phone": row[1],
                    "points": row[2] or 0,
                    "token": int(row[3]) if row[3] else 0,
                    "plays": row[4] or 0,
                })
            else:
                return jsonify({"status": "not_found"}), 404

@app.route("/user/logs")
def user_logs():
    user_id = request.args.get("user_id")
    page = int(request.args.get("page", 1))
    page_size = 20

    # 新增的日期筛选参数
    range_filter = request.args.get("range", "")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    where_clauses = ["user_id = %s"]
    params = [user_id]

    # 根据 range 参数生成日期条件
    if range_filter == "today":
        where_clauses.append("timestamp::date = CURRENT_DATE")
    elif range_filter == "this_week":
        where_clauses.append("timestamp >= date_trunc('week', CURRENT_DATE)")
    elif range_filter == "this_month":
        where_clauses.append("timestamp >= date_trunc('month', CURRENT_DATE)")
    elif range_filter == "custom":
        if start_date:
            where_clauses.append("timestamp::date >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("timestamp::date <= %s")
            params.append(end_date)
    # 全部 (不加额外条件)

    where_sql = " AND ".join(where_clauses)

    with get_conn() as conn:
        with conn.cursor() as c:
            # 游戏记录总数
            c.execute(f"SELECT COUNT(*) FROM game_logs WHERE {where_sql}", params)
            total = c.fetchone()[0]
            total_pages = (total + page_size - 1) // page_size if total else 1

            # 游戏记录
            c.execute(f"""
                SELECT * FROM game_logs
                WHERE {where_sql}
                ORDER BY timestamp DESC
                LIMIT %s OFFSET %s
            """, params + [page_size, (page - 1) * page_size])
            logs = [dict(zip([desc[0] for desc in c.description], row)) for row in c.fetchall()]

            # Token 日志
            c.execute("SELECT * FROM token_logs WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
            token_logs = [dict(zip([desc[0] for desc in c.description], row)) for row in c.fetchall()]

    return render_template(
        "user_logs.html",
        logs=logs,
        token_logs=token_logs,
        user_id=user_id,
        page=page,
        total_pages=total_pages,
        range=range_filter,
        start_date=start_date,
        end_date=end_date
    )
    
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
    from datetime import datetime
    # 获取前端选定日期（默认为今天）
    date_str = request.args.get("date")
    if not date_str:
        date = datetime.now().date()
        date_str = date.strftime("%Y-%m-%d")
    else:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()

    with get_conn() as conn:
        with conn.cursor() as c:
            # 查该日每用户积分总和并关联用户基本信息
            c.execute("""
                SELECT
                    u.user_id,
                    u.username,
                    u.phone,
                    u.created_at,
                    u.last_game_time,
                    COALESCE(SUM(g.user_roll), 0) as day_points
                FROM users u
                LEFT JOIN game_logs g ON u.user_id = g.user_id AND g.timestamp::date = %s
                GROUP BY u.user_id, u.username, u.phone, u.created_at, u.last_game_time
                ORDER BY day_points DESC
                LIMIT 20
            """, (date_str,))
            users = [
                {
                    "user_id": row[0],
                    "username": row[1],
                    "phone": row[2],
                    "created_at": row[3],
                    "last_game_time": row[4],
                    "points": row[5]
                }
                for row in c.fetchall()
            ]

    return render_template("rank_today.html", users=users, date=date_str)

@app.route("/user/save", methods=["POST"])
def save_user():
    data = request.get_json()
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                UPDATE users SET blocked = %s, points = %s, plays = %s, token = %s
                WHERE user_id = %s
            """, (
                data.get("blocked", False),
                data.get("points", 0),
                data.get("plays", 0),
                data.get("token", 0),        # 新增！保存token
                data["user_id"]
            ))
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
    try:
        user_id = request.form.get("user_id")
        score_str = request.form.get("score", "0")
        game_name = request.form.get("game_name", "骰子对赌")

        if not user_id:
            return jsonify({"error": "缺少 user_id"}), 400

        try:
            score = int(score_str)
        except:
            return jsonify({"error": f"score字段格式错误，收到: {score_str}"}), 400

        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute("SELECT points, plays, COALESCE(token, 0) FROM users WHERE user_id = %s", (user_id,))
                result = c.fetchone()
                if not result:
                    return jsonify({"error": "用户不存在"}), 404

                old_points, old_plays, old_token = result
                new_points = (old_points or 0) + score
                new_plays = (old_plays or 0) + 1
                new_token = max((old_token or 0) - 1, 0)

                # 更新用户表
                c.execute("UPDATE users SET points = %s, plays = %s, last_game_time = NOW(), token = %s WHERE user_id = %s",
                          (new_points, new_plays, new_token, user_id))

                # 插入游戏日志
                c.execute("""
                    INSERT INTO game_logs (user_id, user_roll, bot_roll, result, timestamp, game_name)
                    VALUES (%s, %s, %s, %s, NOW(), %s)
                """, (user_id, score, 0, '游戏结束', game_name))

                # 插入 token 日志
                c.execute("""
                    INSERT INTO token_logs (user_id, change, reason)
                    VALUES (%s, %s, %s)
                """, (user_id, -1, 'game_play'))

                conn.commit()

                c.execute("SELECT username, phone, points, COALESCE(token, 0) FROM users WHERE user_id = %s", (user_id,))
                user = c.fetchone()
                data = {
                    "username": user[0],
                    "phone": user[1],
                    "points": user[2],
                    "score": score,
                    "result": "提交成功",
                    "token": user[3]
                }
        return jsonify(data)

    except Exception as e:
        import traceback
        print("❌ /play接口报错:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
        
@app.route("/api/rank")
def api_rank():
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT user_id, username, phone, points
                FROM users
                ORDER BY points DESC
                LIMIT 10
            """)
            results = [
                {
                    "user_id": row[0],
                    "username": row[1],
                    "phone": row[2],
                    "points": row[3]
                }
                for row in c.fetchall()
            ]
    return jsonify(results)

@app.route("/api/rank/today", methods=["GET"])
def api_rank_today():
    from datetime import datetime
    date_str = request.args.get("date")
    if not date_str:
        date = datetime.now().date()
        date_str = date.strftime("%Y-%m-%d")
    else:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()

    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT
                    u.user_id,
                    u.username,
                    u.phone,
                    COALESCE(MAX(g.user_roll), 0) as max_score
                FROM users u
                LEFT JOIN game_logs g ON u.user_id = g.user_id AND g.timestamp::date = %s
                GROUP BY u.user_id, u.username, u.phone
                ORDER BY max_score DESC
                LIMIT 20
            """, (date_str,))
            users = [
                {
                    "user_id": row[0],
                    "username": row[1],
                    "phone": row[2],
                    "max_score": row[3]
                }
                for row in c.fetchall()
            ]

    return jsonify(users)

@app.route("/user/bind", methods=["POST"])
def user_bind():
    data = request.get_json()
    user_id = data.get("user_id")
    phone = data.get("phone")
    username = data.get("username", "")
    inviter = data.get("inviter")  # 新增参数

    if not user_id or not phone:
        return jsonify({"status": "error", "message": "参数不全"}), 400

    with get_conn() as conn:
        with conn.cursor() as c:
            # 检查该用户是否是新用户（没有注册过）
            c.execute("SELECT invited_rewarded FROM users WHERE user_id = %s", (user_id,))
            row = c.fetchone()
            is_new_user = row is None

            # 不能自己邀请自己
            if inviter and str(user_id) == str(inviter):
                inviter = None

            # 新用户且有邀请人时，给邀请人奖励，并标记该用户已经奖励过邀请人
            if is_new_user and inviter:
                # 给邀请人加3 token
                c.execute("UPDATE users SET token = COALESCE(token,0) + 3 WHERE user_id = %s", (inviter,))
                # 插入新用户，标记已奖励
                c.execute("""
                    INSERT INTO users (user_id, phone, username, inviter, token, invited_rewarded)
                    VALUES (%s, %s, %s, %s, 5, TRUE)
                """, (user_id, phone, username, inviter))
            else:
                # 老用户或没有邀请人，正常写入/更新
                c.execute("""
                    INSERT INTO users (user_id, phone, username, inviter)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET phone=EXCLUDED.phone, username=EXCLUDED.username, inviter=EXCLUDED.inviter
                """, (user_id, phone, username, inviter))
            conn.commit()
    return jsonify({"status": "ok"})
    
@app.route("/api/check_bind", methods=["GET"])
def check_bind():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "缺少 user_id"}), 400
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT phone FROM users WHERE user_id = %s", (user_id,))
            row = c.fetchone()
            if row and row[0]:
                return jsonify({"status": "ok"})
            else:
                return jsonify({"status": "not_bind"}), 401


@app.template_filter('format_datetime')
def format_datetime(value):
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")

@app.route("/api/profile", methods=["GET"])
def profile():
    return user_info()

@app.route("/init")
def run_init_tables():
    try:
        init_tables()
        return "✅ 数据表已初始化/更新", 200
    except Exception as e:
        return f"❌ 初始化失败: {e}", 500


if __name__ == "__main__":
    init_tables()  # 自动建表
    scheduler.start()  # ✅ 确保只在主进程启动 scheduler
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
