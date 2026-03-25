import asyncio
import logging
import os
from dotenv import load_dotenv
from db.database import init_db
from scheduler import setup_scheduler

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


async def main():
    logger.info("Artibat Hunter starting...")
    init_db()
    logger.info("Database initialized.")

    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("Scheduler started.")

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down.")


if __name__ == "__main__":
    asyncio.run(main())