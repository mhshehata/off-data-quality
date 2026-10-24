import sys, json, csv, itertools
cols = ["code","product_name","brands","categories_tags","quantity","product_quantity",
        "product_quantity_unit","serving_size","labels_tags","countries_tags",
        "last_modified_t","n_nutrition_sets","set_source","set_per",
        "energy-kcal","fat","sugars","proteins","salt"]
w = csv.writer(sys.stdout)
w.writerow(cols)
for line in itertools.islice(sys.stdin, 500):
    d = json.loads(line)
    sets = (d.get("nutrition") or {}).get("input_sets") or []
    s = next((x for x in sets if x.get("per") == "100g" and x.get("preparation") == "as_sold"), {})
    nut = s.get("nutrients", {})
    row = []
    for c in cols:
        if c == "n_nutrition_sets": v = len(sets)
        elif c == "set_source": v = s.get("source")
        elif c == "set_per": v = s.get("per")
        elif c in ("energy-kcal","fat","sugars","proteins","salt"): v = (nut.get(c) or {}).get("value")
        else: v = d.get(c)
        if isinstance(v, list): v = ", ".join(v)
        row.append("" if v is None else v)
    w.writerow(row)
