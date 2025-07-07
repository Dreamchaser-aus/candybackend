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

-- 检查/添加 token 字段（如未有则加，默认5）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'token'
    ) THEN
        ALTER TABLE users ADD COLUMN token INTEGER DEFAULT 5;
    END IF;
END$$;

-- 游戏记录表，含 game_name 字段
CREATE TABLE IF NOT EXISTS game_logs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    user_roll INTEGER,
    bot_roll INTEGER,
    result TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    game_name TEXT
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

-- ----------- 临时升级区块（执行后建议删除）-----------
-- 1. 将空/非法 token 置为5，非数字置为0（不会影响已是数字的正常数据）
UPDATE users SET token = '5' WHERE token IS NULL OR token = '';
UPDATE users SET token = '0' WHERE token !~ '^\d+$';

-- 2. 强制 token 字段类型转换为 integer
ALTER TABLE users ALTER COLUMN token TYPE INTEGER USING token::integer;

-- 3. 设置默认值/非空限制（如已设置可无视）
ALTER TABLE users ALTER COLUMN token SET DEFAULT 5;
ALTER TABLE users ALTER COLUMN token SET NOT NULL;
-- ----------- ↑↑↑ 执行完成后可以删除 -------------------
