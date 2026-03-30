import asyncio
import json
import logging
import os
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("artibat.login_av")

COOKIES_FILE = "cookies_allovoisins.json"
AV_EMAIL = os.getenv("AV_EMAIL")
AV_PASSWORD = os.getenv("AV_PASSWORD")


async def login_auto() -> bool:
    """Auto login using AV_EMAIL / AV_PASSWORD from .env"""
    if not AV_EMAIL or not AV_PASSWORD:
        logger.error("AV_EMAIL or AV_PASSWORD not set in .env")
        return False

    logger.info("AlloVoisins auto-login started")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        try:
            await page.goto("https://www.allovoisins.com/", timeout=30000)
            await page.wait_for_timeout(2000)

            # GDPR / cookie banner
            for selector in [
                "button.didomi-dismiss-button",
                "button#didomi-notice-agree-button",
                "button[class*='agree']",
                "button[class*='accept']",
            ]:
                try:
                    await page.click(selector, timeout=2000)
                    await page.wait_for_timeout(500)
                    break
                except Exception:
                    pass

            # Знаходимо кнопку логіну
            login_btn = None
            for selector in [
                "a[href*='login']",
                "a[href*='connexion']",
                "button[class*='login']",
                "a[class*='login']",
                "[data-testid='login']",
            ]:
                try:
                    login_btn = await page.query_selector(selector)
                    if login_btn:
                        await login_btn.click()
                        await page.wait_for_timeout(1500)
                        break
                except Exception:
                    pass

            # Заповнюємо форму
            await page.wait_for_timeout(1000)

            email_input = await page.query_selector("input[type='email'], input[name='email'], input[name='username']")
            if email_input:
                await email_input.fill(AV_EMAIL)

            password_input = await page.query_selector("input[type='password']")
            if password_input:
                await password_input.fill(AV_PASSWORD)

            # Сабміт
            submit = await page.query_selector("button[type='submit'], input[type='submit']")
            if submit:
                await submit.click()
                await page.wait_for_timeout(3000)

            # Перевіряємо чи залогінились
            html = await page.content()
            if "logout" in html.lower() or "déconnexion" in html.lower() or "mon compte" in html.lower():
                cookies = await context.cookies()
                with open(COOKIES_FILE, "w") as f:
                    json.dump(cookies, f)
                logger.info(f"Login successful, cookies saved to {COOKIES_FILE}")
                return True
            else:
                logger.error("Login failed — not authenticated after submit")
                return False

        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
        finally:
            await browser.close()


async def login_manual():
    """Fallback: manual login (headless=False)"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.allovoisins.com/")
        print("Залогінься вручну і натисни Enter...")
        input()
        cookies = await context.cookies()
        with open(COOKIES_FILE, "w") as f:
            json.dump(cookies, f)
        print(f"Збережено в {COOKIES_FILE}")
        await browser.close()


if __name__ == "__main__":
    import sys
    if "--manual" in sys.argv:
        asyncio.run(login_manual())
    else:
        asyncio.run(login_auto())