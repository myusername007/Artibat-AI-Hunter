"""
ROI Engine — оцінка інвестиційного потенціалу нерухомості
Регіони: 06 (Alpes-Maritimes) і 83 (Var)
"""
from dataclasses import dataclass
from enum import Enum


class TravauxType(str, Enum):
    LIGHT = "light"   # косметичний ремонт: фарба, підлога, дрібниці
    HEAVY = "heavy"   # капітальний: кухня, ванна, електрика, сантехніка
    FULL  = "full"    # повна реновація: все + можливо структура


class ZoneType(str, Enum):
    CENTRE      = "centre"
    STANDARD    = "standard"
    PERIPHERIE  = "périphérie"


# Вартість ремонту €/m² — ОНОВЛЕНО
TRAVAUX_COST: dict[TravauxType, tuple[int, int]] = {
    TravauxType.LIGHT: (500, 700),
    TravauxType.HEAVY: (800, 1000),
    TravauxType.FULL:  (900, 1100),
}

# Мінімальні пороги для фільтрації
MIN_PRIX    = 20_000   # €  — нижче ігноруємо
MIN_SURFACE = 100      # m² — нижче ігноруємо

# Середній ринковий €/m² по місту — ОНОВЛЕНО (реальніші значення 2024-2025)
# Джерело: meilleursagents.com / notaires.fr
MARKET_PRICE_M2: dict[str, int] = {
    # 06 — Alpes-Maritimes
    "nice":             5000,
    "cannes":           6500,
    "antibes":          5800,
    "grasse":           3600,
    "menton":           5000,
    "cagnes-sur-mer":   4300,
    "cagnes":           4300,
    "vence":            3800,
    "mougins":          5500,
    "vallauris":        4000,
    "juan-les-pins":    5500,
    # 83 — Var
    "toulon":           3200,
    "fréjus":           3800,
    "frejus":           3800,
    "saint-tropez":     14000,
    "draguignan":       2700,
    "hyères":           4000,
    "sainte-maxime":    6000,
    "la seyne-sur-mer": 2900,
    "la seyne":         2900,
    "bandol":           5500,
    "sanary":           5200,
}

DEFAULT_MARKET_PRICE = 4000  # якщо місто не знайдено

# Зональні коефіцієнти
ZONE_COEFF: dict[ZoneType, float] = {
    ZoneType.CENTRE:     1.15,
    ZoneType.STANDARD:   1.0,
    ZoneType.PERIPHERIE: 0.90,
}

# Ключові слова для автовизначення зони
CENTRE_KEYWORDS = [
    "centre", "centre-ville", "vieux", "vieille ville", "hypercentre",
    "promenade", "croisette", "port", "old town", "cœur de",
]
PERIPHERIE_KEYWORDS = [
    "périphérie", "périphérique", "banlieue", "campagne", "rural",
    "zone industrielle", "zac", "lotissement",
]

# Ключові слова для ВИКЛЮЧЕННЯ (дрібні роботи — не є інвестиційним лідом)
EXCLUDE_KEYWORDS = [
    "peinture", "nettoyage", "jardinage", "tonte", "ménage",
    "vitrerie", "vitres", "débarras", "déménagement", "montage meuble",
    "petits travaux", "petit coup de peinture",
]

# Ключові слова для автовизначення типу ремонту
FULL_KEYWORDS = [
    "à rénover entièrement", "rénovation complète", "gros travaux",
    "à restructurer", "ruine", "à reconstruire", "hors d'eau hors d'air",
    "insalubre", "péril",
]
HEAVY_KEYWORDS = [
    "à rénover", "travaux importants", "travaux à prévoir",
    "à rafraîchir fortement", "ancien", "vétuste",
    "électricité à refaire", "plomberie à refaire",
]
LIGHT_KEYWORDS = [
    "à rafraîchir", "quelques travaux", "travaux légers",
    "bon état général", "rafraîchissement",
]


@dataclass
class ROIResult:
    # вхідні дані
    city: str
    surface: float
    prix_achat: float
    travaux_type: TravauxType
    zone: ZoneType
    dpe: str | None

    # розраховані
    prix_m2_marche: int
    travaux_min: float
    travaux_max: float
    travaux_mid: float
    prix_revente_min: float
    prix_revente_max: float
    prix_revente_mid: float

    roi_min: float
    roi_max: float
    roi_mid: float

    score: str  # HIGH / MEDIUM / LOW / IGNORED
    summary: str


