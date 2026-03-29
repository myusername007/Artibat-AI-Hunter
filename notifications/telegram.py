import os
import httpx
from db.models import Lead
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SOURCE_BUTTONS = {
    "allovoisins": ("🌐 Відкрити AlloVoisins", "https://www.allovoisins.com/accueil"),
    "pap":         ("🏠 Відкрити PAP", "https://www.pap.fr"),
    "bienici":     ("🏡 Відкрити Bien'ici", "https://www.bienici.com"),
    "seloger":     ("🔍 Відкрити SeLoger", "https://www.seloger.com"),
}

DEFAULT_BUTTON = ("🌐 Відкрити оголошення", "https://www.pap.fr")


def format_alert(lead: Lead) -> str:
    lines = ["🔥 NEW PROJECT\n"]
    if lead.city:
        lines.append(f"City: {lead.city}")
    if lead.project:
        lines.append(f"Project: {lead.project[:200]}")
    lines.append("")
    if lead.description:
        lines.append(lead.description[:300])
    lines.append("")
    lines.append(f"Source: {lead.source}")
    lines.append(f"Priority: {lead.priority}")
    return "\n".join(lines)


async def send_alert(lead: Lead) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False

    text = format_alert(lead)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    btn_text, btn_url = SOURCE_BUTTONS.get(lead.source, DEFAULT_BUTTON)

    # якщо є пряме посилання на оголошення — використовуємо його
    if lead.url and lead.url.startswith("http"):
        btn_url = lead.url

    reply_markup = {
        "inline_keyboard": [[
            {"text": btn_text, "url": btn_url}
        ]]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json={
            "chat_id": int(CHAT_ID),
            "text": text,
            "reply_markup": reply_markup,
            "disable_web_page_preview": True,
        })
    return response.status_code == 200