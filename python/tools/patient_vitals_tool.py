from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists
from mcp_utilities import create_text_response


async def get_patient_vitals(
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

    # LOINC codes: HR, O2 sat, BP, body temp, respiratory rate
    vital_codes = {
        "8867-4": "Heart Rate (HR)",
        "2708-6": "Oxygen Saturation (O2)",
        "55284-4": "Blood Pressure (BP)",
        "8310-5": "Body Temperature (Temp)",
        "9279-1": "Respiratory Rate (RR)",
    }

    bundle = await fhir_client.search(
        "Observation",
        {
            "patient": patientId,
            "code": ",".join(vital_codes.keys()),
            "_sort": "-date",
            "_count": "5",
        },
    )

    if not bundle or not bundle.get("entry"):
        return create_text_response("No vitals found for this patient.")

    results = []
    seen_codes = set()

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        coding = resource.get("code", {}).get("coding", [{}])
        code = coding[0].get("code") if coding else None

        if not code or code in seen_codes:
            continue
        seen_codes.add(code)

        label = vital_codes.get(code, code)
        value_quantity = resource.get("valueQuantity", {})
        value = value_quantity.get("value")
        unit = value_quantity.get("unit", "")

        # Handle BP (component-based)
        components = resource.get("component", [])
        if components:
            parts = []
            for comp in components:
                comp_val = comp.get("valueQuantity", {})
                comp_label = comp.get("code", {}).get("coding", [{}])[0].get("display", "")
                parts.append(f"{comp_label}: {comp_val.get('value')} {comp_val.get('unit', '')}".strip())
            results.append(f"{label}: {' / '.join(parts)}")
        elif value is not None:
            results.append(f"{label}: {value} {unit}".strip())

    if not results:
        return create_text_response("No vital signs data could be parsed for this patient.")

    return create_text_response("Latest vitals:\n" + "\n".join(results))
