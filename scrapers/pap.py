import asyncio
import logging
import re
from playwright.async_api import async_playwright
from notifications.telegram import send_alert
from db.database import SessionLocal
from db.models import Lead
from core.dedup import save_lead, is_duplicate
from core.roi_engine import calculate_roi, advanced_score

logger = logging.getLogger("artibat.pap")

# Реальні URL з PAP — перевірено вручну на сайті
SEARCH_URLS = [
    # Nice (06)
    "https://www.pap.fr/annonce/vente-appartement-divers-local-commercial-local-d-activite-terrain-nice-06-g8979",
    # Cannes (06)
    "https://www.pap.fr/annonce/vente-appartement-divers-local-commercial-local-d-activite-terrain-cannes-06-g43668",
    # Antibes (06)
    "https://www.pap.fr/annonce/vente-appartement-divers-local-commercial-local-d-activite-terrain-antibes-06-g8853",
    # Grasse (06)
    "https://www.pap.fr/annonce/vente-appartement-divers-local-commercial-local-d-activite-terrain-grasse-06-g43669",
    # Toulon (83)
    "https://www.pap.fr/annonce/vente-appartement-divers-local-commercial-local-d-activite-terrain-toulon-83-g43624",
    # Fréjus (83)
    "https://www.pap.fr/annonce/vente-appartement-divers-local-commercial-local-d-activite-terrain-frejus-83-g43697",
]

# Тільки pap.fr оголошення — все інше ігноруємо
ALLOWED_URL_PREFIXES = [
    "https://www.pap.fr/annonces/",
]

HIGH_PRIORITY_KEYWORDS = [
    "à rénover", "travaux à prévoir", "fort potentiel", "à rafraîchir",
    "immeuble", "division parcellaire", "terrain constructible",
    "à restructurer", "rénovation complète", "gros travaux",
    "rendement", "investisseur", "rentabilité",
    "local commercial", "local d'activité", "entrepôt",
]

BAD_DPE = ["E", "F", "G"]

CITIES_06 = ["Nice", "Cannes", "Antibes", "Grasse", "Menton", "Cagnes-sur-Mer",
             "Cagnes", "Vence", "Mougins", "Vallauris", "Juan-les-Pins"]
CITIES_83 = ["Toulon", "Fréjus", "Saint-Tropez", "Draguignan", "Hyères",
             "Sainte-Maxime", "La Seyne-sur-Mer", "La Seyne", "Bandol", "Sanary"]


async def scrape():
    logger.info("PAP scraper started")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )

        page = await context.new_page()
        session = SessionLocal()

        try:
            for url in SEARCH_URLS:
                try:
                    await _scrape_listing_page(page, url, session)
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Error scraping {url}: {e}")
        finally:
            session.close()
            await browser.close()

    logger.info("PAP scraper finished")


async def _scrape_listing_page(page, url: str, session):
    logger.info(f"Scraping: {url}")

    await page.goto(url, timeout=30000)
    await page.wait_for_timeout(3000)

    for selector in ["button#didomi-notice-agree-button", "button[class*='agree']"]:
        try:
            await page.click(selector, timeout=2000)
            await page.wait_for_timeout(500)
            break
        except Exception:
            pass

    # Scroll down to trigger lazy loading
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
    await page.wait_for_timeout(1000)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(1500)

    # Try multiple selectors — PAP structure differs by city
    card_selectors = [
        "div.search-list-item-alt",
        "div[class*='search-list-item']",
        "article[class*='item']",
        "div.item-list > div",
    ]

    cards = []
    for selector in card_selectors:
        try:
            await page.wait_for_selector(selector, timeout=5000)
            cards = await page.query_selector_all(selector)
            if cards:
                logger.info(f"Selector '{selector}' matched {len(cards)} cards on {url}")
                break
        except Exception:
            continue

    if not cards:
        logger.warning(f"No cards found with any selector: {url}")
        # Save HTML for debugging
        try:
            html = await page.content()
            city_slug = url.split("terrain-")[-1].split("-g")[0]
            debug_path = f"/tmp/pap_debug_{city_slug}.html"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"Saved debug HTML: {debug_path}")
        except Exception as e:
            logger.error(f"Failed to save debug HTML: {e}")
        return

    logger.info(f"Found {len(cards)} cards on {url}")

    for card in cards:
        try:
            await _process_card(card, session)
        except Exception as e:
            logger.error(f"Error processing card: {e}")


