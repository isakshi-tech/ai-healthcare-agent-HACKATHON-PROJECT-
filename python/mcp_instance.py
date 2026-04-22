from mcp.server.fastmcp import FastMCP
from tools.patient_age_tool import get_patient_age
from tools.patient_allergies_tool import get_patient_allergies
from tools.patient_id_tool import find_patient_id
from tools.calculate_news2_tool import calculate_news2
from tools.drug_food_interaction_tool import get_drug_food_interactions
from tools.full_assessment_tool import full_assessment
from tools.generate_alert_tool import generate_alert
from tools.nurse_note_tool import get_nurse_note
from tools.nutritional_alert_tool import get_nutritional_alerts
from tools.patient_diagnosis_tool import get_diagnoses
from tools.patient_medications_tool import get_medications
from tools.patient_risk_level_tool import get_risk_level
from tools.patient_vitals_tool import get_patient_vitals
from tools.patient_vitals_trend_tool import get_vitals_trend

mcp = FastMCP("Python Template", stateless_http=True, host="0.0.0.0")

_original_get_capabilities = mcp._mcp_server.get_capabilities

def _patched_get_capabilities(notification_options, experimental_capabilities):
    caps = _original_get_capabilities(notification_options, experimental_capabilities)
    caps.model_extra["extensions"] = {"ai.promptopinion/fhir-context": {}}
    return caps

mcp._mcp_server.get_capabilities = _patched_get_capabilities



mcp.tool(name="GetPatientAge", description="Gets the age of a patient.")(get_patient_age)
mcp.tool(name="GetPatientAllergies", description="Gets the known allergies of a patient.")(get_patient_allergies)
mcp.tool(name="FindPatientId", description="Finds a patient id given a first name and last name")(find_patient_id)
mcp.tool(name="CalculateNEWS2", description="Calculates the NEWS2 score for a patient based on vital signs.")(calculate_news2)
mcp.tool(name="GetDrugFoodInteractions", description="Gets potential drug-food interactions for a patient's medications.")(get_drug_food_interactions)
mcp.tool(name="FullAssessment", description="Performs a full assessment of the patient including vitals, trends, NEWS2, risk level, medications, interactions, alerts, diagnoses, and nurse notes.")(full_assessment)
mcp.tool(name="GenerateAlert", description="Generates an alert based on patient data.")(generate_alert)
mcp.tool(name="GetNurseNote", description="Gets the latest nurse note for a patient.")(get_nurse_note)
mcp.tool(name="GetNutritionalAlerts", description="Gets nutritional alerts for a patient.")(get_nutritional_alerts)
mcp.tool(name="GetDiagnoses", description="Gets the diagnoses for a patient.")(get_diagnoses)
mcp.tool(name="GetMedications", description="Gets the medications for a patient.")(get_medications)
mcp.tool(name="GetRiskLevel", description="Gets the risk level for a patient.")(get_risk_level)
mcp.tool(name="GetPatientVitals", description="Gets the current vitals for a patient.")(get_patient_vitals)
mcp.tool(name="GetVitalsTrend", description="Gets the vitals trend for a patient.")(get_vitals_trend)
