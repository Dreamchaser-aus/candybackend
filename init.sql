-- 1. 用户表：如不存在则创建
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

-- 2. 自动补全 token 字段（如无则添加，默认10）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'token'
    ) THEN
        ALTER TABLE users ADD COLUMN token INTEGER DEFAULT 10;
    END IF;
END$$;

-- 3. 补齐历史数据 token 字段（将 NULL 初始化为10）
UPDATE users SET token = 10 WHERE token IS NULL;

-- 4. 游戏记录表：如不存在则创建（先不含 game_name 字段）
CREATE TABLE IF NOT EXISTS game_logs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    user_roll INTEGER,
    bot_roll INTEGER,
    result TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. 自动补全 game_logs 的 game_name 字段（如无则添加）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'game_logs' AND column_name = 'game_name'
    ) THEN
        ALTER TABLE game_logs ADD COLUMN game_name TEXT;
    END IF;
END$$;

-- 可选：后续如有新字段同理补充
