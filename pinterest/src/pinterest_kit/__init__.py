"""pinterest_kit — тулкит для системного роста Pinterest-аккаунта.

Модули:
    config      — конфиг аккаунта, досок и семантики
    keywords    — кластеры ключей и их ротация
    copywriter  — тексты пина (title / description / alt) с проверками
    scheduler   — календарь публикаций
    store       — очередь контента и снапшоты аналитики
    api         — клиент Pinterest API v5
    publisher   — синхронизация досок и публикация
    analytics   — сбор и нормализация метрик
    report      — Markdown-отчёт по росту
"""

__version__ = "0.1.0"
__all__ = [
    "analytics",
    "api",
    "config",
    "copywriter",
    "keywords",
    "publisher",
    "report",
    "scheduler",
    "store",
]
