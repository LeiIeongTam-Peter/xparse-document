"""Print proposals (with the challenger's verdict) from improvements.json by id.

Usage: python3 show_items.py T2-P5 T1-M1 ...
Missed proposals are addressed as <topic>-M<n> (1-based, in file order).
"""
import json
import pathlib
import sys

data = json.loads((pathlib.Path(__file__).parent / "improvements.json").read_text())
want = set(sys.argv[1:])
for result in data["results"]:
    challenge = result.get("challenge") or {}
    verdicts = {v["id"]: v for v in challenge.get("verdicts", [])}
    for proposal in result["proposals"]["proposals"]:
        if proposal["id"] in want:
            print(json.dumps({"proposal": proposal, "challenge": verdicts.get(proposal["id"])}, ensure_ascii=False, indent=1))
    for index, missed in enumerate(challenge.get("missed_proposals", []), start=1):
        ident = f"{result['key']}-M{index}"
        if ident in want:
            print(json.dumps({"id": ident, "added_by_challenger": missed}, ensure_ascii=False, indent=1))
