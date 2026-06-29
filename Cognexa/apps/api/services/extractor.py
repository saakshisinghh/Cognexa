"""
Extractor Service — Named Entity Recognition using spaCy.
Extracts entities like equipment, locations, organizations, dates, etc.
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_nlp = None


def _get_nlp():
    """Lazy-load spaCy model."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            try:
                _nlp = spacy.load("en_core_web_sm")
            except OSError:
                logger.warning("en_core_web_sm not found, downloading...")
                import subprocess
                subprocess.run(
                    ["python", "-m", "spacy", "download", "en_core_web_sm"],
                    check=True,
                    capture_output=True,
                )
                _nlp = spacy.load("en_core_web_sm")
            logger.info("spaCy model loaded: en_core_web_sm")
        except Exception as e:
            logger.error(f"Failed to load spaCy: {e}")
            _nlp = None
    return _nlp


@dataclass
class Entity:
    text: str
    label: str
    start: int
    end: int
    context: str = ""


RELEVANT_LABELS = {
    "ORG": "Organization",
    "GPE": "Location",
    "LOC": "Location",
    "PERSON": "Person",
    "DATE": "Date",
    "TIME": "Time",
    "PRODUCT": "Product",
    "FAC": "Facility",
    "QUANTITY": "Quantity",
    "CARDINAL": "Number",
    "PERCENT": "Percentage",
    "MONEY": "Money",
    "EVENT": "Event",
    "LAW": "Law/Standard",
    "NORP": "Group",
}

# Industrial-domain keyword patterns
INDUSTRIAL_PATTERNS = [
    r"\b(?:ISO|IEC|ASTM|ASME|API|ANSI)\s*[\d\-:]+\b",
    r"\b(?:pump|valve|compressor|turbine|motor|bearing|seal|coupling|gearbox)\b",
    r"\b(?:RPM|PSI|bar|kPa|MPa|°C|°F|Hz|kW|MW|A|V|kg|ton)\b",
    r"\b(?:MTBF|MTTR|OEE|KPI|SLA|RCA|FMEA|HAZOP)\b",
    r"\bTag\s*(?:No|#|ID)?\.?\s*[A-Z0-9\-]+\b",
    r"\b(?:P&ID|PLC|DCS|SCADA|HMI|RTU|MES|ERP|CMMS)\b",
]


def extract_entities(text: str, max_length: int = 100_000) -> List[Dict[str, Any]]:
    """
    Extract named entities from text.
    Returns list of entity dicts with text, label, and context.
    """
    entities: List[Dict[str, Any]] = []

    if not text or not text.strip():
        return entities

    nlp = _get_nlp()
    if nlp is None:
        return _extract_with_regex(text)

    # Process in chunks if text is too long for spaCy
    chunk_size = min(max_length, nlp.max_length)
    seen: set[tuple[str, str]] = set()

    for start_idx in range(0, len(text), chunk_size - 200):
        chunk = text[start_idx : start_idx + chunk_size]
        try:
            doc = nlp(chunk)
            for ent in doc.ents:
                if ent.label_ not in RELEVANT_LABELS:
                    continue
                key = (ent.text.strip().lower(), ent.label_)
                if key in seen:
                    continue
                seen.add(key)
                # Get surrounding context (50 chars each side)
                ctx_start = max(0, ent.start_char - 50)
                ctx_end = min(len(chunk), ent.end_char + 50)
                context = chunk[ctx_start:ctx_end].replace("\n", " ").strip()
                entities.append({
                    "text": ent.text.strip(),
                    "label": ent.label_,
                    "label_human": RELEVANT_LABELS[ent.label_],
                    "context": context,
                })
        except Exception as e:
            logger.error(f"spaCy processing error: {e}")
            continue

    # Also run regex-based industrial patterns
    regex_entities = _extract_with_regex(text)
    for re_ent in regex_entities:
        key = (re_ent["text"].lower(), re_ent["label"])
        if key not in seen:
            seen.add(key)
            entities.append(re_ent)

    logger.info(f"Extracted {len(entities)} entities from text")
    return entities


def _extract_with_regex(text: str) -> List[Dict[str, Any]]:
    """Fallback regex-based extraction for industrial terms."""
    import re
    entities = []
    seen: set[str] = set()

    for pattern in INDUSTRIAL_PATTERNS:
        try:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                matched = match.group().strip()
                if matched.lower() in seen or len(matched) < 2:
                    continue
                seen.add(matched.lower())
                ctx_start = max(0, match.start() - 40)
                ctx_end = min(len(text), match.end() + 40)
                context = text[ctx_start:ctx_end].replace("\n", " ").strip()
                entities.append({
                    "text": matched,
                    "label": "INDUSTRIAL",
                    "label_human": "Industrial Term",
                    "context": context,
                })
        except Exception:
            continue

    return entities
