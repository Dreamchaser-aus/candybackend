-- ===========================
-- 用户表：存储用户基本信息
-- ===========================
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

-- ===========================
-- 添加 token 字段（如未有则加，默认 5）
-- ===========================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'token'
    ) THEN
        ALTER TABLE users ADD COLUMN token INTEGER DEFAULT 5;
    END IF;
END$$;

-- ===========================
-- 添加 invited_rewarded 字段（防刷奖励标记）
-- ===========================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'invited_rewarded'
    ) THEN
        ALTER TABLE users ADD COLUMN invited_rewarded BOOLEAN DEFAULT FALSE;
    END IF;
END$$;

-- ===========================
-- 游戏记录表
-- ===========================
CREATE TABLE IF NOT EXISTS game_logs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    user_roll INTEGER,
    bot_roll INTEGER,
    result TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    game_name TEXT
);

-- ===========================
-- 兼容旧 game_logs（补 game_name）
-- ===========================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'game_logs' AND column_name = 'game_name'
    ) THEN
        ALTER TABLE game_logs ADD COLUMN game_name TEXT;
    END IF;
END$$;

-- ===========================
-- Token 日志表（新建）
-- ===========================
CREATE TABLE IF NOT EXISTS token_logs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    change INTEGER,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
