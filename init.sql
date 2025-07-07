-- 用户表：存储用户基本信息
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

-- 如未加 token 字段，则自动添加（默认 10）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'token'
    ) THEN
        ALTER TABLE users ADD COLUMN token INTEGER DEFAULT 10;
    END IF;
END$$;

-- 将已有用户的 token 字段补全（为空或 NULL 时初始化为10）
UPDATE users SET token = 10 WHERE token IS NULL;

-- 游戏记录表：如无则创建，含 game_name 字段
CREATE TABLE IF NOT EXISTS game_logs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    user_roll INTEGER,
    bot_roll INTEGER,
    result TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    game_name TEXT    -- 默认新表有此字段
);

-- 兼容老 game_logs（如无 game_name 字段则补充）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'game_logs' AND column_name = 'game_name'
    ) THEN
        ALTER TABLE game_logs ADD COLUMN game_name TEXT;
    END IF;
END$$;
