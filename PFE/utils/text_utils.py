# ============================================================
#  utils/text_utils.py — Utilitaires Texte Darija
# ============================================================

import re
import unicodedata
import logging

logger = logging.getLogger(__name__)


def normalize_darija(text: str) -> str:
    """
    Normalise le texte darija tunisien.
    - Gère les espaces insérés dans les mots (artefacts OCR/STT)
    - Normalise les variantes d'écriture arabe
    - Conserve les mots français (code-switching darija ↔ français)
    """
    if not text:
        return ""

    # 1. Supprimer les espaces dans les mots arabes mal découpés
    #    (artefact dataset : "ريزو" → "ري زو" corrigé)
    text = re.sub(r'(\w)\s(\w)', lambda m:
        m.group(0) if _is_latin(m.group(1)) else m.group(1) + m.group(2),
        text
    )

    # 2. Normalisation Unicode arabe
    text = unicodedata.normalize("NFC", text)

    # 3. Remplacer les variantes de alef
    text = re.sub(r'[أإآا]', 'ا', text)

    # 4. Supprimer les diacritiques (tashkil) — facultatif pour darija
    text = re.sub(r'[\u064B-\u065F]', '', text)

    # 5. Normaliser les espaces multiples
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def clean_arabic_text(text: str) -> str:
    """Nettoyage plus agressif pour l'indexation (supprime ponctuation)."""
    if not text:
        return ""
    text = normalize_darija(text)
    text = re.sub(r'[؟!،,\.\?\!\:\;\|«»\(\)\[\]]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_user_turns(instruction: str) -> list:
    """
    Extrait tous les tours utilisateur d'une instruction multi-tour.
    Format: "USER: ... | BOT: ... | USER: ..."
    Returns: liste de textes utilisateur
    """
    if not instruction:
        return []
    parts = instruction.split("|")
    user_turns = []
    for part in parts:
        part = part.strip()
        if part.upper().startswith("USER:"):
            user_turns.append(part[5:].strip())
    return user_turns


def build_conversation_text(history: list) -> str:
    """
    Formate l'historique de conversation en texte lisible.
    """
    lines = []
    for role, text in history:
        prefix = "🧑 Client" if role == "user" else "🤖 BOT"
        lines.append(f"{prefix}: {text}")
    return "\n".join(lines)


def truncate_text(text: str, max_chars: int = 200) -> str:
    """Tronque un texte long avec '...'"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(' ', 1)[0] + "..."


def _is_latin(char: str) -> bool:
    """Vérifie si un caractère est latin (pour le code-switching)."""
    try:
        return unicodedata.name(char).startswith('LATIN')
    except (ValueError, TypeError):
        return False


def detect_language_mix(text: str) -> dict:
    """
    Détecte le mélange de langues dans le darija.
    Returns: {"arabic_ratio": float, "french_ratio": float, "mixed": bool}
    """
    if not text:
        return {"arabic_ratio": 0.0, "french_ratio": 0.0, "mixed": False}

    words      = text.split()
    total      = len(words)
    if total == 0:
        return {"arabic_ratio": 0.0, "french_ratio": 0.0, "mixed": False}

    arabic_cnt = sum(1 for w in words if re.search(r'[\u0600-\u06FF]', w))
    latin_cnt  = sum(1 for w in words if re.match(r'^[a-zA-Z]+$', w))

    arabic_ratio = arabic_cnt / total
    french_ratio = latin_cnt  / total

    return {
        "arabic_ratio": round(arabic_ratio, 2),
        "french_ratio": round(french_ratio, 2),
        "mixed":        arabic_ratio > 0 and french_ratio > 0,
    }
