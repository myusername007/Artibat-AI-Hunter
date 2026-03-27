import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from scrapers.leboncoin import scrape as leboncoin_scrape
from scrapers.allovoisins import scrape as allovoisins_scrape

logger = logging.getLogger("artibat.scheduler")


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()


    scheduler.add_job(
        allovoisins_scrape,
        "interval",
        minutes=27,
        id="allovoisins",
        name="AlloVoisins scraper",
    )

    return scheduler