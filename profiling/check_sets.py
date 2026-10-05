import sys, json, collections
n_sets, combos = collections.Counter(), collections.Counter()
for line in sys.stdin:
    d = json.loads(line)
    sets = (d.get("nutrition") or {}).get("input_sets") or []
    n_sets[len(sets)] += 1
    for s in sets:
        combos[(s.get("source"), s.get("preparation"), s.get("per"))] += 1
print("input_sets per record:", sorted(n_sets.items()))
print("source/preparation/per combos:", combos.most_common(10))
