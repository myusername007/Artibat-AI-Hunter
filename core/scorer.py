from dataclasses import dataclass


LEAD_TYPE_SCORE = {
    "direct_lead": 40,
    "weak_signal_a": 20,
    "weak_signal_b": 10,
    "weak_signal_c": 5,
}

SOURCE_SCORE = {
    "leboncoin": 10,
    "allovoisins": 9,
    "needhelp": 8,
    "frizbiz": 7,
}


@dataclass
class LeadData:
    type: str
    surface: float | None
    budget: float | None
    phone: str | None
    email: str | None
    urgency_keywords: bool
    source: str


def score_lead(lead: LeadData) -> tuple[int, str]:
    score = 0

    # type
    score += LEAD_TYPE_SCORE.get(lead.type, 0)

    # surface
    if lead.surface:
        if lead.surface >= 100:
            score += 15
        elif lead.surface >= 50:
            score += 10
        else:
            score += 5

    # budget
    if lead.budget:
        if lead.budget >= 50000:
            score += 15
        elif lead.budget >= 10000:
            score += 10
        else:
            score += 5

    # contact
    if lead.phone:
        score += 15
    if lead.email:
        score += 5

    # urgency
    if lead.urgency_keywords:
        score += 10

    # source
    score += SOURCE_SCORE.get(lead.source, 5)

    # priority
    if score >= 70:
        priority = "HIGH"
    elif score >= 40:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    return score, priority