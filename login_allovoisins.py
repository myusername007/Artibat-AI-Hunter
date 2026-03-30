import asyncio
import json
import logging
import os
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("artibat.login_av")

COOKIES_FILE = "cookies_allovoisins.json"


async def login_manual():
    """Manual login (headless=False) — залогінься вручну, cookies збережуться автоматично."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )
        page = await context.new_page()
        await page.goto("https://www.allovoisins.com/")
        print("Залогінься вручну і натисни Enter...")
        input()
        cookies = await context.cookies()
        with open(COOKIES_FILE, "w") as f:
            json.dump(cookies, f)
        print(f"✅ Cookies збережено в {COOKIES_FILE}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(login_manual())