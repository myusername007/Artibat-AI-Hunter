import asyncio
import json
import logging
import os
import re
from playwright.async_api import async_playwright
from notifications.telegram import send_alert
from db.database import SessionLocal
from db.models import Lead
from core.dedup import save_lead, is_duplicate
from core.roi_engine import advanced_score

logger = logging.getLogger("artibat.allovoisins")

COOKIES_FILE = "cookies_allovoisins.json"
FEED_URL     = "https://www.allovoisins.com/accueil"
AV_EMAIL     = os.getenv("AV_EMAIL")
AV_PASSWORD  = os.getenv("AV_PASSWORD")

CONSTRUCTION_KEYWORDS = [
    "rénovation", "travaux", "ravalement", "isolation",
    "extension", "construction", "toiture", "sinistre",
    "peinture", "plomberie", "électricité", "carrelage",
    "façade", "fenêtre", "porte", "cuisine", "salle de bain",
    "maçonnerie", "charpente", "couverture", "enduit",
    "clôture", "escalier", "parquet", "placard",
]

EXCLUDE_KEYWORDS = [
    "déménagement", "déménager", "ménage", "nettoyage",
    "garde d'enfant", "baby-sitting", "covoiturage",
    "jardinage", "tonte", "cours particulier", "leçon",
    "informatique", "dépannage informatique",
    "vente", "don ", "cherche emploi",
    "terrasse en lame", "terrasse composite", "terrasse bois",
    "lame composite", "lame de bois",
]

AUTO_REPLY = """Bonjour,

Je suis très intéressé par votre projet. Notre équipe est disponible rapidement pour intervenir dans votre secteur.

Pouvez-vous me contacter pour que nous puissions discuter de vos besoins et vous proposer un devis gratuit ?

Cordialement,
Artibat"""


def _extract_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 10 and line not in ("NOUVEAU", "Bud", "Demande publique"):
            return line[:120]
    return text[:80]


def _is_authenticated(html: str) -> bool:
    html_l = html.lower()
    return "mon compte" in html_l or "déconnexion" in html_l or "se déconnecter" in html_l


async def _do_login(page, context) -> bool:
    logger.info("Logging in via form...")
    try:
        await page.goto("https://www.allovoisins.com/", timeout=30000)
        await page.wait_for_timeout(2000)

        for sel in ["button.didomi-dismiss-button", "button#didomi-notice-agree-button"]:
            try:
                await page.click(sel, timeout=2000)
                await page.wait_for_timeout(500)
                break
            except Exception:
                pass

        await page.click("button[data-mtm-category='connexion'], button.btn--ghost", timeout=5000)
        await page.wait_for_timeout(1500)

        await page.fill("input[type='email']", AV_EMAIL, timeout=5000)
        await page.wait_for_timeout(300)
        await page.fill("input[type='password']", AV_PASSWORD, timeout=5000)
        await page.wait_for_timeout(300)
        await page.click("button:has-text('Connexion')", timeout=5000)
        await page.wait_for_timeout(3000)

        html = await page.content()
        if _is_authenticated(html):
            cookies = await context.cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f)
            logger.info("Login successful, cookies saved ✅")
            return True
        else:
            logger.error("Login failed after form submit ❌")
            return False

    except Exception as e:
        logger.error(f"Login error: {e}")
        return False


async def scrape():
    logger.info("AlloVoisins scraper started")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )
        page = await context.new_page()

        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE) as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)

        try:
            await page.goto(FEED_URL, timeout=30000)
            await page.wait_for_timeout(3000)

            html = await page.content()

            if not _is_authenticated(html):
                logger.warning("Session expired — re-logging in...")
                ok = await _do_login(page, context)
                if not ok:
                    logger.error("Cannot authenticate, aborting")
                    return
                await page.goto(FEED_URL, timeout=30000)
                await page.wait_for_timeout(3000)
                html = await page.content()

            logger.info("Session: authenticated ✅")

            try:
                await page.click("button.didomi-dismiss-button", timeout=3000)
                await page.wait_for_timeout(1000)
            except Exception:
                pass

            for _ in range(3):
                await page.keyboard.press("End")
                await page.wait_for_timeout(1000)

            posts = await page.query_selector_all("article.search")
            logger.info(f"Found {len(posts)} posts")

            if not posts:
                logger.warning(f"Page HTML length: {len(html)}")

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
            logger.error(f"Scraper error: {e}")
        finally:
            await browser.close()

    logger.info("AlloVoisins scraper finished")


async def _process_post(post, page, session):
    text = await post.inner_text()
    if not text.strip():
        return

    if "Thématiques du moment" in text or "themes-du-moment" in text:
        return

    text_lower = text.lower()
    if not any(kw in text_lower for kw in CONSTRUCTION_KEYWORDS):
        return

    if any(kw in text_lower for kw in EXCLUDE_KEYWORDS):
        logger.debug(f"Skipped (excluded): {text[:80]}")
        return

    link = await post.query_selector("a[href*='/annonce/'], a[href*='/search/'], a[href*='/demande/']")
    if link:
        url = await link.get_attribute("href")
        if not url.startswith("http"):
            url = f"https://www.allovoisins.com{url}"
    else:
        url = f"https://www.allovoisins.com/accueil#{hash(text[:100])}"

    if is_duplicate(session, url):
        logger.debug(f"Duplicate: {url}")
        return

    city_match = re.search(r"(Nice|Cannes|Antibes|Toulon|Fréjus|Saint-Tropez|Grasse)", text)
    city = city_match.group(1) if city_match else "Nice"
    department = "06" if any(c in city for c in ["Nice", "Cannes", "Antibes", "Grasse"]) else "83"

    base_priority, lead_type = advanced_score(text, "LOW")

    clean_lines = [
        line.strip() for line in text.splitlines()
        if line.strip() and line.strip() not in ("NOUVEAU", "Bud", "Demande publique")
    ]
    clean_description = "\n".join(clean_lines)[:500]

    lead = Lead(
        source="allovoisins",
        city=city,
        department=department,
        project=_extract_title(text),
        type=lead_type.value,
        priority=base_priority,
        surface=None,
        budget=None,
        phone=None,
        email=None,
        url=url,
        description=clean_description,
    )

    saved = save_lead(session, lead)
    if saved:
        logger.info(f"New lead: {city} | {base_priority} | {url}")
        await send_alert(lead)

        try:
            reply_btn = await post.query_selector(
                "button[class*='reply'], a[class*='reply'], [class*='repondre']"
            )
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
                        logger.info(f"Auto-reply sent: {url}")
        except Exception as e:
            logger.error(f"Auto-reply error: {e}")

            
"""python -c "
import asyncio, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
from scrapers.allovoisins import scrape as scrape_av
from scrapers.pap import scrape as scrape_pap

async def run_all():
    await asyncio.gather(scrape_av(), scrape_pap())

asyncio.run(run_all())
"
"""

