import os
from typing import Optional
from fastapi import FastAPI, Depends, Query
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, CheckConstraint, select
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

# 1. Настройка базы данных SQLite (Переименовали в database.db по ТЗ)
DATABASE_URL = "sqlite:///./database.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Активируем поддержку FOREIGN KEY на уровне сессии SQLite
from sqlalchemy import event
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# 2. Определение моделей данных по ТЗ

# Таблица 1: files (Информация о файлах)
class File(Base):
    __tablename__ = "files"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    
    # Связь: один файл может содержать много элементов кода
    elements = relationship("CodeElement", back_populates="file", cascade="all, delete")

# Таблица 2: code_elements (Классы и функции)
class CodeElement(Base):
    __tablename__ = "code_elements"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, index=True, nullable=False)       # Индекс 1 из ТЗ (Поиск по имени)
    type = Column(String, index=True, nullable=False)       # Индекс 2 из ТЗ (Поиск по типу)
    line_number = Column(Integer, nullable=False)
    docstring = Column(String, nullable=True)               # Может быть NULL, если описания нет
    
    # Ограничение CHECK: строго class или function
    __table_args__ = (
        CheckConstraint(type.in_(['class', 'function']), name='check_element_type'),
    )
    
    # Обратная связь с файлом
    file = relationship("File", back_populates="elements")

# Создаем таблицы и индексы в database.db автоматически
Base.metadata.create_all(bind=engine)

# 3. Наполнение БД демонстрационными данными (с учетом новых связей)
def init_db():
    db = SessionLocal()
    if db.query(File).count() == 0:
        # Сначала создаем тестовые файлы
        auth_file = File(file_name="auth.py", file_path="dataset/auth.py")
        db_file = File(file_name="db.py", file_path="dataset/db.py")
        db.add_all([auth_file, db_file])
        db.flush() # Получаем ID файлов для связывания
        
        # Наполняем элементами кода, привязывая их к файлам через file_id
        test_elements = [
            CodeElement(file_id=auth_file.id, name="AuthManager", type="class", line_number=1, docstring="Класс авторизации"),
            CodeElement(file_id=auth_file.id, name="get_user_profile", type="function", line_number=15, docstring="Получить профиль"),
            CodeElement(file_id=auth_file.id, name="validate_user_input", type="function", line_number=30, docstring=None),
            CodeElement(file_id=db_file.id, name="DatabaseConnection", type="class", line_number=5, docstring="Коннект к БД"),
            CodeElement(file_id=db_file.id, name="send_notification", type="function", line_number=45, docstring="Отправка пушей")
        ]
        db.add_all(test_elements)
        db.commit()
    db.close()

init_db()

# 4. Инициализация FastAPI приложения
app = FastAPI(title="Архив кода — Поисковый API")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 5. Обновленный Эндпоинт фильтрации поиска
@app.get("/api/search")
def search_elements(
    q: Optional[str] = Query(None, description="Поисковый запрос по имени"),
    type: Optional[str] = Query(None, description="Фильтр по типу: class или function"),
    db: Session = Depends(get_db)
):
    stmt = select(CodeElement)
    
    if q:
        stmt = stmt.where(CodeElement.name.contains(q))
    if type:
        stmt = stmt.where(CodeElement.type == type)
        
    results = db.execute(stmt).scalars().all()
    return {"results": results}
