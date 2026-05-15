import re
from typing import Optional

def slugify(text: str) -> str:
    """Convert text to URL-friendly slug"""
    if not text:
        return ""
    # Handle non-string types (e.g., lists)
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r'[^\w\s-]', '', text.lower().strip())
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')


def is_arabic(text: str) -> bool:
    """Detect Arabic text"""
    if not text:
        return False
    return bool(re.search(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', text))


def normalize_arabic(text: str) -> str:
    """Basic Arabic normalization"""
    if not text:
        return ""
    # Remove diacritics (optional)
    text = re.sub(r'[\u064B-\u0652]', '', text)
    return text.strip()


def truncate_text(text: Optional[str], max_len: int = 300) -> Optional[str]:
    """Truncate text safely"""
    if not text:
        return None
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."