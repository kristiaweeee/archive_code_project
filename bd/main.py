import os
from typing import Optional
from fastapi import FastAPI, Depends, Query
from sqlalchemy import create_engine, Column, Integer, String, select
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# 1. Настройка базы данных SQLite
# Файл project.db создастся автоматически в этой же папке
DATABASE_URL = "sqlite:///./project.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Определение модели данных (Таблица в БД)
class CodeElement(Base):
    __tablename__ = "code_elements"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)  # Имя функции или класса
    type = Column(String)              # Строка: 'class' или 'function'

# Создаем таблицы в файле базы данных (если их еще нет)
Base.metadata.create_all(bind=engine)

# 3. Наполнение БД тестовыми данными (для демонстрации)
def init_db():
    db = SessionLocal()
    # Проверяем, пустая ли база. Если пустая — заполняем
    if db.query(CodeElement).count() == 0:
        test_data = [
            CodeElement(name="UserService", type="class"),
            CodeElement(name="get_user_profile", type="function"),
            CodeElement(name="DatabaseConnection", type="class"),
            CodeElement(name="validate_user_input", type="function"),
            CodeElement(name="AuthManager", type="class"),
            CodeElement(name="send_notification", type="function"),
        ]
        db.add_all(test_data)
        db.commit()
    db.close()

init_db()

# 4. Инициализация FastAPI приложения
app = FastAPI(title="Поисковый API")

# Функция (зависимость) для безопасного управления сессиями БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 5. Тот самый Эндпоинт фильтрации поиска
@app.get("/api/search")
def search_elements(
    q: Optional[str] = Query(None, description="Поисковый запрос по имени"),
    type: Optional[str] = Query(None, description="Фильтр по типу: class или function"),
    db: Session = Depends(get_db)
):
    # Создаем базовый SQL запрос: SELECT * FROM code_elements
    stmt = select(CodeElement)
    
    # Если передан параметр `q`, добавляем фильтр LIKE (поиск подстроки)
    if q:
        stmt = stmt.where(CodeElement.name.contains(q))
        
    # Если передан параметр `type`, добавляем строгое равенство по типу
    if type:
        stmt = stmt.where(CodeElement.type == type)
        
    # Выполняем собранный запрос в БД
    results = db.execute(stmt).scalars().all()
    
    # Возвращаем результат в формате JSON
    return {"results": results}