import asyncio
import logging
import os
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db.database import init_db

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/artibat.log"),
    ]
)
logger = logging.getLogger("artibat")

INTERVAL = int(os.getenv("SCRAPER_INTERVAL_MINUTES", 15))


async def run_scrapers():
    logger.info("Starting scraper cycle...")
    # scrapers будуть підключатися тут по мірі реалізації
    logger.info("Scraper cycle finished.")


async def main():
    logger.info("Artibat Hunter starting...")
    init_db()
    logger.info("Database initialized.")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_scrapers, "interval", minutes=INTERVAL)
    scheduler.start()

    logger.info(f"Scheduler started. Interval: {INTERVAL} min.")
    await run_scrapers()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down.")


if __name__ == "__main__":
    asyncio.run(main())