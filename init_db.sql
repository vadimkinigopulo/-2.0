REATE TABLE IF NOT EXISTS admins (
    user_id TEXT PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    start_time REAL
);

-- Таблица для старших админов
CREATE TABLE IF NOT EXISTS senior_admins (
    user_id INTEGER PRIMARY KEY
);

-- Таблица для руководства
CREATE TABLE IF NOT EXISTS management (
    user_id INTEGER PRIMARY KEY
);
