"""
Build the FULL ingestion list for real-world testing:
- Your 12 golden contracts (exact matches, always included)
- N distractor PDFs sampled from the same CUAD corpus, biased toward
  categories that overlap with your golden set (harder distractors)
  plus a few from unrelated categories (general noise)

Usage:
    python build_ingestion_list.py "<path to full_contract_pdf folder>" pdf_ingest_list.txt
"""

import os
import sys
import random
import shutil

random.seed(7)

DISTRACTOR_COUNT_SAME_CATEGORY = 10   # extra contracts from folders that already contain a golden doc
DISTRACTOR_COUNT_OTHER_CATEGORY = 8   # extra contracts from folders you haven't touched at all
MAX_FILE_SIZE_MB = 3                  # skip huge contracts for faster test ingestion


def find_all_pdfs_by_folder(root_dir):
    """Returns dict: folder_path -> list of pdf file paths in that folder"""
    folder_map = {}
    for dirpath, _, filenames in os.walk(root_dir):
        pdfs = [os.path.join(dirpath, f) for f in filenames if f.lower().endswith(".pdf")]
        if pdfs:
            folder_map[dirpath] = pdfs
    return folder_map


def find_golden_pdf_paths(root_dir, golden_titles):
    """Locate exact golden PDFs anywhere under root_dir by filename match."""
    found = {}
    for dirpath, _, filenames in os.walk(root_dir):
        for f in filenames:
            if f in golden_titles:
                found[f] = os.path.join(dirpath, f)
    return found


def main(pdf_root, golden_list_file, out_dir="ingestion_pdfs"):
    with open(golden_list_file, "r", encoding="utf-8") as f:
        golden_titles = set(line.strip() for line in f if line.strip())

    print(f"Looking for {len(golden_titles)} golden contracts...")
    golden_found = find_golden_pdf_paths(pdf_root, golden_titles)
    missing = golden_titles - set(golden_found.keys())
    if missing:
        print("[warn] could not locate these golden files exactly:")
        for m in missing:
            print(f"  {m}")

    golden_folders = set(os.path.dirname(p) for p in golden_found.values())

    folder_map = find_all_pdfs_by_folder(pdf_root)

    # candidates from folders that already contain a golden doc (harder distractors)
    same_category_candidates = []
    for folder in golden_folders:
        for p in folder_map.get(folder, []):
            if os.path.basename(p) not in golden_titles:
                same_category_candidates.append(p)

    # candidates from folders with NO golden doc (general noise)
    other_category_candidates = []
    for folder, pdfs in folder_map.items():
        if folder not in golden_folders:
            other_category_candidates.extend(pdfs)

    def size_ok(path):
        try:
            return os.path.getsize(path) / (1024 * 1024) <= MAX_FILE_SIZE_MB
        except OSError:
            return False

    same_category_candidates = [p for p in same_category_candidates if size_ok(p)]
    other_category_candidates = [p for p in other_category_candidates if size_ok(p)]

    random.shuffle(same_category_candidates)
    random.shuffle(other_category_candidates)

    distractors_same = same_category_candidates[:DISTRACTOR_COUNT_SAME_CATEGORY]
    distractors_other = other_category_candidates[:DISTRACTOR_COUNT_OTHER_CATEGORY]

    os.makedirs(out_dir, exist_ok=True)

    all_final = list(golden_found.values()) + distractors_same + distractors_other

    for src in all_final:
        dest = os.path.join(out_dir, os.path.basename(src))
        shutil.copy2(src, dest)

    print(f"\nGolden contracts copied: {len(golden_found)}")
    print(f"Same-category distractors: {len(distractors_same)}")
    print(f"Other-category distractors: {len(distractors_other)}")
    print(f"TOTAL PDFs for ingestion: {len(all_final)}")
    print(f"Copied to: {os.path.abspath(out_dir)}")
    print("\nPoint your Legal RAG ingestion pipeline at this folder.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print('Usage: python build_ingestion_list.py "<full_contract_pdf folder>" pdf_ingest_list.txt')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])