from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists
from mcp_utilities import create_text_response


# ---------------------------------------------------------------------------
# Known drug–food interaction data
# Key: lowercase substring of medication name
# Value: list of (food_item, reason)
# ---------------------------------------------------------------------------
_DRUG_FOOD_INTERACTIONS: dict[str, list[tuple[str, str]]] = {
    "warfarin": [
        ("Leafy greens (spinach, kale, broccoli)", "High vitamin K antagonises anticoagulant effect"),
        ("Grapefruit / grapefruit juice", "CYP2C9 inhibition → increased bleeding risk"),
        ("Cranberry juice", "May potentiate INR elevation"),
        ("Alcohol", "Increases bleeding risk and unpredictable INR changes"),
    ],
    "metformin": [
        ("Alcohol", "Increased risk of lactic acidosis"),
    ],
    "simvastatin": [
        ("Grapefruit / grapefruit juice", "CYP3A4 inhibition → increased myopathy risk"),
        ("Large quantities of alcohol", "Increased hepatotoxicity risk"),
    ],
    "atorvastatin": [
        ("Grapefruit / grapefruit juice", "CYP3A4 inhibition → elevated drug levels"),
    ],
    "lisinopril": [
        ("High-potassium foods (bananas, potatoes, salt substitutes)", "Risk of hyperkalaemia"),
    ],
    "spironolactone": [
        ("High-potassium foods (bananas, potatoes, salt substitutes)", "Risk of hyperkalaemia"),
        ("Liquorice", "May reduce diuretic effect"),
    ],
    "ciprofloxacin": [
        ("Dairy products / calcium-fortified foods", "Chelation reduces drug absorption"),
        ("Caffeine", "Inhibits caffeine metabolism → CNS effects"),
    ],
    "tetracycline": [
        ("Dairy products", "Calcium chelation reduces absorption"),
        ("Iron-rich foods", "Reduces drug absorption"),
    ],
    "phenelzine": [
        ("Tyramine-rich foods (aged cheese, cured meats, red wine)", "Hypertensive crisis risk (MAOI interaction)"),
    ],
    "tranylcypromine": [
        ("Tyramine-rich foods (aged cheese, cured meats, red wine)", "Hypertensive crisis risk (MAOI interaction)"),
    ],
    "levothyroxine": [
        ("High-fibre foods / soy", "May reduce absorption"),
        ("Coffee / calcium-rich foods", "Take on empty stomach — food reduces absorption"),
    ],
    "amlodipine": [
        ("Grapefruit / grapefruit juice", "CYP3A4 inhibition → increased hypotensive effect"),
    ],
    "digoxin": [
        ("High-fibre foods (bran)", "Reduces drug absorption"),
        ("Liquorice", "Hypokalaemia potentiates toxicity"),
    ],
}


def _find_interactions(medication_name: str) -> list[tuple[str, str]]:
    name_lower = medication_name.lower()
    for drug_key, interactions in _DRUG_FOOD_INTERACTIONS.items():
        if drug_key in name_lower:
            return interactions
    return []


async def get_drug_food_interactions(
    patientId: Annotated[  # noqa: N803
        str | None,
        Field(description="The id of the patient. This is optional if patient context already exists"),
    ] = None,
    ctx: Context = None,
) -> str:
    if not patientId:
        patientId = get_patient_id_if_context_exists(ctx)
        if not patientId:
            raise ValueError("No patient context found")

    fhir_context = get_fhir_context(ctx)
    if not fhir_context:
        raise ValueError("The fhir context could not be retrieved")

    fhir_client = FhirClient(base_url=fhir_context.url, token=fhir_context.token)

    bundle = await fhir_client.search(
        "MedicationRequest",
        {"patient": patientId, "status": "active"},
    )

    if not bundle or not bundle.get("entry"):
        return create_text_response("No active medications found — no food interactions to report.")

    all_interactions: list[str] = []

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        med_ref = resource.get("medicationCodeableConcept", {})
        name = med_ref.get("text") or (med_ref.get("coding") or [{}])[0].get("display", "")

        if not name:
            continue

        interactions = _find_interactions(name)
        for food, reason in interactions:
            all_interactions.append(f"  ⚠ {name} ✕ {food}\n     Reason: {reason}")

    if not all_interactions:
        return create_text_response(
            "No known drug–food interactions found for this patient's active medications."
        )

    return create_text_response(
        f"Drug–food interactions ({len(all_interactions)} found):\n\n"
        + "\n\n".join(all_interactions)
    )
