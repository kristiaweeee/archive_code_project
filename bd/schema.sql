-- Включение поддержки внешних ключей в SQLite (обязательно для каждой сессии)
PRAGMA foreign_keys = ON;

-- 1. Создание таблицы файлов
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL
);

-- 2. Создание таблицы элементов кода (классы и функции)
CREATE TABLE IF NOT EXISTS code_elements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('class', 'function')),
    line_number INTEGER NOT NULL,
    docstring TEXT,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- 3. Создание индексов для оптимизации поиска в FastAPI
CREATE INDEX IF NOT EXISTS idx_elements_name ON code_elements(name);
CREATE INDEX IF NOT EXISTS idx_elements_type ON code_elements(type);

