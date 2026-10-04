import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "shared" / "contracts"

schemas = sorted(CONTRACTS.rglob("*.schema.json"))

if not schemas:
    raise SystemExit("ERROR: No JSON schemas found.")

failed = []

for schema in schemas:
    try:
        with schema.open("r", encoding="utf-8-sig") as f:
            json.load(f)
        print(f"OK   {schema.relative_to(ROOT)}")
    except Exception as exc:
        failed.append((schema, exc))
        print(f"FAIL {schema.relative_to(ROOT)}: {exc}")

print()
print(f"Validated: {len(schemas)} schema(s)")

if failed:
    print(f"FAILED: {len(failed)} schema(s)")
    raise SystemExit(1)

print("RESULT: ALL SCHEMAS VALID")
