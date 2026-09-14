import pandas as pd

from database.did_mapping import create_patient_did


class SyntheaRepository:
    def __init__(self, path):
        self.patients = self._load_csv(path, "patients.csv")
        self.conditions = self._load_csv(path, "conditions.csv")
        self.observations = self._load_csv(path, "observations.csv")
        self.medications = self._load_csv(path, "medications.csv")
        self.procedures = self._load_csv(path, "procedures.csv")

    @staticmethod
    def _load_csv(path, filename):
        file_path = f"{path}/{filename}"
        try:
            return pd.read_csv(file_path)
        except (UnicodeDecodeError, pd.errors.ParserError, OSError) as exc:
            # Keep the dashboard usable when an optional Synthea export is
            # missing or damaged; the affected scope simply returns no rows.
            print(f"Warning: could not load {file_path}: {exc}")
            return pd.DataFrame()

    def get_patient_dids(self):
        if "Id" not in self.patients.columns:
            return pd.DataFrame(columns=["DID", "FIRST", "LAST", "BIRTHDATE"])
        self.patients["DID"] = self.patients["Id"].apply(create_patient_did)
        return self.patients[["DID", "FIRST", "LAST", "BIRTHDATE"]]

    def resolve_did(self, did):
        return did.replace("did:patient:", "")

    def query_patient(self, did, scope):
        patient_id = self.resolve_did(did)
        result = {}
        datasets = {
            "Patient": self.patients,
            "Observation": self.observations,
            "Medication": self.medications,
            "Condition": self.conditions,
            "Procedure": self.procedures,
        }
        for name in scope:
            frame = datasets.get(name)
            if frame is None:
                continue
            if "PATIENT" in frame.columns:
                result[name] = frame[frame["PATIENT"] == patient_id]
            elif name == "Patient" and "Id" in frame.columns:
                result[name] = frame[frame["Id"] == patient_id]
            else:
                result[name] = pd.DataFrame()
        return result
