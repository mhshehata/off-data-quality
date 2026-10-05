import sys, json
fields = ["product_name","brands","categories_tags","quantity","product_quantity",
          "serving_size","ingredients_text","labels_tags","nutrition","nutriments"]
present = {f: 0 for f in fields}; filled = {f: 0 for f in fields}
n = both = 0; sample = None
for line in sys.stdin:
    d = json.loads(line); n += 1
    for f in fields:
        if f in d:
            present[f] += 1
            if d[f] not in (None, "", [], {}): filled[f] += 1
    if "nutrition" in d and "nutriments" in d:
        both += 1
        if sample is None: sample = d
print(f"records {n}, with both nutrition+nutriments: {both}\n")
for f in fields:
    print(f"{f:18} present {present[f]/n*100:5.1f}%  filled {filled[f]/n*100:5.1f}%")
if sample:
    print("\ncode:", sample["code"])
    print("nutrition:", json.dumps(sample["nutrition"])[:800])
    print("nutriments:", json.dumps(sample["nutriments"])[:800])
