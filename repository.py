import pandas as pd

from database.did_mapping import (
    create_patient_did
)



class SyntheaRepository:
    def __init__(self,path):
        self.patients=pd.read_csv(
            path+"/patients.csv"
        )

        self.conditions=pd.read_csv(
            path+"/conditions.csv"
        )

        self.observations=pd.read_csv(
            path+"/observations.csv"
        )

        self.medications=pd.read_csv(
            path+"/medications.csv"
        )

        self.procedures=pd.read_csv(
            path+"/procedures.csv"
        )


    # Patient DID
    def get_patient_dids(self):
        self.patients["DID"] = self.patients["Id"].apply(create_patient_did)
        return self.patients[
            [
                "DID",
                "FIRST",
                "LAST",
                "BIRTHDATE"
            ]
        ]




    # DID to Synthea ID
    def resolve_did(self,did):
        return did.replace(
            "did:patient:",
            ""
        )

    # data query
    def query_patient(self,did,scope):
        patient_id = self.resolve_did(did)

        result={}
        if "Patient" in scope:
            result["Patient"]=(
                self.patients[self.patients.Id==patient_id]
            )

        if "Observation" in scope:
            result["Observation"]=(
                self.observations[self.observations.PATIENT==patient_id]
            )



        if "Medication" in scope:
            result["Medication"]=(
                self.medications[self.medications.PATIENT==patient_id]
            )


        if "Condition" in scope:
            result["Condition"]=(self.conditions[self.conditions.PATIENT==patient_id])


        if "Procedure" in scope:
            result["Procedure"]=(
                self.procedures[self.procedures.PATIENT==patient_id]
            )


        return result

    ##########################

    # def query_patient(self,did):
    #     patient_id=self.resolve_did(
    #         did
    #     )
    #     return {

    #     "Patient":
    #     self.patients[
    #         self.patients.Id==patient_id
    #     ],

    #     "Observation":

    #     self.observations[
    #         self.observations.PATIENT==patient_id
    #     ],



    #     "Medication":

    #     self.medications[
    #         self.medications.PATIENT==patient_id
    #     ],



    #     "Condition":

    #     self.conditions[
    #         self.conditions.PATIENT==patient_id
    #     ],



    #     "Procedure":

    #     self.procedures[
    #         self.procedures.PATIENT==patient_id
    #     ]


    #     }