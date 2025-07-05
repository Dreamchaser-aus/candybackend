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

-- 游戏记录表：记录每一次掷骰子的对局
CREATE TABLE IF NOT EXISTS game_logs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    user_roll INTEGER,
    bot_roll INTEGER,
    result TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    game_name TEXT  -- 新增：游戏名称字段，兼容多种游戏
);

-- 兼容老表自动加字段（如老库未加 game_name 字段时也能自适应）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='game_logs' AND column_name='game_name'
    ) THEN
        ALTER TABLE game_logs ADD COLUMN game_name TEXT;
    END IF;
END$$;
