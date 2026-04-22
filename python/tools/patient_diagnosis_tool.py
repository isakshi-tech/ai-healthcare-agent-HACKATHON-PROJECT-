from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists
from mcp_utilities import create_text_response


async def get_diagnoses(
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
        "Condition",
        {"patient": patientId, "clinical-status": "active"},
    )

    if not bundle or not bundle.get("entry"):
        return create_text_response("No active diagnoses found for this patient.")

    diagnoses: list[str] = []

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})

        code = resource.get("code", {})
        name = code.get("text") or (code.get("coding") or [{}])[0].get("display", "Unknown condition")

        # Onset
        onset = resource.get("onsetDateTime") or resource.get("onsetString", "")
        onset_str = f" (onset: {onset[:10]})" if onset else ""

        # Severity
        severity = resource.get("severity", {})
        severity_text = severity.get("text") or (severity.get("coding") or [{}])[0].get("display", "")
        severity_str = f" — severity: {severity_text}" if severity_text else ""

        diagnoses.append(f"  • {name}{onset_str}{severity_str}")

    if not diagnoses:
        return create_text_response("No active diagnoses could be parsed for this patient.")

    return create_text_response(
        f"Active diagnoses ({len(diagnoses)}):\n" + "\n".join(diagnoses)
    )
