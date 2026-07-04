import re
from typing import List, Tuple

import fitz  # PyMuPDF

_HYPHEN_BREAK_RE = re.compile(r"-\s*\n\s*")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def _detect_two_column(blocks: list, page_width: float) -> Tuple[bool, float]:
    """
    Returns (is_two_column, col_midpoint).

    Looks at x0 positions of narrow text blocks only (excludes full-width
    headers/footers whose width exceeds 55% of the page). A page is treated
    as two-column when at least 15% of those narrow blocks sit in each half.
    """
    col_mid = page_width / 2
    narrow = [
        b for b in blocks
        if b[6] == 0 and (b[2] - b[0]) < page_width * 0.55
    ]
    if not narrow:
        return False, col_mid

    left = sum(1 for b in narrow if b[0] < col_mid)
    right = len(narrow) - left
    total = left + right
    is_two_col = (left / total) >= 0.15 and (right / total) >= 0.15
    return is_two_col, col_mid


def _reading_order_key(
    block, page_width: float, is_two_col: bool, col_mid: float
) -> Tuple:
    """
    Sort key: (column_index, bucketed_y0, x0).

    Vertical coordinates (y0) are grouped into 5-pixel buckets to keep text blocks 
    that sit on the same visual line perfectly aligned horizontally despite minor 
    rendering variations.

    Full-width blocks (spanning > 55% of page width — typical for section titles, 
    headers, and footers) are assigned independent column index -1 in two-column 
    layouts so they are processed cleanly in page flow rather than interleaving 
    with column content.

    In two-column mode, narrow right-column blocks are assigned column index 1 
    and therefore appear after all left-column content, giving the correct 
    top-to-bottom, left-column-first reading order for court judgments.
    """
    x0, y0, x1 = block[0], block[1], block[2]
    bucket_y = round(y0 / 5) * 5

    # Single-column pages
    if not is_two_col:
        return (0, bucket_y, x0)

    # Full-width spanning blocks (Titles, Headers, Footers)
    if (x1 - x0) > page_width * 0.55:
        return (-1, bucket_y, x0)

    # Right column
    if x0 >= col_mid:
        return (1, bucket_y, x0)

    # Left column
    return (0, bucket_y, x0)


def _process_page(page: fitz.Page) -> str:
    """
    Extract, geometrically sort, and clean all text on a single page.

    Steps
    -----
    1. Call page.get_text("blocks") to get positioned text rectangles.
    2. Detect single- vs two-column layout from block x0 distribution.
    3. Sort blocks by (column, bucketed_y0, x0) for correct reading order.
    4. Strip image/drawing blocks (type != 0).
    5. Clean and rejoin hyphenated line-breaks common in legal typography.
    6. Collapse runs of spaces/tabs to a single space.
    7. Rejoin separate layout blocks with double newlines (\n\n) to preserve paragraph 
       boundaries for downstream RAG character splitters.
    """
    blocks = page.get_text("blocks")
    page_width = page.rect.width
    is_two_col, col_mid = _detect_two_column(blocks, page_width)

    sorted_blocks = sorted(
        blocks,
        key=lambda b: _reading_order_key(b, page_width, is_two_col, col_mid),
    )

    cleaned_blocks = []
    for block in sorted_blocks:
        if block[6] == 0:  # Text blocks only
            text = block[4].strip()
            if text:
                text = _HYPHEN_BREAK_RE.sub("", text)  # "agree-\nment" → "agreement"
                text = _MULTI_SPACE_RE.sub(" ", text)  # collapse runs of spaces/tabs
                cleaned_blocks.append(text)

    # Join distinct visual blocks using paragraph breaks (\n\n) to guide chunking splits
    raw = "\n\n".join(cleaned_blocks)
    return raw.strip()


def extract_pages_from_pdf(file_path: str) -> List[Tuple[int, str]]:
    """
    Open *file_path* with PyMuPDF and return a list of
    ``(page_num, cleaned_text)`` tuples (page numbers are 1-indexed).
    Blank pages are omitted.

    Suitable for callers that want per-page metadata (e.g. LangChain's
    Document objects that carry a ``page`` field in their metadata).
    """
    doc = fitz.open(file_path)
    result: List[Tuple[int, str]] = []
    for page_num, page in enumerate(doc, start=1):
        text = _process_page(page)
        if text:
            result.append((page_num, text))
    doc.close()
    return result


def extract_text_from_pdf(file_path: str) -> str:
    """
    Return the entire document as a single string with
    ``--- Page N ---`` section markers between pages.

    Suitable for passing directly to a
    ``RecursiveCharacterTextSplitter`` when per-page metadata tracking
    is not required.
    """
    doc = fitz.open(file_path)
    page_texts: List[str] = []
    for page_num, page in enumerate(doc, start=1):
        text = _process_page(page)
        if text:
            page_texts.append(f"--- Page {page_num} ---\n{text}")
    doc.close()
    return "\n\n".join(page_texts)
