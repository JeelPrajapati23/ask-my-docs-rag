import os
import re
import uuid

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.pdf_parser import extract_pages_from_pdf

_SECTION_RE = re.compile(
    r"^((?:ARTICLE|SECTION|SCHEDULE|EXHIBIT|ANNEX|APPENDIX)\s+[\w\d]+.*"
    r"|(?:Section|Article)\s+\d[\d\.]*\s+\S.*"
    r"|\d+[\.\d]*\s+[A-Z][A-Z ]{2,50}$)",
    re.MULTILINE,
)

# Parents: broad legal sections (no overlap — sections must be distinct)
# Children: tight fragments for dense semantic retrieval
PARENT_CHUNK_SIZE = 2000
CHILD_CHUNK_SIZE = 350
CHILD_CHUNK_OVERLAP = 50

_parent_splitter = RecursiveCharacterTextSplitter(
    chunk_size=PARENT_CHUNK_SIZE,
    chunk_overlap=0,
    separators=["\n\n", "\n", " "],
)
_child_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHILD_CHUNK_SIZE,
    chunk_overlap=CHILD_CHUNK_OVERLAP,
)


def _extract_section_hint(text: str) -> str:
    """Returns the first section-header-like line found in the first 500 chars."""
    match = _SECTION_RE.search(text[:500])
    return match.group(0).strip()[:100] if match else ""


def process_pdf(file_path: str):
    """
    Two-tier parent-child chunking for legal PDFs.

    Parents (2000 chars, no overlap): broad legal sections split at paragraph
    boundaries. Stored as payload on each child — sent to the LLM at generation time.

    Children (350 chars, 50 overlap): tight, high-signal fragments. Embedded as
    vectors and indexed in Qdrant — used for semantic + BM25 retrieval.

    Every child carries:
      parent_context  : full text of its parent section
      parent_id       : UUID shared by all siblings from the same parent (used for
                        deduplication at retrieval time)
      section         : first detected legal heading in the child or parent
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    source_file = os.path.basename(file_path)
    pages = extract_pages_from_pdf(file_path)  # [(page_num, text), ...]

    page_docs = [
        Document(
            page_content=text,
            metadata={
                "source": file_path,
                "source_file": source_file,
                "page": page_num,
            },
        )
        for page_num, text in pages
    ]

    child_chunks = []
    for parent in _parent_splitter.split_documents(page_docs):
        parent_id = str(uuid.uuid4())
        parent_section = _extract_section_hint(parent.page_content)
        children = _child_splitter.split_documents([parent])
        for child in children:
            child.metadata["parent_context"] = parent.page_content
            child.metadata["parent_id"] = parent_id
            section = _extract_section_hint(child.page_content) or parent_section
            if section:
                child.metadata["section"] = section
        child_chunks.extend(children)

    return child_chunks
