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

SOURCE_EMOJI = {
    "pap": "🏠",
    "allovoisins": "🤝",
}

AUTO_REPLY_TEMPLATE = (
    "Bonjour,\n\n"
    "Je suis très intéressé par votre projet. Notre équipe est disponible "
    "rapidement pour intervenir dans votre secteur.\n\n"
    "Pouvez-vous me contacter pour que nous puissions discuter de vos besoins "
    "et vous proposer un devis gratuit ?\n\n"
    "Cordialement,\nArtibat"
)


def format_alert(lead: Lead) -> str:
    emoji = SOURCE_EMOJI.get(lead.source, "🔥")
    lines = [f"{emoji} NEW PROJECT\n"]

    if lead.city:
        lines.append(f"City: {lead.city}")

    # project — тільки для PAP
    if lead.source == "pap" and lead.project:
        lines.append(f"Type: {lead.project[:100]}")

    lines.append("")

    if lead.description:
        lines.append(lead.description[:400])

    lines.append("")
    lines.append(f"Source: {lead.source}")
    lines.append(f"Priority: {lead.priority}")
    return "\n".join(lines)


async def send_alert(lead: Lead, roi_text: str = "") -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False

    text = format_alert(lead)
    if roi_text:
        text += f"\n\n{roi_text}"

    text = text[:4096]

    tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    btn_text, btn_url = SOURCE_BUTTONS.get(lead.source, DEFAULT_BUTTON)
    if lead.url and lead.url.startswith("http"):
        btn_url = lead.url

    reply_markup = {"inline_keyboard": [[{"text": btn_text, "url": btn_url}]]}

    async with httpx.AsyncClient() as client:
        response = await client.post(tg_url, json={
            "chat_id": int(CHAT_ID),
            "text": text,
            "reply_markup": reply_markup,
            "disable_web_page_preview": True,
        })

    # Для AV — окреме повідомлення з шаблоном для швидкого copy-paste
    if lead.source == "allovoisins" and response.status_code == 200:
        await _send_reply_template(lead)

    return response.status_code == 200


async def _send_reply_template(lead: Lead) -> None:
    """Send reply template as a separate message — tap to copy and paste on AV."""
    tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    header = f"📋 Шаблон відповіді — {lead.city}"
    text = f"{header}\n\n`{AUTO_REPLY_TEMPLATE}`"

    async with httpx.AsyncClient() as client:
        await client.post(tg_url, json={
            "chat_id": int(CHAT_ID),
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        })