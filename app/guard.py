import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .common import config
from .common.config import PROJECT_ID

COLLECTION = "guard"

MESSAGES = {
    "visitor_day": "You have used your live runs for today. You can view the recorded run, or try again tomorrow.",
    "global_day": "Today's live runs are used up for everyone. You can view the recorded run, or try again tomorrow.",
    "global_month": "This month's live runs are used up. You can view the recorded run.",
    "guard_error": "Live runs are unavailable right now. You can view the recorded run.",
}


def default_limits():
    return {
        "visitor_day": config.LIVE_PER_VISITOR_DAY,
        "global_day": config.LIVE_PER_DAY,
        "global_month": config.LIVE_PER_MONTH,
    }


class MemoryCounters:
    def __init__(self):
        self.n = {}

    def counts(self, keys):
        return [self.n.get(key, 0) for key in keys]

    def reserve(self, checks):
        counts = self.counts([key for _reason, key, _limit in checks])
        for (reason, _key, limit), n in zip(checks, counts):
            if n >= limit:
                return False, reason, counts
        for _reason, key, _limit in checks:
            self.n[key] = self.n.get(key, 0) + 1
        return True, None, [n + 1 for n in counts]


class FirestoreCounters:
    def __init__(self):
        from google.cloud import firestore

        self._firestore = firestore
        self._db = firestore.Client(project=PROJECT_ID)

    def _ref(self, key):
        return self._db.collection(COLLECTION).document(key)

    def counts(self, keys):
        snaps = {snap.id: snap for snap in self._db.get_all([self._ref(k) for k in keys])}
        return [
            snaps[key].to_dict().get("n", 0) if key in snaps and snaps[key].exists else 0
            for key in keys
        ]

    def reserve(self, checks):
        firestore = self._firestore

        @firestore.transactional
        def run(transaction):
            counts = []
            for _reason, key, _limit in checks:
                snap = self._ref(key).get(transaction=transaction)
                counts.append(snap.to_dict().get("n", 0) if snap.exists else 0)
            for (reason, _key, limit), n in zip(checks, counts):
                if n >= limit:
                    return False, reason, counts
            for (_reason, key, _limit), n in zip(checks, counts):
                transaction.set(self._ref(key), {"n": n + 1})
            return True, None, [n + 1 for n in counts]

        return run(self._db.transaction())


@dataclass(frozen=True)
class Decision:
    ok: bool
    reason: str = None
    remaining: dict = field(default_factory=dict)

    @property
    def left(self):
        return min(self.remaining.values()) if self.remaining else 0

    @property
    def message(self):
        return "" if self.ok else MESSAGES.get(self.reason, "")


class Guard:
    def __init__(self, counters, limits=None, salt=None, clock=None):
        self.counters = counters
        self.limits = limits or default_limits()
        self.salt = salt if salt is not None else config.VISITOR_SALT
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def visitor_id(self, address):
        raw = (address or "unknown").encode()
        return hmac.new(self.salt.encode(), raw, hashlib.sha256).hexdigest()[:16]

    def _checks(self, address):
        now = self.clock()
        day, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
        return [
            ("visitor_day", f"visitor-{self.visitor_id(address)}-{day}", self.limits["visitor_day"]),
            ("global_day", f"day-{day}", self.limits["global_day"]),
            ("global_month", f"month-{month}", self.limits["global_month"]),
        ]

    @staticmethod
    def _remaining(checks, counts):
        return {reason: max(0, limit - n) for (reason, _key, limit), n in zip(checks, counts)}

    def reserve(self, address):
        checks = self._checks(address)
        try:
            ok, reason, counts = self.counters.reserve(checks)
        except Exception:
            return Decision(False, "guard_error", {})
        return Decision(ok, reason, self._remaining(checks, counts))

    def status(self, address):
        checks = self._checks(address)
        try:
            counts = self.counters.counts([key for _reason, key, _limit in checks])
        except Exception:
            return Decision(False, "guard_error", {})
        remaining = self._remaining(checks, counts)
        reason = next((r for r, left in remaining.items() if left == 0), None)
        return Decision(reason is None, reason, remaining)
