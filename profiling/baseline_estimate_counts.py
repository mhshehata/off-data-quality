"""Counts how many records in one OFF delta file trip each STTM rule, grouped by the
manual effort a human would need. Throwaway analysis for the README's estimated
before-number; NOT the pipeline. Usage: python3 baseline_estimate_counts.py <file.json.gz>
Rule logic follows docs/sttm.xlsx v1 (R19 without tolerance)."""
import gzip, json, sys

def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def gtin_ok(c):
    if not c or not c.isdigit() or len(c) not in (8, 12, 13, 14): return False
    d = [int(ch) for ch in c]
    s = sum(v * (3 if i % 2 == 0 else 1) for i, v in enumerate(reversed(d[:-1])))
    return (10 - s % 10) % 10 == d[-1]

PREC = {'manufacturer': 0, 'packaging': 1, 'estimate': 2}
FILL_FROM_RECORD = {'R07', 'R03f'}                # value can be typed in from data already in the record
LOOKUP_LIGHT = {'R01', 'R02', 'R03', 'R04', 'R08', 'R10', 'R15', 'R16', 'R17', 'R18', 'R19'}   # needs a web check
LOOKUP_HEAVY = {'R06', 'R09', 'R11', 'R12'}       # needs package photo / product page

n = 0; per_rule = {}; t1_cells = 0; t2_recs = 0; t3_recs = 0; t1_recs = 0
for line in gzip.open(sys.argv[1], 'rt', encoding='utf-8'):
    d = json.loads(line); n += 1; f = set()
    code = (d.get('code') or '').strip()
    if not code: f.add('R01')
    elif not gtin_ok(code): f.add('R02')
    if not (d.get('product_name') or '').strip():
        other = any((d.get(k) or '').strip() for k in d if k.startswith('product_name_') or k == 'generic_name')
        f.add('R03f' if other else 'R03')                       # R03f = a name exists in another language field
    if not (d.get('brands') or '').strip(): f.add('R04')
    if not d.get('categories_tags'): f.add('R06')
    if (d.get('quantity') or '').strip() and num(d.get('product_quantity')) is None: f.add('R07')
    u = (d.get('product_quantity_unit') or '').strip().lower()
    if u and u not in ('g', 'ml'): f.add('R08')
    if not (d.get('ingredients_text') or '').strip(): f.add('R09')
    if not d.get('countries_tags'): f.add('R10')
    sets = (d.get('nutrition') or {}).get('input_sets') or []
    want = '100ml' if u == 'ml' else '100g'
    cand = sorted([s for s in sets if s.get('preparation') == 'as_sold' and s.get('per') == want],
                  key=lambda s: PREC.get(s.get('source'), 9))
    if not cand:
        f.add('R11')
        if sets and any(s.get('per') == 'serving' for s in sets): f.add('R12')
    else:
        nut = cand[0].get('nutrients') or {}
        v = lambda k: num((nut.get(k) or {}).get('value'))
        kcal, fat, sat, carb, sug, pro, salt = (v(k) for k in ('energy-kcal', 'fat', 'saturated-fat', 'carbohydrates', 'sugars', 'proteins', 'salt'))
        if kcal is not None and not (0 <= kcal <= 900): f.add('R15')
        if any(x is not None and not (0 <= x <= 100) for x in (fat, sat, carb, sug, pro, v('fiber'))): f.add('R16')
        if salt is not None and not (0 <= salt <= 100): f.add('R17')
        if kcal is not None and None not in (fat, carb, pro) and ((kcal == 0 and (fat > 0 or carb > 0 or pro > 0)) or (kcal > 0 and fat == 0 and carb == 0 and pro == 0)): f.add('R18')
        if (sug is not None and carb is not None and sug > carb) or (sat is not None and fat is not None and sat > fat): f.add('R19')
    for r in f: per_rule[r] = per_rule.get(r, 0) + 1
    t1_cells += len(f & FILL_FROM_RECORD)
    t1_recs += bool(f & FILL_FROM_RECORD)
    t2_recs += bool(f & LOOKUP_LIGHT)
    t3_recs += bool(f & LOOKUP_HEAVY)

print('records', n)
print('per rule:', dict(sorted(per_rule.items())))
print(f'TIER 1 fill a value from the record: {t1_cells} cell edits in {t1_recs} records')
print(f'TIER 2 light lookup (web check):      {t2_recs} records')
print(f'TIER 3 heavy lookup (photo/product page): {t3_recs} records')
