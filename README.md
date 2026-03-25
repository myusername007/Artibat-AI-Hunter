# Artibat AI-Hunter

Автоматическая система поиска строительных лидов во Франции (департаменты 06/83).

## Стек
- Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic
- Playwright + BeautifulSoup4
- PostgreSQL 16
- Docker Compose
- Telegram Bot API

## Запуск
```bash
cp .env.example .env
# заполни .env своими данными

docker-compose up --build
```

## Структура
```
artibat-hunter/
├── scrapers/        # отдельный scraper на каждый источник
├── core/            # extractor, scorer, dedup
├── db/              # models, database, migrations
├── notifications/   # telegram alerts
├── logs/
├── main.py
└── docker-compose.yml
```

## Phases

| Phase | Источники |
|-------|-----------|
| 1 MVP | Leboncoin, AlloVoisins, NeedHelp, Frizbiz + Telegram |
| 2 | Immobilier sources + weak signals |
| 3 | Urbanisme, enchères, copro |
| 4 | Email + SMS + follow-up |