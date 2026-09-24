import re
import pandas as pd

from database.did_mapping import create_patient_did

UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


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
        except (UnicodeDecodeError, pd.errors.ParserError):
            # Partially corrupted export: keep every row that still parses and
            # carries a valid patient UUID instead of dropping the whole module.
            return SyntheaRepository._salvage_csv(file_path)
        except OSError as exc:
            # Keep the dashboard usable when an optional Synthea export is
            # missing or damaged; the affected scope simply returns no rows.
            print(f"Warning: could not load {file_path}: {exc}")
            return pd.DataFrame()

    @staticmethod
    def _salvage_csv(file_path):
        frame = pd.read_csv(file_path, encoding_errors="replace", on_bad_lines="skip",
                            engine="python", dtype=str)
        key = "PATIENT" if "PATIENT" in frame.columns else "Id"
        if key in frame.columns:
            frame = frame[frame[key].astype(str).str.fullmatch(UUID_RE, na=False)]
        frame = frame[~frame.apply(lambda r: r.astype(str).str.contains("\ufffd", regex=False).any(), axis=1)]
        print(f"Warning: {file_path} is partially corrupted - salvaged {len(frame)} valid rows")
        return frame.reset_index(drop=True)

    def get_patient_dids(self):
        if "Id" not in self.patients.columns:
            return pd.DataFrame(columns=["DID", "FIRST", "LAST", "BIRTHDATE"])
        self.patients["DID"] = self.patients["Id"].apply(create_patient_did)
        return self.patients[["DID", "FIRST", "LAST", "BIRTHDATE"]]

    def resolve_did(self, did):
        return did.replace("did:patient:", "")

    @staticmethod
    def _canonical_id(value):
        text = str(value).strip().replace("\ufeff", "")
        match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", text)
        return match.group(0).lower() if match else text.lower()

    def query_patient(self, did, scope):
        patient_id = self._canonical_id(self.resolve_did(did))
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
                ids = frame["PATIENT"].astype(str).str.strip()
                result[name] = frame[ids == str(patient_id).strip()]
            elif name == "Patient" and "Id" in frame.columns:
                ids = frame["Id"].astype(str).str.strip()
                result[name] = frame[ids == str(patient_id).strip()]
            else:
                result[name] = pd.DataFrame()
        return result
