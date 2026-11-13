"""Units, unit conversion and produce-name normalisation shared by listings, requirements and AI tools."""
import re
from decimal import Decimal

from django.db import models


class Unit(models.TextChoices):
    KG = "KG", "kg"
    TONNE = "TONNE", "tonne"
    BAG = "BAG", "bag"
    CRATE = "CRATE", "crate"
    BOX = "BOX", "box"
    DOZEN = "DOZEN", "dozen"
    LITRE = "LITRE", "litre"
    UNIT = "UNIT", "unit"


# Units that convert into each other, expressed in a base unit.
_MASS_IN_KG = {Unit.KG: Decimal("1"), Unit.TONNE: Decimal("1000")}


def convert_quantity(quantity, from_unit, to_unit) -> Decimal | None:
    """
    Convert ``quantity`` between units. Returns None when the units can't be
    converted (e.g. BAG -> KG): those only match the same unit.
    """
    quantity = Decimal(quantity)
    if from_unit == to_unit:
        return quantity
    if from_unit in _MASS_IN_KG and to_unit in _MASS_IN_KG:
        return quantity * _MASS_IN_KG[from_unit] / _MASS_IN_KG[to_unit]
    return None


def units_compatible(a, b) -> bool:
    return a == b or (a in _MASS_IN_KG and b in _MASS_IN_KG)


def format_quantity(quantity, unit) -> str:
    q = Decimal(quantity).normalize()
    text = format(q, "f")
    label = Unit(unit).label if unit in Unit.values else str(unit)
    return f"{text} {label}"


def produce_key(name: str) -> str:
    """
    Normalised produce name used for matching: lower case, single spaces,
    punctuation removed, last word made singular. "Cherry Tomatoes" ->
    "cherry tomato", "Potatoes" -> "potato", "Strawberries" -> "strawberry".
    """
    text = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    words = text.split()
    if not words:
        return ""
    last = words[-1]
    if len(last) > 4 and last.endswith("oes"):
        last = last[:-2]
    elif len(last) > 4 and last.endswith("ies"):
        last = last[:-3] + "y"
    elif len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
        last = last[:-1]
    words[-1] = last
    return " ".join(words)


def produce_matches(key_a: str, key_b: str) -> bool:
    """True if one produce key is the other, or contains it as whole words ("tomato" ~ "cherry tomato")."""
    if not key_a or not key_b:
        return False
    if key_a == key_b:
        return True
    a, b = f" {key_a} ", f" {key_b} "
    return a in b or b in a
