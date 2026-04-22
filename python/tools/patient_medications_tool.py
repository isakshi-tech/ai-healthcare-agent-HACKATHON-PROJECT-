from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists
from mcp_utilities import create_text_response


async def get_medications(
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
        return create_text_response("No active medications found for this patient.")

    medications = []
    warnings = []

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})

        # Medication name
        med_ref = resource.get("medicationCodeableConcept", {})
        name = med_ref.get("text") or (med_ref.get("coding") or [{}])[0].get("display", "Unknown medication")

        # Dosage
        dosage_list = resource.get("dosageInstruction", [])
        dosage_text = dosage_list[0].get("text", "") if dosage_list else ""

        # Warnings / notes
        note_list = resource.get("note", [])
        for note in note_list:
            note_text = note.get("text", "").strip()
            if note_text:
                warnings.append(f"  ⚠ {name}: {note_text}")

        entry_line = f"  • {name}"
        if dosage_text:
            entry_line += f" — {dosage_text}"
        medications.append(entry_line)

    result = f"Active medications ({len(medications)}):\n" + "\n".join(medications)
    if warnings:
        result += "\n\nWarnings / Notes:\n" + "\n".join(warnings)

    return create_text_response(result)
