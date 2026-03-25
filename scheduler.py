import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from scrapers.leboncoin import scrape as leboncoin_scrape

logger = logging.getLogger("artibat.scheduler")


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # marketplaces — кожні 15 хвилин
    scheduler.add_job(
        leboncoin_scrape,
        "interval",
        minutes=15,
        id="leboncoin",
        name="Leboncoin scraper",
    )

    return scheduler