import os
import httpx
from db.models import Lead
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def format_alert(lead: Lead) -> str:
    lines = ["🔥 NEW PROJECT\n"]
    if lead.city:
        lines.append(f"City: {lead.city}")
    if lead.project:
        lines.append(f"Project: {lead.project}")
    if lead.surface:
        lines.append(f"Surface: {lead.surface} m²")
    if lead.budget:
        lines.append(f"Budget: ~{int(lead.budget):,} €".replace(",", " "))
    lines.append("")
    contact = lead.phone or lead.email or "—"
    lines.append(f"Contact: {contact}")
    lines.append("")
    lines.append(f"Source: {lead.source}")
    lines.append(f"Priority: {lead.priority}")
    lines.append(f"\nLink: {lead.url}")
    return "\n".join(lines)


async def send_alert(lead: Lead) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False

    text = format_alert(lead)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json={
            "chat_id": int(CHAT_ID),
            "text": text,
            "disable_web_page_preview": True,
        })
    return response.status_code == 200