"""Split articles into overlapping, paragraph-aware chunks."""
import re

CATEGORY_KEYWORDS = {
    "skincare": ["skin", "acne", "retinol", "retinoid", "spf", "sunscreen", "moistur", "serum", "niacinamide",
                 "exfoli", "aha", "bha", "cleanser", "pore", "hyperpigment", "peau", "crème", "vitamin c"],
    "makeup": ["foundation", "concealer", "mascara", "lipstick", "eyeshadow", "blush", "primer", "makeup",
               "eyeliner", "contour", "highlighter", "maquillage", "fond de teint"],
    "hair": ["hair", "shampoo", "conditioner", "curl", "scalp", "frizz", "keratin", "dandruff", "cheveux",
             "braid", "heat protect", "bleach"],
    "nails": ["nail", "cuticle", "manicure", "polish", "gel", "ongle"],
    "fragrance": ["perfume", "fragrance", "scent", "eau de", "parfum"],
}


def guess_category(text: str, default: str = "beauty") -> str:
    t = text.lower()
    scores = {c: sum(t.count(k) for k in kws) for c, kws in CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else default


def chunk_text(text: str, max_chars: int = 900, overlap: int = 150) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, current = [], ""
    for p in paragraphs:
        # Very long paragraph: hard-split on sentences
        if len(p) > max_chars:
            sentences = re.split(r"(?<=[.!?])\s+", p)
        else:
            sentences = [p]
        for s in sentences:
            if len(current) + len(s) + 1 <= max_chars:
                current = f"{current}\n{s}" if current else s
            else:
                if current:
                    chunks.append(current)
                tail = current[-overlap:] if current and overlap else ""
                tail = tail.partition(" ")[2]  # start the overlap on a whole word
                current = f"{tail} {s}".strip() if tail else s
    if current:
        chunks.append(current)
    return [c for c in chunks if len(c) > 60]
