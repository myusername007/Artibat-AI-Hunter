from sqlalchemy.orm import Session
from db.models import Lead


def is_duplicate(session: Session, url: str) -> bool:
    return session.query(Lead).filter(Lead.url == url).first() is not None


def save_lead(session: Session, lead: Lead) -> bool:
    if is_duplicate(session, lead.url):
        return False
    session.add(lead)
    session.commit()
    return True