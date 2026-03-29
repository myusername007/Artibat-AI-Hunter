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


# Вартість ремонту €/m²
TRAVAUX_COST: dict[TravauxType, tuple[int, int]] = {
    TravauxType.LIGHT: (300, 500),
    TravauxType.HEAVY: (600, 800),
    TravauxType.FULL:  (900, 1100),
}

# Середній ринковий €/m² по місту (базові значення 2024-2025)
# Джерело: meilleursagents.com / notaires.fr
MARKET_PRICE_M2: dict[str, int] = {
    # 06 — Alpes-Maritimes
    "nice":          4200,
    "cannes":        5800,
    "antibes":       5200,
    "grasse":        3100,
    "menton":        4500,
    "cagnes-sur-mer": 3800,
    "cagnes":        3800,
    "vence":         3200,
    "mougins":       4800,
    "vallauris":     3400,
    "juan-les-pins": 5000,
    # 83 — Var
    "toulon":        2900,
    "fréjus":        3400,
    "frejus":        3400,
    "saint-tropez":  12000,
    "draguignan":    2400,
    "hyères":        3600,
    "sainte-maxime": 5500,
    "la seyne-sur-mer": 2600,
    "la seyne":      2600,
    "bandol":        5000,
    "sanary":        4800,
}

DEFAULT_MARKET_PRICE = 3500  # якщо місто не знайдено

# Зональні коефіцієнти
ZONE_COEFF: dict[ZoneType, float] = {
    ZoneType.CENTRE:     1.15,  # +15% (середина між +10 і +20)
    ZoneType.STANDARD:   1.0,
    ZoneType.PERIPHERIE: 0.90,  # -10%
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

    score: str  # HIGH / MEDIUM / LOW
    summary: str


def detect_zone(description: str) -> ZoneType:
    text = description.lower()
    if any(kw in text for kw in CENTRE_KEYWORDS):
        return ZoneType.CENTRE
    if any(kw in text for kw in PERIPHERIE_KEYWORDS):
        return ZoneType.PERIPHERIE
    return ZoneType.STANDARD


def detect_travaux_type(description: str, dpe: str | None) -> TravauxType:
    text = description.lower()

    # DPE F/G → мінімум HEAVY
    if dpe in ("F", "G"):
        if any(kw in text for kw in FULL_KEYWORDS):
            return TravauxType.FULL
        return TravauxType.HEAVY

    # DPE E → мінімум LIGHT
    if dpe == "E":
        if any(kw in text for kw in HEAVY_KEYWORDS + FULL_KEYWORDS):
            return TravauxType.HEAVY
        return TravauxType.LIGHT

    # без DPE — визначаємо по тексту
    if any(kw in text for kw in FULL_KEYWORDS):
        return TravauxType.FULL
    if any(kw in text for kw in HEAVY_KEYWORDS):
        return TravauxType.HEAVY
    if any(kw in text for kw in LIGHT_KEYWORDS):
        return TravauxType.LIGHT

    # за замовчуванням — LIGHT (консервативно)
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

    city_key = city.lower().strip()
    prix_m2_marche = MARKET_PRICE_M2.get(city_key, DEFAULT_MARKET_PRICE)

    # автовизначення якщо не передано
    if zone is None:
        zone = detect_zone(description)
    if travaux_type is None:
        travaux_type = detect_travaux_type(description, dpe)

    zone_coeff = ZONE_COEFF[zone]

    # вартість ремонту
    cost_min, cost_max = TRAVAUX_COST[travaux_type]
    travaux_min = surface * cost_min
    travaux_max = surface * cost_max
    travaux_mid = surface * (cost_min + cost_max) / 2

    # ціна продажу після ремонту
    base_revente = surface * prix_m2_marche * zone_coeff
    # діапазон ±5% для консервативної/оптимістичної оцінки
    prix_revente_min = base_revente * 0.95
    prix_revente_max = base_revente * 1.05
    prix_revente_mid = base_revente

    # ROI = (revente - achat - travaux) / (achat + travaux)
    def _roi(revente: float, travaux: float) -> float:
        total = prix_achat + travaux
        if total <= 0:
            return 0.0
        return (revente - prix_achat - travaux) / total * 100

    roi_min = _roi(prix_revente_min, travaux_max)
    roi_max = _roi(prix_revente_max, travaux_min)
    roi_mid = _roi(prix_revente_mid, travaux_mid)

    # scoring
    if roi_mid >= 30:
        score = "HIGH"
    elif roi_mid >= 15:
        score = "MEDIUM"
    else:
        score = "LOW"

    # підвищуємо пріоритет для F/G DPE (ринок недооцінює, ми заробляємо на реновації)
    if dpe in ("F", "G") and score == "MEDIUM":
        score = "HIGH"

    summary = _build_summary(
        city, surface, prix_achat, prix_m2_marche,
        travaux_type, zone, dpe,
        travaux_mid, prix_revente_mid, roi_mid, roi_min, roi_max, score
    )

    return ROIResult(
        city=city,
        surface=surface,
        prix_achat=prix_achat,
        travaux_type=travaux_type,
        zone=zone,
        dpe=dpe,
        prix_m2_marche=prix_m2_marche,
        travaux_min=travaux_min,
        travaux_max=travaux_max,
        travaux_mid=travaux_mid,
        prix_revente_min=prix_revente_min,
        prix_revente_max=prix_revente_max,
        prix_revente_mid=prix_revente_mid,
        roi_min=roi_min,
        roi_max=roi_max,
        roi_mid=roi_mid,
        score=score,
        summary=summary,
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