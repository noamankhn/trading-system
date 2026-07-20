"""
Applies human-approved proposals from improvement_proposals.json to tunable_config.json.

This is the ONLY script permitted to modify tunable_config.json automatically. It only
ever applies the fixed set of proposal types from improvement/analyzer.py - never arbitrary
code, never anything outside PROPOSAL_TYPES. Every change still passes through config.py's
bounds validation on next load, as a second layer of protection.

A proposal is only applied if a human has set "approved": true on that specific entry in
improvement_proposals.json - nothing here bypasses that gate.

Usage:
    python improvement/apply_approved.py
"""

import sys
import os
import json
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROPOSALS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "improvement_proposals.json")
TUNABLE_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "tunable_config.json")


def apply_proposal(tunables, proposal):
    ptype = proposal["type"]
    symbol = proposal.get("symbol")

    if ptype == "demote_to_watchlist":
        if symbol in tunables["active_symbols"]:
            tunables["active_symbols"].remove(symbol)
        if symbol not in tunables["watchlist_symbols"]:
            tunables["watchlist_symbols"].append(symbol)
        return True

    elif ptype == "promote_to_active":
        if symbol in tunables["watchlist_symbols"]:
            tunables["watchlist_symbols"].remove(symbol)
        if symbol not in tunables["active_symbols"]:
            tunables["active_symbols"].append(symbol)
        return True

    elif ptype == "adjust_risk_parameter":
        param = proposal.get("parameter")
        new_value = proposal.get("new_value")
        if param in tunables["risk_parameters"] and isinstance(new_value, (int, float)):
            tunables["risk_parameters"][param] = new_value
            return True
        print(f"  SKIPPED: invalid parameter/value for adjust_risk_parameter proposal {proposal['id']}")
        return False

    else:
        print(f"  SKIPPED: unknown proposal type '{ptype}' - refusing to apply anything "
              f"outside the fixed set of safe change types")
        return False


def main():
    if not os.path.exists(PROPOSALS_PATH):
        print("No improvement_proposals.json found - nothing to apply.")
        return

    with open(PROPOSALS_PATH) as f:
        proposals_data = json.load(f)

    with open(TUNABLE_CONFIG_PATH) as f:
        tunables = json.load(f)

    applied_count = 0
    for proposal in proposals_data.get("proposals", []):
        if proposal.get("approved") and not proposal.get("applied"):
            print(f"Applying proposal #{proposal['id']}: {proposal['type']} for {proposal.get('symbol', '')}")
            success = apply_proposal(tunables, proposal)
            if success:
                proposal["applied"] = True
                proposal["applied_at"] = datetime.now(timezone.utc).isoformat()
                applied_count += 1

    if applied_count == 0:
        print("No approved-but-unapplied proposals found. Nothing changed.")
        return

    tunables["last_modified_by"] = "improvement/apply_approved.py (human-approved proposals)"
    tunables["last_modified_at"] = datetime.now(timezone.utc).isoformat()

    with open(TUNABLE_CONFIG_PATH, "w") as f:
        json.dump(tunables, f, indent=2)
    with open(PROPOSALS_PATH, "w") as f:
        json.dump(proposals_data, f, indent=2)

    print(f"\nApplied {applied_count} proposal(s) to tunable_config.json")
    print("Commit and push both files to deploy - or let the workflow do it automatically.")


if __name__ == "__main__":
    main()
