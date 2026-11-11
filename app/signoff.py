"""Human sign-off rules for a case. Pure functions, no I/O."""
from datetime import datetime, timezone

DECISIONS = ("approve", "decline")


class SignoffError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code


def apply_signoff(doc, role, name, decision, reason="", now=None):
    """Return the fields to store after one person signs. Raises SignoffError."""
    if doc.get("status") in ("signed_off", "declined"):
        raise SignoffError("closed", "this case is already closed")
    signers = doc["referral"]["signers"]
    if role not in signers:
        raise SignoffError("role_not_required", role + " is not a required signer")
    if decision not in DECISIONS:
        raise SignoffError("bad_decision", "decision must be approve or decline")
    name = (name or "").strip()
    if not name:
        raise SignoffError("name_required", "a name is required")
    reason = (reason or "").strip()
    if decision == "decline" and not reason:
        raise SignoffError("reason_required", "declining needs a reason")
    existing = list(doc.get("signoffs", []))
    if any(s["role"] == role for s in existing):
        raise SignoffError("already_signed", role + " has already signed")
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    entry = {
        "role": role,
        "name": name[:80],
        "decision": decision,
        "reason": reason[:500],
        "at": stamp,
    }
    signoffs = existing + [entry]
    approved = {s["role"] for s in signoffs if s["decision"] == "approve"}
    if decision == "decline":
        status = "declined"
    elif all(r in approved for r in signers):
        status = "signed_off"
    else:
        status = "awaiting_signoff"
    return {"signoffs": signoffs, "status": status}
