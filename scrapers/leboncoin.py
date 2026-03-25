import logging
from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup
from db.models import Lead
from core.extractor import (
    extract_phone, extract_email,
    extract_surface, extract_budget, has_urgency
)
from core.scorer import score_lead, LeadData
from core.dedup import save_lead, is_duplicate
from notifications.telegram import send_alert
from db.database import SessionLocal

logger = logging.getLogger("artibat.leboncoin")

BASE_URL = "https://www.leboncoin.fr/recherche?category=8&locations=06,83&text="
KEYWORDS = [
    "rénovation", "travaux", "ravalement", "isolation",
    "extension", "construction", "toiture", "sinistre"
]


async def scrape():
    logger.info("Leboncoin scraper started")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="fr-FR",
            timezone_id="Europe/Paris",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        for keyword in KEYWORDS:
            url = BASE_URL + keyword
            try:
                await page.goto(url, timeout=30000)
                await page.wait_for_timeout(3000)
                html = await page.content()

                # перевіряємо чи не заблокований
                if "Доступ тимчасово обмежено" in html or "accès temporairement limité" in html.lower():
                    logger.warning(f"Blocked by Leboncoin for keyword '{keyword}'")
                    continue

                await _parse(html, keyword, page)
            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")

        await browser.close()
    logger.info("Leboncoin scraper finished")


async def _parse(html: str, keyword: str, page: Page):
    soup = BeautifulSoup(html, "lxml")
    ads = soup.select("a[data-qa-id='aditem_container']")
    logger.info(f"Found {len(ads)} ads for '{keyword}'")

    session = SessionLocal()
    try:
        for ad in ads:
            try:
                await _process_ad(ad, keyword, page, session)
            except Exception as e:
                logger.error(f"Error processing ad: {e}")
    finally:
        session.close()


async def _fetch_detail(page: Page, url: str) -> str:
    await page.goto(url, timeout=30000)
    await page.wait_for_timeout(2000)
    return await page.content()


def _extract_department(city: str, postal: str | None) -> str:
    if postal and len(postal) >= 2:
        return postal[:2]
    return "06"


async def _process_ad(ad, keyword: str, page: Page, session):
    url_tag = ad.get("href", "")
    if not url_tag:
        return

    url = f"https://www.leboncoin.fr{url_tag}"

    if is_duplicate(session, url):
        logger.debug(f"Duplicate skipped: {url}")
        return

    title_tag = ad.select_one("[data-qa-id='aditem_title']")
    location_tag = ad.select_one("[data-qa-id='aditem_location']")
    price_tag = ad.select_one("[data-qa-id='aditem_price']")

    title = title_tag.get_text(strip=True) if title_tag else keyword
    location_text = location_tag.get_text(strip=True) if location_tag else ""

    parts = location_text.split(" ")
    city = parts[0] if parts else None
    postal = parts[1] if len(parts) > 1 else None
    department = _extract_department(city, postal)

    budget_from_list = None
    if price_tag:
        try:
            raw = price_tag.get_text(strip=True).replace(" ", "").replace("€", "")
            budget_from_list = float(raw)
        except ValueError:
            pass

    detail_html = await _fetch_detail(page, url)
    detail_soup = BeautifulSoup(detail_html, "lxml")
    detail_text = detail_soup.get_text(separator=" ")

    phone = extract_phone(detail_text)
    email = extract_email(detail_text)
    surface = extract_surface(detail_text)
    budget = extract_budget(detail_text) or budget_from_list

    lead_data = LeadData(
        type="direct_lead",
        surface=surface,
        budget=budget,
        phone=phone,
        email=email,
        urgency_keywords=has_urgency(detail_text),
        source="leboncoin",
    )
    _, priority = score_lead(lead_data)

    lead = Lead(
        source="leboncoin",
        city=city,
        department=department,
        project=title,
        type="direct_lead",
        surface=surface,
        budget=budget,
        phone=phone,
        email=email,
        priority=priority,
        url=url,
        description=detail_text[:500],
    )

    saved = save_lead(session, lead)
    if saved:
        logger.info(f"New lead: {city} | {priority} | {url}")
        await send_alert(lead)
