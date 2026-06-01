import os
import ast
import sqlite3

DB_NAME = "database.db"
DATASET_DIR = "dataset"


def initialize_database():
    """Устанавливает соединение с SQLite и формирует структуру таблиц."""
    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    # Включение поддержки ограничений внешних ключей
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Таблица для регистрации проиндексированных файлов
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL UNIQUE
        );
    """
    )

    # Таблица для хранения классов и функций с указанием границ строк и docstring
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS code_elements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('class', 'function')),
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            docstring TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        );
    """
    )

    # Создание индексов для оптимизации поисковых запросов веб-интерфейса
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_elements_name ON code_elements(name);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_elements_type ON code_elements(type);"
    )

    # Очистка таблиц перед началом сессии для предотвращения дублирования данных
    cursor.execute("DELETE FROM code_elements;")
    cursor.execute("DELETE FROM files;")

    connection.commit()
    return connection, cursor


def parse_python_file(file_path):
    """Выполняет чтение файла и его преобразование в абстрактное синтаксическое дерево."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return ast.parse(content)
    except (UnicodeDecodeError, SyntaxError) as e:
        print(f"Пропуск файла {file_path} из-за ошибки обработки: {e}")
        return None


def main():
    if not os.path.exists(DATASET_DIR):
        print(f"Критическая ошибка: Директория '{DATASET_DIR}' не найдена.")
        return

    print("Инициализация базы данных и подготовка схемы...")
    connection, cursor = initialize_database()

    print("Сканирование директории и синтаксический анализ файлов...")
    files_indexed = 0
    elements_indexed = 0

    # Рекурсивный обход целевой директории с датасетом
    for root, _, files in os.walk(DATASET_DIR):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.normpath(os.path.join(root, file))

                tree = parse_python_file(file_path)
                if tree is None:
                    continue

                # Фиксация файла в базе данных и получение его уникального ID
                cursor.execute(
                    "INSERT INTO files (file_name, file_path) VALUES (?, ?);",
                    (file, file_path),
                )
                file_id = cursor.lastrowid
                files_indexed += 1

                # Анализ узлов синтаксического дерева
                for node in ast.walk(tree):
                    if isinstance(
                        node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        element_type = (
                            "class"
                            if isinstance(node, ast.ClassDef)
                            else "function"
                        )

                        name = node.name
                        start_line = node.lineno
                        # Атрибут end_lineno поддерживается в Python 3.8+
                        end_line = getattr(node, "end_lineno", start_line)
                        docstring = ast.get_docstring(node)

                        cursor.execute(
                            """
                            INSERT INTO code_elements (file_id, name, type, start_line, end_line, docstring)
                            VALUES (?, ?, ?, ?, ?, ?);
                        """,
                            (
                                file_id,
                                name,
                                element_type,
                                start_line,
                                end_line,
                                docstring,
                            ),
                        )
                        elements_indexed += 1

    connection.commit()
    connection.close()

    print("\nПроцесс индексации успешно завершен.")
    print(f"Обработано файлов: {files_indexed}")
    print(f"Сохранено элементов структуры: {elements_indexed}")
    print(f"Выходной файл: {DB_NAME}")


if __name__ == "__main__":
    main()