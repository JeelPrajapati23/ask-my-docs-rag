"""
Find the real PDF file paths for contracts listed in pdf_ingest_list.txt.
CUAD's full_contract_pdf/ folder is organized into subfolders by category
(Part_I/Transportation, Part_I/License, etc.) and actual filenames don't
exactly match the JSON "title" field -- so we search recursively and
fuzzy-match instead of guessing the path.

Usage:
    python find_pdfs.py "C:\\path\\to\\CUAD_v1\\full_contract_pdf" pdf_ingest_list.txt
"""

import os
import sys
import re
import shutil
import difflib

def normalize(name):
    # strip extension, punctuation, lowercase -- for fuzzy comparison
    name = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^a-z0-9]", "", name.lower())
    return name

def find_all_pdfs(root_dir):
    pdfs = []
    for dirpath, _, filenames in os.walk(root_dir):
        for f in filenames:
            if f.lower().endswith(".pdf"):
                pdfs.append(os.path.join(dirpath, f))
    return pdfs

def main(pdf_root, list_file, out_dir="matched_pdfs"):
    with open(list_file, "r", encoding="utf-8") as f:
        wanted_titles = [line.strip() for line in f if line.strip()]

    all_pdfs = find_all_pdfs(pdf_root)
    all_pdf_norms = {p: normalize(os.path.basename(p)) for p in all_pdfs}

    os.makedirs(out_dir, exist_ok=True)

    matched = []
    unmatched = []

    for title in wanted_titles:
        target_norm = normalize(title)

        # try exact substring match first (most reliable)
        exact_hits = [p for p, n in all_pdf_norms.items() if target_norm in n or n in target_norm]

        if exact_hits:
            best = exact_hits[0]
            matched.append((title, best))
            continue

        # fallback: fuzzy match on normalized names
        close = difflib.get_close_matches(target_norm, all_pdf_norms.values(), n=1, cutoff=0.6)
        if close:
            best_norm = close[0]
            best_path = next(p for p, n in all_pdf_norms.items() if n == best_norm)
            matched.append((title, best_path))
        else:
            unmatched.append(title)

    print(f"Matched: {len(matched)} / {len(wanted_titles)}")
    for title, path in matched:
        dest = os.path.join(out_dir, os.path.basename(path))
        shutil.copy2(path, dest)
        print(f"  OK  {title}\n      -> {path}")

    if unmatched:
        print(f"\nUnmatched ({len(unmatched)}):")
        for t in unmatched:
            print(f"  MISSING  {t}")
        print("\nFor unmatched titles, search manually:")
        print(f'  in File Explorer, use the search box at "{pdf_root}" for a keyword from the title')

    print(f"\nMatched PDFs copied to: {os.path.abspath(out_dir)}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print('Usage: python find_pdfs.py "<full_contract_pdf folder>" pdf_ingest_list.txt')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
