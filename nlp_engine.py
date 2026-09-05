"""
nlp_engine.py
Lightweight, dependency-friendly NLP layer for the Voice Shopping Assistant.

It does three things:
  1. Intent detection      -> add / remove / update_quantity / show_cart / checkout / unknown
  2. Entity extraction     -> quantity + unit (e.g. "2 kg", "1 litre", "3 packets")
  3. Product matching      -> fuzzy-matches whatever the user said against the
                               product catalog in the database (so "basmati"
                               matches "Basmati Rice").
"""

import re
from dataclasses import dataclass
from typing import Optional

from rapidfuzz import process, fuzz

# ---------------------------------------------------------------------------
# 1. Intent detection
# ---------------------------------------------------------------------------

INTENT_KEYWORDS = {
    "remove": ["remove", "delete", "take out", "cancel"],
    "update_quantity": ["change", "update", "make it", "set"],
    "show_cart": ["show cart", "show my cart", "view cart", "what's in my cart", "whats in my cart"],
    "checkout": ["checkout", "check out", "place order", "buy now", "confirm order"],
    "add": ["add", "i need", "i want", "put", "get me", "buy"],
}

UNITS = ["kg", "kilogram", "kilograms", "g", "gram", "grams",
         "litre", "litres", "liter", "liters", "l",
         "packet", "packets", "pack", "packs",
         "piece", "pieces", "pcs", "dozen", "dozens"]

UNIT_NORMALIZATION = {
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "g": "g", "gram": "g", "grams": "g",
    "litre": "litre", "litres": "litre", "liter": "litre", "liters": "litre", "l": "litre",
    "packet": "packet", "packets": "packet", "pack": "packet", "packs": "packet",
    "piece": "piece", "pieces": "piece", "pcs": "piece",
    "dozen": "dozen", "dozens": "dozen",
}

# Words that spell out small numbers, since people often speak these instead
# of digits ("add two packets of rice").
WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}


def detect_intent(text: str) -> str:
    text_lower = text.lower()
    # Check longer/more specific phrases first (show_cart, checkout) before
    # generic single-word intents like "add".
    for intent in ["checkout", "show_cart", "remove", "update_quantity", "add"]:
        for kw in INTENT_KEYWORDS[intent]:
            if kw in text_lower:
                return intent
    return "unknown"


# ---------------------------------------------------------------------------
# 2. Quantity + unit extraction
# ---------------------------------------------------------------------------

def extract_quantity_unit(text: str) -> tuple[float, str]:
    """Returns (quantity, unit). Defaults to (1, 'piece') if nothing found."""
    text_lower = text.lower()

    unit_pattern = "|".join(sorted(UNITS, key=len, reverse=True))
    # Numeric quantity, e.g. "2 kg", "1.5 litre"
    match = re.search(rf"(\d+(?:\.\d+)?)\s*({unit_pattern})?", text_lower)
    if match and match.group(1):
        qty = float(match.group(1))
        unit = UNIT_NORMALIZATION.get(match.group(2), "piece") if match.group(2) else "piece"
        return qty, unit

    # Word-based quantity, e.g. "two packets"
    for word, value in WORD_NUMBERS.items():
        word_match = re.search(rf"\b{word}\b\s*({unit_pattern})?", text_lower)
        if word_match:
            unit = UNIT_NORMALIZATION.get(word_match.group(1), "piece") if word_match.group(1) else "piece"
            return float(value), unit

    return 1.0, "piece"


# ---------------------------------------------------------------------------
# 3. Product matching
# ---------------------------------------------------------------------------

def match_product(text: str, product_names: list[str], score_cutoff: int = 60) -> Optional[str]:
    """Fuzzy-matches the spoken text against known product names.
    Returns the best matching product name, or None if nothing is close enough.
    """
    if not product_names:
        return None
    result = process.extractOne(text, product_names, scorer=fuzz.partial_ratio, score_cutoff=score_cutoff)
    return result[0] if result else None


# ---------------------------------------------------------------------------
# Combined parser
# ---------------------------------------------------------------------------

@dataclass
class ParsedCommand:
    intent: str
    product: Optional[str]
    quantity: float
    unit: str
    raw_text: str


def split_into_clauses(text: str) -> list[str]:
    """Splits a compound command into per-item clauses, so
    'Add 2 packets rice and 1 litre milk' becomes
    ['2 packets rice', '1 litre milk'] instead of being matched as one blob.
    """
    # Remove a leading intent verb once (e.g. "add", "i need") so it doesn't
    # attach itself to the first clause only.
    cleaned = text.lower()
    for kw_list in INTENT_KEYWORDS.values():
        for kw in sorted(kw_list, key=len, reverse=True):
            if cleaned.startswith(kw):
                cleaned = cleaned[len(kw):].strip()
                break

    clauses = re.split(r"\s*,\s*|\s+and\s+", cleaned)
    return [c.strip() for c in clauses if c.strip()]


def parse_command(text: str, product_names: list[str]) -> list[ParsedCommand]:
    """Parses a (possibly multi-item) voice command into one or more
    ParsedCommand objects — one per product mentioned.
    """
    intent = detect_intent(text)

    if intent not in ("add", "remove", "update_quantity"):
        quantity, unit = extract_quantity_unit(text)
        return [ParsedCommand(intent=intent, product=None, quantity=quantity, unit=unit, raw_text=text)]

    commands = []
    for clause in split_into_clauses(text):
        quantity, unit = extract_quantity_unit(clause)
        product = match_product(clause, product_names)
        commands.append(ParsedCommand(
            intent=intent,
            product=product,
            quantity=quantity,
            unit=unit,
            raw_text=clause,
        ))

    return commands or [ParsedCommand(intent=intent, product=None, quantity=1.0, unit="piece", raw_text=text)]


if __name__ == "__main__":
    # Quick manual test
    catalog = ["Basmati Rice", "Milk", "Pasta", "Pasta Sauce", "Tomato"]
    samples = [
        "Add 2 packets of rice and 1 litre milk",
        "I need two kg tomato",
        "Remove the milk",
        "Show my cart",
        "Change rice quantity to 3",
        "Checkout please",
    ]
    for s in samples:
        results = parse_command(s, catalog)
        print(s, "->", results)
