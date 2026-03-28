import asyncio
import json
import logging
import os
import re
from datetime import datetime
from playwright.async_api import async_playwright
from notifications.telegram import send_alert
from db.database import SessionLocal
from db.models import Lead
from core.dedup import save_lead, is_duplicate

logger = logging.getLogger("artibat.allovoisins")

COOKIES_FILE = "cookies_allovoisins.json"
FEED_URL = "https://www.allovoisins.com/accueil"

KEYWORDS = [
    "rénovation", "travaux", "ravalement", "isolation",
    "extension", "construction", "toiture", "sinistre",
    "peinture", "plomberie", "électricité", "carrelage",
    "façade", "fenêtre", "porte", "cuisine", "salle de bain"
]

AUTO_REPLY = """Bonjour,

Je suis très intéressé par votre projet. Notre équipe est disponible rapidement pour intervenir dans votre secteur.

Pouvez-vous me contacter pour que nous puissions discuter de vos besoins et vous proposer un devis gratuit ?

Cordialement,
Artibat"""


async def scrape():
    logger.info("AlloVoisins scraper started")

    if not os.path.exists(COOKIES_FILE):
        logger.error(f"Cookies file not found: {COOKIES_FILE}")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )

        with open(COOKIES_FILE) as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)

        page = await context.new_page()

        try:
            await page.goto(FEED_URL, timeout=30000)
            await page.wait_for_timeout(3000)

            # закриваємо GDPR якщо є
            try:
                await page.click("button.didomi-dismiss-button", timeout=3000)
                await page.wait_for_timeout(1000)
            except Exception:
                pass

            # скролимо щоб завантажити більше
            for _ in range(3):
                await page.keyboard.press("End")
                await page.wait_for_timeout(1000)

            # знаходимо всі запити
            posts = await page.query_selector_all("article, .request-card, [class*='request'], [class*='demande']")
            logger.info(f"Found {len(posts)} posts")

            if not posts:
                # спробуємо через текст
                html = await page.content()
                logger.info(f"Page length: {len(html)}")

            session = SessionLocal()
            try:
                for post in posts:
                    try:
                        await _process_post(post, page, session)
                    except Exception as e:
                        logger.error(f"Error processing post: {e}")
            finally:
                session.close()

        except Exception as e:
            logger.error(f"Error: {e}")
        finally:
            await browser.close()

    logger.info("AlloVoisins scraper finished")


async def _process_post(post, page, session):
    text = await post.inner_text()
    if not text.strip():
        return

    # перевіряємо чи є ключові слова
    text_lower = text.lower()
    if not any(kw in text_lower for kw in KEYWORDS):
        return

    # унікальний ID поста
    post_id = await post.get_attribute("id") or await post.get_attribute("data-id")
    url = f"https://www.allovoisins.com/accueil#{post_id}" if post_id else f"https://www.allovoisins.com/accueil#{hash(text[:100])}"

    if is_duplicate(session, url):
        logger.debug(f"Duplicate: {url}")
        return

    # витягуємо місто
    city_match = re.search(r"(Nice|Cannes|Antibes|Toulon|Fréjus|Saint-Tropez|Grasse)[^)]*", text)
    city = city_match.group(0).strip() if city_match else "Nice"
    department = "06" if any(c in city for c in ["Nice", "Cannes", "Antibes", "Grasse"]) else "83"

    lead = Lead(
        source="allovoisins",
        city=city,
        department=department,
        project=text[:200],
        type="direct_lead",
        surface=None,
        budget=None,
        phone=None,
        email=None,
        priority="HIGH",
        url=url,
        description=text[:500],
    )

    saved = save_lead(session, lead)
    if saved:
        logger.info(f"New lead: {city} | {url}")
        await send_alert(lead)

        # автовідповідь
        try:
            reply_btn = await post.query_selector("button[class*='reply'], a[class*='reply'], [class*='repondre'], [class*='Ответить']")
            if reply_btn:
                await reply_btn.click()
                await page.wait_for_timeout(1000)
                textarea = await page.query_selector("textarea")
                if textarea:
                    await textarea.fill(AUTO_REPLY)
                    await page.wait_for_timeout(500)
                    submit = await page.query_selector("button[type='submit']")
                    if submit:
                        await submit.click()
                        logger.info(f"Auto-reply sent for: {url}")
        except Exception as e:
            logger.error(f"Auto-reply error: {e}")