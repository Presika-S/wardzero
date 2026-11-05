"""Caregiver free-text notes -> risk flags (English, Tamil, Hindi). Keyword/phrase rules with simple
negation handling for English. Deliberately simple, deterministic and explainable (no LLM required)."""
import re

FLAGS = {
    "dizzy": (0.5, "dizziness", [r"dizz\w*", r"light[- ]?headed", "மயக்கம்", "தலைசுற்றல்", "चक्कर"]),
    "not_eating": (0.4, "reduced eating", [r"not eating", r"(?:poor|loss of|no) appetite", r"refus\w* (?:food|meals?|to eat)",
                                           r"skipp\w* meals?", "சாப்பிடவில்லை", "खाना नहीं", "भूख नहीं"]),
    "breathless": (0.8, "breathlessness", [r"breathless\w*", r"short(?:ness)? of breath", r"difficulty breathing",
                                           "மூச்சுத் திணறல்", "மூச்சு திணறல்", "सांस फूल", "सांस लेने में"]),
    "confused": (0.7, "confusion / drowsiness", [r"confus\w*", r"disorient\w*", r"drowsy", "குழப்பம்", "भ्रम"]),
    "chest_pain": (0.9, "chest discomfort", [r"chest pain", r"chest (?:tight\w*|pressure)", "நெஞ்சு வலி", "सीने में दर्द"]),
    "vomiting": (0.4, "vomiting / nausea", [r"vomit\w*", r"nausea\w*", "வாந்தி", "उल्टी"]),
    "weak": (0.3, "weakness / fatigue", [r"weak\w*", r"fatigue\w*", r"very tired", "சோர்வு", "कमजोरी"]),
    "fever_felt": (0.4, "felt feverish", [r"fever\w*", r"feels? hot", r"chills", "காய்ச்சல்", "बुखार"]),
    "missed_meds": (0.3, "missed medication", [r"missed (?:her |his |the )?(?:medic\w*|dose|tablets?)"]),
}
NEGATORS = re.compile(r"\b(no|not|without|never|denies|denied|none)\b[^.,;]{0,18}$", re.I)
MAX_NUDGE = 1.5


def detect_lang(text):
    ta = bool(re.search(r"[\u0B80-\u0BFF]", text))
    hi = bool(re.search(r"[\u0900-\u097F]", text))
    en = bool(re.search(r"[A-Za-z]{3}", text))
    langs = [n for n, ok in (("ta", ta), ("hi", hi), ("en", en)) if ok]
    return langs[0] if len(langs) == 1 else ("mixed" if langs else "unknown")


def analyze(text):
    found = {}
    for key, (w, label, pats) in FLAGS.items():
        for p in pats:
            for m in re.finditer(p, text, re.I):
                before = text[max(0, m.start() - 22):m.start()]
                is_en = bool(re.match(r"[A-Za-z]", m.group(0)))
                # "not eating"/"no appetite" are positive patterns that already contain the negator
                if is_en and NEGATORS.search(before) and not re.match(r"(not|no|loss)", m.group(0), re.I):
                    continue
                found[key] = label
    nudge = min(MAX_NUDGE, sum(FLAGS[k][0] for k in found))
    return {"lang": detect_lang(text), "flags": sorted(found), "labels": [found[k] for k in sorted(found)],
            "nudge": round(nudge, 2)}
