import re
import unicodedata


ALIASES = {"sardar sarovar dam": "sardar sarovar", "nagarjuna sagar dam": "nagarjuna sagar"}


def normalize_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\.(tif|tiff)$", "", text)
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"\bdam\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def normalized_name(value: object) -> str:
    key = normalize_key(value)
    return ALIASES.get(f"{key} dam", key)


def normalized_id(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())
