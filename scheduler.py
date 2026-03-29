import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from scrapers.allovoisins import scrape as allovoisins_scrape
from scrapers.pap import scrape as pap_scrape

logger = logging.getLogger("artibat.scheduler")


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()


    scheduler.add_job(
        allovoisins_scrape,
        "interval",
        minutes=27,
        id="allovoisins",
        name="AlloVoisins scraper",
    ),

    scheduler.add_job(
        pap_scrape,
        "interval",
        minutes=30,
        id="pap",
        name="PAP scraper",
    )


    return scheduler