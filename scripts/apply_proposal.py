"""
Human-in-the-Loop Proposal Review & Application Tool for Kepler Tech SalesAI.
Ensures no offline job mutates production data without explicit human approval.

Usage:
  python scripts/apply_proposal.py --list
  python scripts/apply_proposal.py --view <proposal_id>
  python scripts/apply_proposal.py --dry-run --apply <proposal_id>
  python scripts/apply_proposal.py --apply <proposal_id> [--user <username>]
  python scripts/apply_proposal.py --reject <proposal_id> [--user <username>]
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

PROPOSALS_DIR = Path("data/proposals")


def load_proposal(proposal_id: str) -> tuple[Optional[Path], Optional[Dict[str, Any]]]:
    """Finds and loads proposal file matching proposal_id."""
    clean_id = proposal_id.strip()
    for f in PROPOSALS_DIR.glob("*.json"):
        if clean_id in f.name:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if data.get("proposal_id") == clean_id or clean_id in f.stem:
                        return f, data
            except Exception:
                pass
    return None, None


def list_proposals(status_filter: Optional[str] = None):
    print(f"\n{'ID':<16} {'JOB':<22} {'STATUS':<10} {'TARGET FILE':<30} {'CONFLICTS':<10} {'CREATED'}")
    print("-" * 105)

    count = 0
    for f in sorted(PROPOSALS_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                status = data.get("status", "pending")
                if status_filter and status != status_filter:
                    continue
                p_id = data.get("proposal_id", f.stem)
                job = data.get("job_name", "unknown")
                target = Path(data.get("target_file", "")).name
                conflicts = len(data.get("conflicts_reported", []))
                created = data.get("created_at", "")[:19]
                print(f"{p_id:<16} {job:<22} {status:<10} {target:<30} {conflicts:<10} {created}")
                count += 1
        except Exception as e:
            print(f"Error reading {f.name}: {e}")

    print("-" * 105)
    print(f"Total proposals found: {count}\n")


def view_proposal(proposal_id: str):
    path, data = load_proposal(proposal_id)
    if not data:
        print(f"Error: Proposal '{proposal_id}' not found.")
        return 1

    print(f"\n==================================================")
    print(f"PROPOSAL: {data.get('proposal_id')}")
    print(f"Job: {data.get('job_name')} | Status: {data.get('status')}")
    print(f"Created: {data.get('created_at')} | Target: {data.get('target_file')}")
    print(f"==================================================")

    print("\n[PROPOSED CHANGES]:")
    print(json.dumps(data.get("proposed_changes"), indent=2))

    conflicts = data.get("conflicts_reported", [])
    if conflicts:
        print(f"\n[CONFLICTS REPORTED ({len(conflicts)})]:")
        for i, c in enumerate(conflicts, 1):
            print(f"  {i}. {c}")
    else:
        print("\n[CONFLICTS]: None")

    if data.get("approved_by"):
        print(f"\nApproved by: {data.get('approved_by')} at {data.get('applied_at')}")

    print("\n")
    return 0


def apply_proposal(proposal_id: str, dry_run: bool = False, approved_by: str = "human_operator") -> int:
    path, data = load_proposal(proposal_id)
    if not data or not path:
        print(f"Error: Proposal '{proposal_id}' not found.")
        return 1

    if data.get("status") == "applied":
        print(f"Notice: Proposal '{proposal_id}' is already marked as 'applied'.")
        return 0

    target_file = Path(data.get("target_file", ""))
    proposed_changes = data.get("proposed_changes", {})

    print(f"\nTarget File: {target_file}")
    print(f"Mode: {'DRY RUN (No changes will be saved)' if dry_run else 'APPLYING CHANGES'}")

    if not target_file.exists():
        print(f"Target file {target_file} does not exist. Creating...")
        target_data = {}
    else:
        with open(target_file, "r", encoding="utf-8") as f:
            target_data = json.load(f)

    # Apply changes according to structure
    if isinstance(target_data, list):
        # List of items, e.g. catalogue_products.json
        model_id = proposed_changes.get("model_id")
        updates = proposed_changes.get("updates", {})
        found = False
        for item in target_data:
            if item.get("id") == model_id or item.get("model_family") == model_id:
                found = True
                print(f"Found match for '{model_id}'. Applying updates:")
                for k, v in updates.items():
                    print(f"  + {k}: {item.get(k)} -> {v}")
                    if not dry_run:
                        item[k] = v
                break
        if not found:
            print(f"Model '{model_id}' not found in catalogue. Append proposed.")
            if not dry_run:
                target_data.append(proposed_changes)
    elif isinstance(target_data, dict):
        # Dictionary config or delivery_policy.json
        print("Applying updates to dictionary target:")
        for k, v in proposed_changes.items():
            print(f"  + {k}: {target_data.get(k)} -> {v}")
            if not dry_run:
                target_data[k] = v

    if not dry_run:
        # Write back to target file
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(target_data, f, indent=2)

        # Update proposal record
        data["status"] = "applied"
        data["approved_by"] = approved_by
        data["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"\nSUCCESS: Proposal '{proposal_id}' successfully applied to {target_file}.")
    else:
        print(f"\nDRY RUN COMPLETE: Target file was NOT modified.")

    return 0


def reject_proposal(proposal_id: str, rejected_by: str = "human_operator") -> int:
    path, data = load_proposal(proposal_id)
    if not data or not path:
        print(f"Error: Proposal '{proposal_id}' not found.")
        return 1

    data["status"] = "rejected"
    data["approved_by"] = f"rejected_by_{rejected_by}"
    data["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Proposal '{proposal_id}' marked as 'rejected'.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Kepler Tech SalesAI Proposal Review & Apply Tool")
    parser.add_argument("--list", action="store_true", help="List all generated proposals")
    parser.add_argument("--status", type=str, help="Filter list by status (pending, applied, rejected)")
    parser.add_argument("--view", type=str, help="View proposal details")
    parser.add_argument("--apply", type=str, help="Apply proposal to target file")
    parser.add_argument("--reject", type=str, help="Reject proposal")
    parser.add_argument("--dry-run", action="store_true", help="Simulate applying proposal without modifying file")
    parser.add_argument("--user", type=str, default="admin", help="Username of human operator approving")

    args = parser.parse_args()

    if args.list or (not args.view and not args.apply and not args.reject):
        list_proposals(status_filter=args.status)
    elif args.view:
        view_proposal(args.view)
    elif args.apply:
        apply_proposal(args.apply, dry_run=args.dry_run, approved_by=args.user)
    elif args.reject:
        reject_proposal(args.reject, rejected_by=args.user)


if __name__ == "__main__":
    main()
