import os
from typing import Optional, List
from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, CheckConstraint, select, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from sqlalchemy import event

# 1. Настройка базы данных SQLite
DATABASE_URL = "sqlite:///./database.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Активируем поддержку FOREIGN KEY для SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# 2. Модели данных
class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False, unique=True)
    elements = relationship("CodeElement", back_populates="file", cascade="all, delete")

class CodeElement(Base):
    __tablename__ = "code_elements"
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, index=True, nullable=False)
    type = Column(String, index=True, nullable=False)
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    docstring = Column(String, nullable=True)
    
    __table_args__ = (
        CheckConstraint(type.in_(['class', 'function']), name='check_element_type'),
    )
    file = relationship("File", back_populates="elements")

Base.metadata.create_all(bind=engine)

# Инициализация FastAPI
app = FastAPI(title="Архив кода — Поисковый API")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- ЭНДПОИНТЫ API ПО ТЗ (С ИДЕАЛЬНЫМ ПОРЯДКОМ ДЛЯ СЛЭШТОКС) ---

@app.get("/api/search", 
         tags=["🔍 Поисковая система"], 
         summary="Интеллектуальный поиск по кодовой базе",
         description="Ищет классы и функции по совпадению в названии или в тексте документации (docstring).")
def search_elements(
    q: Optional[str] = Query(None, description="Поисковый запрос (имя или докстринг)"),
    type: Optional[str] = Query(None, description="Фильтр типа: 'class' или 'function'"),
    limit: int = Query(10, ge=1, le=100, description="Количество результатов на страницу"),
    offset: int = Query(0, ge=0, description="Сколько результатов пропустить с начала"),
    db: Session = Depends(get_db)
):
    stmt = select(CodeElement)
    if q:
        stmt = stmt.where((CodeElement.name.contains(q)) | (CodeElement.docstring.contains(q)))
    if type:
        stmt = stmt.where(CodeElement.type == type)
        
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    stmt = stmt.limit(limit).offset(offset)
    results = db.execute(stmt).scalars().all()
    
    return {
        "total_found": total,
        "limit": limit,
        "offset": offset,
        "results": results
    }


@app.get("/api/stats", 
         tags=["📊 Аналитика и статистика"], 
         summary="Получение общей статистики проекта",
         description="Возвращает счетчики проиндексированных файлов, найденных классов и функций.")
def get_project_stats(db: Session = Depends(get_db)):
    total_files = db.query(File).count()
    total_classes = db.query(CodeElement).filter(CodeElement.type == "class").count()
    total_functions = db.query(CodeElement).filter(CodeElement.type == "function").count()
    
    return {
        "summary": {
            "total_files_indexed": total_files,
            "total_classes_found": total_classes,
            "total_functions_found": total_functions,
            "total_code_elements": total_classes + total_functions
        }
    }


@app.get("/api/files", 
         tags=["📁 Работа с файлами репозитория"], 
         summary="Список всех проиндексированных файлов",
         description="Выводит список всех файлов, которые система успешно распарсила и внесла в базу данных.")
def get_all_files(db: Session = Depends(get_db)):
    files = db.execute(select(File)).scalars().all()
    return {"files": [{"id": f.id, "file_name": f.file_name, "file_path": f.file_path} for f in files]}


@app.get("/api/files/{file_id}/structure", 
         tags=["📁 Работа с файлами репозитория"], 
         summary="Внутренняя структура конкретного файла",
         description="Принимает ID файла и выдает все его внутренности (классы и функции), отсортированные по порядку появления в коде.")
def get_file_structure(file_id: int, db: Session = Depends(get_db)):
    file_obj = db.get(File, file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="Файл не найден")
    elements = db.execute(select(CodeElement).where(CodeElement.file_id == file_id).order_by(CodeElement.start_line)).scalars().all()
    return {
        "file_name": file_obj.file_name,
        "file_path": file_obj.file_path,
        "structure": elements
    }

# --- ФРОНТЕНД ---