async def _process_card(card, session):
    link_el = await card.query_selector("a.item-title")
    if not link_el:
        link_el = await card.query_selector("a[href*='/annonces/']")
    if not link_el:
        return

    href = await link_el.get_attribute("href") or ""
    if not href:
        return

    url = f"https://www.pap.fr{href}" if not href.startswith("http") else href

    # фільтр — тільки pap.fr/annonces/
    if not any(url.startswith(p) for p in ALLOWED_URL_PREFIXES):
        logger.debug(f"Skipped non-PAP URL: {url}")
        return

    if is_duplicate(session, url):
        logger.debug(f"Duplicate: {url}")
        return

    price_el = await card.query_selector("span.item-price")
    price_text = await price_el.inner_text() if price_el else ""
    price = _parse_price(price_text)

    city_el = await card.query_selector("span.h1")
    city_text = await city_el.inner_text() if city_el else ""

    tags_el = await card.query_selector("ul.item-tags, div.item-tags")
    tags_text = await tags_el.inner_text() if tags_el else ""
    surface = _extract_surface(tags_text)

    full_text = await card.inner_text()
    text_lower = full_text.lower()

    dpe = await _extract_dpe_from_card(card, full_text)
    city, department = _parse_city_dept(city_text or full_text)
    priority = _determine_priority(text_lower, dpe, price, surface)

    # advanced detection — IMMEUBLE / DIVISION / TERRAIN → завжди HIGH
    priority, lead_type = advanced_score(full_text, priority)

    title_text = await link_el.inner_text()

    lead = Lead(
        source="pap",
        city=city,
        department=department,
        project=title_text[:200].strip(),
        type=lead_type.value,
        surface=surface,
        budget=price,
        phone=None,
        email=None,
        priority=priority,
        url=url,
        description=_build_description(price, surface, dpe),
    )

    saved = save_lead(session, lead)
    if saved:
        roi_text = ""
        if price and surface and surface > 0:
            try:
                roi = calculate_roi(
                    city=city,
                    surface=surface,
                    prix_achat=price,
                    description=full_text,
                    dpe=dpe,
                )
                roi_text = roi.summary
                if roi.score == "HIGH" and lead.priority != "HIGH":
                    lead.priority = "HIGH"
                    session.commit()
                logger.info(f"New PAP lead: {city} | {price}€ | {surface}m² | DPE:{dpe} | ROI:{roi.roi_mid:.1f}% | {lead.priority} | {url}")
            except Exception as e:
                logger.error(f"ROI calculation error: {e}")
                logger.info(f"New PAP lead: {city} | {price}€ | {surface}m² | DPE:{dpe} | {priority} | {url}")
        else:
            logger.info(f"New PAP lead: {city} | {price}€ | {surface}m² | DPE:{dpe} | {priority} | {url}")
        await send_alert(lead, roi_text=roi_text)


async def _extract_dpe_from_card(card, text: str) -> str | None:
    dpe_el = await card.query_selector("div[class*='item-thumb-dpe']")
    if dpe_el:
        class_attr = await dpe_el.get_attribute("class") or ""
        match = re.search(r"item-thumb-dpe-([a-g])", class_attr, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return _extract_dpe_from_text(text)


def _extract_dpe_from_text(text: str) -> str | None:
    match = re.search(r"(?:DPE|classe\s+énergi(?:e|étique))[^\w]*([A-G])\b", text, re.IGNORECASE)
    return match.group(1).upper() if match else None


def _parse_price(text: str) -> float | None:
    cleaned = (text
               .replace("\u202f", "").replace("\xa0", "")
               .replace(" ", "").replace(".", "").replace(",", ""))
    match = re.search(r"(\d{4,})", cleaned)
    if match:
        val = float(match.group(1))
        if 30_000 <= val <= 10_000_000:
            return val
    return None


def _extract_surface(text: str) -> float | None:
    match = re.search(r"(\d+)\s*m[²2]", text)
    if match:
        val = float(match.group(1))
        if 10 <= val <= 5000:
            return val
    return None


def _parse_city_dept(text: str) -> tuple[str, str]:
    for city in CITIES_06:
        if city.lower() in text.lower():
            return city, "06"
    for city in CITIES_83:
        if city.lower() in text.lower():
            return city, "83"
    if "06" in text:
        return "Nice", "06"
    if "83" in text:
        return "Toulon", "83"
    return "Nice", "06"


def _determine_priority(text_lower: str, dpe: str | None, price: float | None, surface: float | None) -> str:
    score = 0

    for kw in HIGH_PRIORITY_KEYWORDS:
        if kw in text_lower:
            score += 2

    if dpe in BAD_DPE:
        score += 3
        if dpe in ["F", "G"]:
            score += 2

    if price and surface and surface > 0:
        ppm2 = price / surface
        if ppm2 < 3000:
            score += 3
        elif ppm2 < 4000:
            score += 1

    if any(kw in text_lower for kw in ["immeuble", "terrain", "division", "corps de ferme"]):
        score += 5

    if score >= 5:
        return "HIGH"
    elif score >= 2:
        return "MEDIUM"
    return "LOW"


def _build_description(price: float | None, surface: float | None, dpe: str | None) -> str:
    """Structured metadata only — raw text excluded to avoid duplication in Telegram."""
    parts = []
    if price:
        parts.append(f"Prix: {int(price):,}€".replace(",", " "))
    if surface:
        parts.append(f"Surface: {int(surface)}m²")
    if price and surface and surface > 0:
        parts.append(f"Prix/m²: {int(price / surface):,}€".replace(",", " "))
    if dpe:
        parts.append(f"DPE: {dpe}")
    return "\n".join(parts)