def is_excluded(description: str) -> bool:
    """Повертає True якщо опис містить ключові слова дрібних робіт."""
    text = description.lower()
    return any(kw in text for kw in EXCLUDE_KEYWORDS)


def detect_zone(description: str) -> ZoneType:
    text = description.lower()
    if any(kw in text for kw in CENTRE_KEYWORDS):
        return ZoneType.CENTRE
    if any(kw in text for kw in PERIPHERIE_KEYWORDS):
        return ZoneType.PERIPHERIE
    return ZoneType.STANDARD


def detect_travaux_type(description: str, dpe: str | None) -> TravauxType:
    text = description.lower()

    if dpe in ("F", "G"):
        if any(kw in text for kw in FULL_KEYWORDS):
            return TravauxType.FULL
        return TravauxType.HEAVY

    if dpe == "E":
        if any(kw in text for kw in HEAVY_KEYWORDS + FULL_KEYWORDS):
            return TravauxType.HEAVY
        return TravauxType.LIGHT

    if any(kw in text for kw in FULL_KEYWORDS):
        return TravauxType.FULL
    if any(kw in text for kw in HEAVY_KEYWORDS):
        return TravauxType.HEAVY
    if any(kw in text for kw in LIGHT_KEYWORDS):
        return TravauxType.LIGHT

    return TravauxType.LIGHT


def calculate_roi(
    city: str,
    surface: float,
    prix_achat: float,
    description: str = "",
    dpe: str | None = None,
    travaux_type: TravauxType | None = None,
    zone: ZoneType | None = None,
) -> ROIResult:

    # ── Фільтри: ігноруємо нерелевантні об'єкти ──────────────────────────────
    ignored_reason = None

    if is_excluded(description):
        ignored_reason = "дрібні роботи (excluded keywords)"
    elif surface > 0 and surface < MIN_SURFACE:
        ignored_reason = f"surface {surface}m² < {MIN_SURFACE}m²"
    elif prix_achat > 0 and prix_achat < MIN_PRIX:
        ignored_reason = f"prix {prix_achat}€ < {MIN_PRIX}€"

    if ignored_reason:
        return ROIResult(
            city=city, surface=surface, prix_achat=prix_achat,
            travaux_type=travaux_type or TravauxType.LIGHT,
            zone=zone or ZoneType.STANDARD, dpe=dpe,
            prix_m2_marche=0, travaux_min=0, travaux_max=0, travaux_mid=0,
            prix_revente_min=0, prix_revente_max=0, prix_revente_mid=0,
            roi_min=0, roi_max=0, roi_mid=0,
            score="IGNORED",
            summary=f"⚫ IGNORED: {ignored_reason}",
        )
    # ─────────────────────────────────────────────────────────────────────────

    city_key = city.lower().strip()
    prix_m2_marche = MARKET_PRICE_M2.get(city_key, DEFAULT_MARKET_PRICE)

    if zone is None:
        zone = detect_zone(description)
    if travaux_type is None:
        travaux_type = detect_travaux_type(description, dpe)

    zone_coeff = ZONE_COEFF[zone]

    cost_min, cost_max = TRAVAUX_COST[travaux_type]
    travaux_min = surface * cost_min
    travaux_max = surface * cost_max
    travaux_mid = surface * (cost_min + cost_max) / 2

    base_revente = surface * prix_m2_marche * zone_coeff
    prix_revente_min = base_revente * 0.95
    prix_revente_max = base_revente * 1.05
    prix_revente_mid = base_revente

    def _roi(revente: float, travaux: float) -> float:
        total = prix_achat + travaux
        if total <= 0:
            return 0.0
        return (revente - prix_achat - travaux) / total * 100

    roi_min = _roi(prix_revente_min, travaux_max)
    roi_max = _roi(prix_revente_max, travaux_min)
    roi_mid = _roi(prix_revente_mid, travaux_mid)

    if roi_mid >= 30:
        score = "HIGH"
    elif roi_mid >= 15:
        score = "MEDIUM"
    else:
        score = "LOW"

    if dpe in ("F", "G") and score == "MEDIUM":
        score = "HIGH"

    summary = _build_summary(
        city, surface, prix_achat, prix_m2_marche,
        travaux_type, zone, dpe,
        travaux_mid, prix_revente_mid, roi_mid, roi_min, roi_max, score
    )

    return ROIResult(
        city=city, surface=surface, prix_achat=prix_achat,
        travaux_type=travaux_type, zone=zone, dpe=dpe,
        prix_m2_marche=prix_m2_marche,
        travaux_min=travaux_min, travaux_max=travaux_max, travaux_mid=travaux_mid,
        prix_revente_min=prix_revente_min, prix_revente_max=prix_revente_max,
        prix_revente_mid=prix_revente_mid,
        roi_min=roi_min, roi_max=roi_max, roi_mid=roi_mid,
        score=score, summary=summary,
    )


