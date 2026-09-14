import re
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
            frame = pd.read_csv(file_path, encoding="utf-8-sig")
            frame.columns = [str(column).strip().upper() for column in frame.columns]
            return frame
        except (UnicodeDecodeError, pd.errors.ParserError, OSError) as exc:
            print(f"Warning: could not load {file_path}: {exc}")
            return pd.DataFrame()

    @staticmethod
    def _canonical_id(value):
        text = str(value).strip().replace("\ufeff", "")
        match = re.search(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            text,
        )
        return match.group(0).lower() if match else text.lower()

    def get_patient_dids(self):
        if "ID" not in self.patients.columns:
            return pd.DataFrame(columns=["DID", "FIRST", "LAST", "BIRTHDATE"])
        self.patients["DID"] = self.patients["ID"].apply(create_patient_did)
        columns = [column for column in ["DID", "FIRST", "LAST", "BIRTHDATE"] if column in self.patients]
        return self.patients[columns]

    def resolve_did(self, did):
        return str(did).replace("did:patient:", "", 1)

    def query_patient(self, did, scope):
        patient_id = self._canonical_id(self.resolve_did(did))
        datasets = {
            "Patient": self.patients,
            "Observation": self.observations,
            "Medication": self.medications,
            "Condition": self.conditions,
            "Procedure": self.procedures,
        }
        result = {}
        for name in scope:
            frame = datasets.get(name, pd.DataFrame())
            id_column = "PATIENT" if "PATIENT" in frame.columns else ("ID" if name == "Patient" and "ID" in frame.columns else None)
            if id_column is None:
                result[name] = pd.DataFrame()
                continue
            ids = frame[id_column].map(self._canonical_id)
            result[name] = frame.loc[ids == patient_id].copy()
        return result
