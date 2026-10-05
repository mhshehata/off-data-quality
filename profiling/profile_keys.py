import sys, json, collections
keys, schema, dq_err = collections.Counter(), collections.Counter(), collections.Counter()
n = 0
for line in sys.stdin:
    d = json.loads(line); n += 1
    keys.update(d.keys())
    schema[d.get("schema_version")] += 1
    dq_err.update(d.get("data_quality_errors_tags", []))
print("records:", n)
print("schema_version:", schema.most_common())
print("\nkey presence %:")
for k, v in keys.most_common(): print(f"{v/n*100:5.1f}  {k}")
print("\ntop OFF data-quality errors:", dq_err.most_common(15))
