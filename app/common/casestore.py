from .config import PROJECT_ID

COLLECTION = "cases"


class MemoryStore:
    def __init__(self):
        self.cases = {}

    def save(self, doc):
        self.cases[doc["case_id"]] = doc

    def get(self, case_id):
        return self.cases.get(case_id)


class FirestoreStore:
    def __init__(self):
        from google.cloud import firestore

        self._db = firestore.Client(project=PROJECT_ID)

    def save(self, doc):
        self._db.collection(COLLECTION).document(doc["case_id"]).set(doc)

    def get(self, case_id):
        snap = self._db.collection(COLLECTION).document(case_id).get()
        return snap.to_dict() if snap.exists else None
