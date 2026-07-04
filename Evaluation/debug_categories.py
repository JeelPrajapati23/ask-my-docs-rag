import json, sys
from collections import defaultdict

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

TARGET_CATEGORIES = [
    "Governing Law",
    "Termination For Convenience",
    "Cap On Liability",
    "Non-Compete",
    "Change Of Control",
    "Audit Rights",
]

raw_counts = defaultdict(int)          # total questions matching category text at all
valid_counts = defaultdict(int)        # after is_impossible + answer filters
sample_questions = defaultdict(list)

for contract in data["data"]:
    for para in contract["paragraphs"]:
        for qa in para["qas"]:
            q = qa["question"]
            matched = next((c for c in TARGET_CATEGORIES if c.lower() in q.lower()), None)
            if not matched:
                continue
            raw_counts[matched] += 1
            if len(sample_questions[matched]) < 2:
                sample_questions[matched].append(q)
            if qa.get("is_impossible", False) or not qa["answers"]:
                continue
            if len(qa["answers"][0]["text"].strip()) < 5:
                continue
            valid_counts[matched] += 1

print(f"{'Category':<30} {'Raw matches':<15} {'Valid (usable)':<15}")
for cat in TARGET_CATEGORIES:
    print(f"{cat:<30} {raw_counts.get(cat,0):<15} {valid_counts.get(cat,0):<15}")

print()
print("Sample raw question text per category (to check phrasing):")
for cat in TARGET_CATEGORIES:
    for s in sample_questions.get(cat, []):
        print(f"  [{cat}] {s}")
