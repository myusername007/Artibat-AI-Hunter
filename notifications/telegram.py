import os
import httpx
from db.models import Lead
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID")

# Twilio — для SMS HIGH alerts
TWILIO_SID     = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM    = os.getenv("TWILIO_FROM_NUMBER")   # +1xxxxxxxxxx
TWILIO_TO      = os.getenv("TWILIO_TO_NUMBER")     # +33xxxxxxxxx

SOURCE_BUTTONS = {
    "allovoisins": ("🌐 Open AlloVoisins", "https://www.allovoisins.com/accueil"),
    "pap":         ("🏠 Open PAP", "https://www.pap.fr"),
    "bienici":     ("🏡 Open Bien'ici", "https://www.bienici.com"),
    "seloger":     ("🔍 Open SeLoger", "https://www.seloger.com"),
}

DEFAULT_BUTTON = ("🌐 Open Announcement", "https://www.pap.fr")

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

    # AV — шаблон у тілі повідомлення (як раніше, для контексту)
    if lead.source == "allovoisins":
        lines.append("\n─────────────────")
        lines.append("📋 Answer (copy):\n")
        lines.append(AUTO_REPLY_TEMPLATE)

    return "\n".join(lines)


def _build_keyboard(lead: Lead) -> dict:
    """
    Рядок 1: [📞 Позвонить] [🌐 Open Announcement]
    Рядок 2: (порожній — кнопка шаблону надсилається окремим повідомленням)
    """
    btn_text, btn_url = SOURCE_BUTTONS.get(lead.source, DEFAULT_BUTTON)
    if lead.url and lead.url.startswith("http"):
        btn_url = lead.url

    row = [{"text": btn_text, "url": btn_url}]

    # Кнопка "Позвонить" — тільки якщо є номер
    if lead.phone:
        phone_clean = lead.phone.strip().replace(" ", "")
        row.insert(0, {"text": "📞 Позвонить", "url": f"tel:{phone_clean}"})

    return {"inline_keyboard": [row]}


async def _send_template_message(client: httpx.AsyncClient, lead: Lead) -> None:
    """Окреме forward-ready повідомлення з шаблоном відповіді."""
    city_part = f" ({lead.city})" if lead.city else ""
    header = f"📋 Шаблон відповіді{city_part} — скопіюй і відправ:\n\n"
    text = header + AUTO_REPLY_TEMPLATE
    await client.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": int(CHAT_ID),
            "text": text[:4096],
            "disable_web_page_preview": True,
        },
    )


async def _send_sms_high(lead: Lead) -> None:
    """SMS через Twilio для лідів з priority=HIGH."""
    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, TWILIO_TO]):
        return

    city = lead.city or "?"
    phone = lead.phone or "—"
    body = (
        f"🔴 ARTIBAT HIGH LEAD\n"
        f"City: {city}\n"
        f"Phone: {phone}\n"
        f"Source: {lead.source}\n"
        f"{lead.url or ''}"
    )[:160]

    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
            auth=(TWILIO_SID, TWILIO_TOKEN),
            data={"From": TWILIO_FROM, "To": TWILIO_TO, "Body": body},
        )


async def send_alert(lead: Lead, roi_text: str = "") -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False

    text = format_alert(lead)
    if roi_text:
        text += f"\n\n{roi_text}"
    text = text[:4096]

    keyboard = _build_keyboard(lead)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": int(CHAT_ID),
                "text": text,
                "reply_markup": keyboard,
                "disable_web_page_preview": True,
            },
        )
        ok = response.status_code == 200

        # Окреме повідомлення з шаблоном — для AV лідів
        if ok and lead.source == "allovoisins":
            await _send_template_message(client, lead)

    # SMS — тільки для HIGH, незалежно від джерела
    if lead.priority == "HIGH":
        await _send_sms_high(lead)

    return ok