def _build_summary(
    city, surface, prix_achat, prix_m2_marche,
    travaux_type, zone, dpe,
    travaux_mid, prix_revente_mid, roi_mid, roi_min, roi_max, score
) -> str:
    score_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(score, "⚪")
    travaux_label = {"light": "Légers", "heavy": "Importants", "full": "Complets"}.get(travaux_type, "?")

    lines = [
        f"📊 ROI ANALYSIS",
        f"",
        f"🏙 {city.title()} | {int(surface)}m² | {int(prix_achat):,}€".replace(",", " "),
        f"📍 Zone: {zone.value} | Marché: {prix_m2_marche:,}€/m²".replace(",", " "),
        f"🔧 Travaux: {travaux_label} ({TRAVAUX_COST[travaux_type][0]}–{TRAVAUX_COST[travaux_type][1]}€/m²)",
    ]
    if dpe:
        lines.append(f"⚡ DPE: {dpe}")
    lines += [
        f"",
        f"💰 Travaux estimés: ~{int(travaux_mid):,}€".replace(",", " "),
        f"💵 Prix revente estimé: ~{int(prix_revente_mid):,}€".replace(",", " "),
        f"",
        f"📈 ROI: {roi_mid:.1f}% (range: {roi_min:.1f}% – {roi_max:.1f}%)",
        f"{score_emoji} Score: {score}",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# ADVANCED DETECTION
# ─────────────────────────────────────────────

class LeadType(str, Enum):
    IMMEUBLE  = "immeuble"
    DIVISION  = "division"
    TERRAIN   = "terrain"
    STANDARD  = "standard"


IMMEUBLE_KEYWORDS = [
    "immeuble", "immeuble de rapport", "immeuble entier",
    "plusieurs lots", "plusieurs appartements", "multiple logements",
    "immeuble mixte", "rez-de-chaussée commercial",
]

DIVISION_KEYWORDS = [
    "division possible", "division parcellaire", "divisible",
    "à diviser", "peut être divisé", "permis de diviser",
    "découpage possible", "plusieurs entrées",
]

TERRAIN_KEYWORDS = [
    "terrain constructible", "terrain à bâtir", "terrain viabilisé",
    "terrain nu", "dépendance", "grange à aménager",
    "corps de ferme", "mazet", "cabanon", "hangar",
    "entrepôt", "local d'activité", "local commercial",
]


def detect_lead_type(description: str) -> LeadType:
    text = description.lower()
    if any(kw in text for kw in IMMEUBLE_KEYWORDS):
        return LeadType.IMMEUBLE
    if any(kw in text for kw in DIVISION_KEYWORDS):
        return LeadType.DIVISION
    if any(kw in text for kw in TERRAIN_KEYWORDS):
        return LeadType.TERRAIN
    return LeadType.STANDARD


def advanced_score(description: str, current_priority: str) -> tuple[str, LeadType]:
    """
    Повертає (новий_пріоритет, тип_ліда).
    IMMEUBLE / DIVISION / TERRAIN → завжди HIGH.
    """
    lead_type = detect_lead_type(description)
    if lead_type in (LeadType.IMMEUBLE, LeadType.DIVISION, LeadType.TERRAIN):
        return "HIGH", lead_type
    return current_priority, lead_type