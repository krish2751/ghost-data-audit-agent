"""Intent decisions. The model reader (readers/intent_reader.py) is the primary path; this module holds the
deterministic decision over its facts, and a generic regex fallback used only when the reader is unavailable."""
import re

# --- generic fallback (no phrases taken from specific requests) -----------------------------------------
DELETE_RX = re.compile(
    r"delet|erase|erasure|remov|\bclos(?:e|ed|ing)\b[^.]{0,20}\b(?:account|profile)|forget|permanent|"
    r"elimin|borra|supr|suppress|efface|l[öo]sch|exclu|apag|cancel|削除|消去|삭제|删除|刪除|удал|حذف", re.I)
NEGATION_RX = re.compile(
    r"\b(?:not|never|no|without|dont|don't|do not|keep|leave|nicht|ohne|sin|sans|nao|não|no quiero|ne pas)\b|ない|ないで|않|말|不要|别", re.I)
VERIFY_RX = re.compile(r"\b(?:gone|still (?:exists?|recogni[sz]ed|there|active)|leftover|remaining)\b", re.I)


def wants_deletion(text):
    """True if some deletion cue is not negated shortly before it; verification-style wording counts as deletion."""
    for m in DELETE_RX.finditer(text):
        window = text[max(0, m.start() - 45):m.start()]
        if not NEGATION_RX.search(window):
            return True
    return bool(VERIFY_RX.search(text)) and not NEGATION_RX.search(text)


def decide(facts, classify_nondeletion):
    """Deterministic decision from the reader's facts plus the intake CLASSIFY_REQUEST cross-check.

    Returns (wants_deletion, flags). The intake row is a claim; it only breaks ties when the reader is not high-confidence."""
    flags = []
    if facts is None:
        return None, ["reader_failed"]
    wants = bool(facts["asks_for_deletion"])
    if facts.get("contains_instructions_to_assistant"):
        flags.append("injection_flag")
    if classify_nondeletion and wants:
        if facts["confidence"] == "high":
            flags.append("conflict_intake_nondeletion_kept_deletion")
        else:
            wants = False
            flags.append("intake_nondeletion_overrode_unsure_reader")
    if classify_nondeletion is False and not wants and facts["confidence"] == "low":
        flags.append("low_confidence_not_deletion")
    return wants, flags