html_template = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Архив Кода — Поисковая Система</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap');
        
        body {
            font-family: 'Inter', sans-serif;
            background-color: #0b0f17;
        }
        .code-font {
            font-family: 'Fira Code', monospace;
        }
        /* Тонкий красивый скроллбар */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #0b0f17; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #334155; }
    </style>
</head>
<body class="text-slate-200 min-h-screen flex flex-col antialiased">

    <nav class="bg-[#111827] border-b border-slate-800 sticky top-0 z-50 px-6 py-4 shadow-sm">
        <div class="max-w-6xl mx-auto flex justify-between items-center">
            <div class="flex items-center gap-3">
                <div class="bg-blue-600 p-2 rounded-lg text-white shadow-md shadow-blue-600/20">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                </div>
                <span class="text-lg font-semibold tracking-tight text-white">АрхивКода <span class="text-slate-500 font-normal text-sm">// Поиск по AST</span></span>
            </div>
            <div id="statsPanel" class="text-xs font-medium text-slate-400 flex gap-3">
                </div>
        </div>
    </nav>

    <main class="flex-grow max-w-5xl mx-auto w-full p-4 md:p-8">
        
        <div class="text-center md:text-left my-6">
            <h1 class="text-3xl font-bold text-white tracking-tight mb-2">Поисковый интерфейс API</h1>
            <p class="text-slate-400 text-sm">Система навигации по структурам исходного кода Python-проектов</p>
        </div>

        <div class="bg-[#111827] border border-slate-800 rounded-xl p-4 shadow-xl mb-8">
            <div class="flex flex-col md:flex-row gap-3">
                
                <div class="flex-grow relative">
                    <input type="text" id="searchInput" 
                        placeholder="Введите название функции, класса или текст из документации..." 
                        class="w-full bg-[#1f2937] text-white placeholder-slate-500 py-3.5 px-4 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 border border-slate-700 text-sm font-medium transition-all"
                        onkeypress="if(event.key === 'Enter') performSearch()">
                </div>
                
                <div class="w-full md:w-56">
                    <select id="typeFilter" class="w-full bg-[#1f2937] text-slate-200 py-3.5 px-4 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 border border-slate-700 text-sm font-medium cursor-pointer">
                        <option value="">Все элементы кода</option>
                        <option value="class">⚡ Только классы</option>
                        <option value="function">⚙️ Только функции</option>
                    </select>
                </div>
                
                <button onclick="performSearch()" class="bg-blue-600 hover:bg-blue-500 text-white font-semibold py-3.5 px-8 rounded-lg text-sm transition-all shadow-lg shadow-blue-600/10 active:scale-95">
                    Найти
                </button>
            </div>
        </div>

        <div id="resultsInfo" class="mb-4 text-xs font-semibold text-slate-400 uppercase tracking-wider"></div>
        
        <div id="results" class="space-y-4">
            <div class="text-center py-16 bg-[#111827]/40 rounded-xl border border-slate-800 border-dashed">
                <p class="text-slate-500 text-sm">Введите запрос выше, чтобы начать поиск по базе данных</p>
            </div>
        </div>
    </main>

    <footer class="bg-[#111827] border-t border-slate-800 py-6 mt-12 text-xs text-slate-500">
        <div class="max-w-5xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-4">
            <div>
                <p class="font-medium text-slate-400">Проект «Архив Кода» © 2026</p>
                <p class="text-[11px] text-slate-600">Разработка серверной архитектуры и поисковых алгоритмов AST</p>
            </div>
            <div class="text-center md:text-right">
                <p class="text-slate-400">Команда проекта:</p>
                <p class="text-slate-500 mt-0.5">Кристина Коржуева, Соня Горбачева (Документация), Эля, Яся, Соня Селезнева</p>
            </div>
        </div>
    </footer>

    <script>
        // Загрузка счетчиков файлов/классов/функций
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                const stats = data.summary;
                document.getElementById('statsPanel').innerHTML = `
                    <span class="bg-slate-800 px-2.5 py-1 rounded-md border border-slate-700/60">Файлов: <b class="text-white">${stats.total_files_indexed}</b></span>
                    <span class="bg-slate-800 px-2.5 py-1 rounded-md border border-slate-700/60">Классов: <b class="text-blue-400">${stats.total_classes_found}</b></span>
                    <span class="bg-slate-800 px-2.5 py-1 rounded-md border border-slate-700/60">Функций: <b class="text-emerald-400">${stats.total_functions_found}</b></span>
                `;
            } catch (e) {
                console.error("Не удалось обновить панель статистики", e);
            }
        }

        // Поиск элементов
        async function performSearch() {
            const q = document.getElementById('searchInput').value.trim();
            const type = document.getElementById('typeFilter').value;
            const resultsDiv = document.getElementById('results');
            const infoDiv = document.getElementById('resultsInfo');

            infoDiv.innerHTML = '';
            resultsDiv.innerHTML = `
                <div class="flex justify-center items-center py-16">
                    <div class="animate-spin rounded-full h-8 w-8 border-2 border-blue-500 border-t-transparent"></div>
                    <span class="ml-3 text-sm text-slate-400">Поиск в репозитории...</span>
                </div>
            `;

            let url = `/api/search?limit=50`;
            if (q) url += `&q=${encodeURIComponent(q)}`;
            if (type) url += `&type=${type}`;

            try {
                const response = await fetch(url);
                const data = await response.json();

                if (data.results.length === 0) {
                    resultsDiv.innerHTML = `
                        <div class="text-center py-16 bg-[#111827]/60 rounded-xl border border-slate-800">
                            <p class="text-slate-400 text-sm font-medium">Ничего не найдено</p>
                            <p class="text-slate-600 text-xs mt-1">Попробуйте изменить поисковое слово или фильтр</p>
                        </div>`;
                    return;
                }

                infoDiv.innerHTML = `Результатов в базе данных: ${data.total_found}`;
                
                resultsDiv.innerHTML = data.results.map(item => {
                    const isClass = item.type === 'class';
                    const badgeStyle = isClass 
                        ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' 
                        : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
                    const iconName = isClass ? 'Класс' : 'Функция';
                    const docstringText = item.docstring 
                        ? item.docstring.replace(/</g, "&lt;").replace(/>/g, "&gt;") 
                        : 'Документация к данному элементу отсутствует.';

                    return `
                        <div class="bg-[#111827] rounded-xl p-5 border border-slate-800/80 shadow-sm hover:border-slate-700 transition-all flex flex-col gap-3">
                            <div class="flex items-start justify-between gap-4">
                                <div>
                                    <div class="flex items-center gap-2.5 mb-1.5">
                                        <h3 class="text-lg font-semibold text-white code-font">${item.name}</h3>
                                        <span class="text-[10px] font-bold px-2 py-0.5 rounded border uppercase tracking-wider ${badgeStyle}">${iconName}</span>
                                    </div>
                                    <div class="text-xs text-slate-500 code-font flex items-center gap-3">
                                        <span>ID файла: <span class="text-slate-300">${item.file_id}</span></span>
                                        <span>•</span>
                                        <span>Строки: <span class="text-blue-400">${item.start_line}</span> — <span class="text-blue-400">${item.end_line}</span></span>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="bg-[#1f2937]/40 rounded-lg p-3.5 border border-slate-800 shadow-inner">
                                <pre class="text-xs text-slate-300 code-font overflow-x-auto whitespace-pre-wrap leading-relaxed"><code>${docstringText}</code></pre>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (e) {
                resultsDiv.innerHTML = `
                    <div class="bg-red-500/5 border border-red-500/20 rounded-xl py-8 text-center">
                        <p class="text-red-400 text-sm font-semibold">Ошибка соединения с сервером API</p>
                        <p class="text-slate-500 text-xs mt-1 font-mono">${e.message}</p>
                    </div>`;
            }
        }

        window.onload = loadStats;
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def read_root():
    return html_template