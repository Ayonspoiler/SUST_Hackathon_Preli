"""Validate the deployed service against the public sample pack.

Usage:
  1) Start the service:  uvicorn main:app --port 8000
  2) Run:                python tests/test_samples.py SUST_Preli_Sample_Cases.json [BASE_URL]
"""
import json
import sys
import urllib.request

BASE = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
URL = BASE.rstrip("/") + "/analyze-ticket"
KEY_FIELDS = [
    "relevant_transaction_id",
    "evidence_verdict",
    "case_type",
    "department",
    "severity",
    "human_review_required",
]


def post(payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        URL, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def load_cases(path: str) -> list:
    doc = json.load(open(path, encoding="utf-8"))
    if isinstance(doc, list):
        return doc
    for k in ("cases", "samples", "data"):
        if isinstance(doc.get(k), list):
            return doc[k]
    raise SystemExit("Could not find a list of cases in the file.")


def main(path: str) -> None:
    cases = load_cases(path)
    passed = 0
    for case in cases:
        inp = case.get("input") or case.get("request")
        exp = case.get("expected_output") or case.get("expected")
        if not inp or not exp:
            continue
        try:
            got = post(inp)
        except Exception as e:
            print(f"[{case.get('id', '?')}] ERROR: {e}")
            continue
        diffs = [
            f"{k}: got={got.get(k)!r} exp={exp.get(k)!r}"
            for k in KEY_FIELDS
            if str(got.get(k)) != str(exp.get(k))
        ]
        if diffs:
            print(f"[{case.get('id', '?')}] FAIL")
            for d in diffs:
                print("    " + d)
        else:
            passed += 1
            print(
                f"[{case.get('id', '?')}] OK  "
                f"({got.get('case_type')}, {got.get('evidence_verdict')})"
            )
    print(f"\n{passed}/{len(cases)} cases matched on key fields.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "SUST_Preli_Sample_Cases.json")
