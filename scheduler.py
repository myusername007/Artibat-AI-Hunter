import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from scrapers.allovoisins import scrape as allovoisins_scrape
from scrapers.pap import scrape as pap_scrape
from login_allovoisins import login_auto

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

    scheduler.add_job(
        pap_scrape,
        "interval",
        minutes=30,
        id="pap",
        name="PAP scraper",
    )

    # Refresh AV cookies daily at 06:00
    scheduler.add_job(
        login_auto,
        "cron",
        hour=6,
        minute=0,
        id="av_cookie_refresh",
        name="AlloVoisins cookie refresh",
    )

    return scheduler