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

# Службові рядки AV які не потрібні в description
AV_NOISE = {"J'aime", "Recommander", "Répondre", "réponses", "réponse", "Bud", "NOUVEAU"}


def _clean_av_description(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(noise in line for noise in AV_NOISE):
            continue
        lines.append(line)
    return "\n".join(lines)


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
        desc = lead.description[:400]
        if lead.source == "allovoisins":
            desc = _clean_av_description(desc)
        lines.append(desc)

    lines.append("")
    lines.append(f"Source: {lead.source}")
    lines.append(f"Priority: {lead.priority}")

    # Для AV — шаблон відповіді в кінці
    if lead.source == "allovoisins":
        lines.append("\n─────────────────")
        lines.append("📋 Answer (copy):\n")
        lines.append(AUTO_REPLY_TEMPLATE)

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

    return response.status_code == 200