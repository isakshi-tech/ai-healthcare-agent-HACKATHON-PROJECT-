from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists
from mcp_utilities import create_text_response


async def get_vitals_trend(
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
            "_count": "15",  # 3 readings x 5 vitals
        },
    )

    if not bundle or not bundle.get("entry"):
        return create_text_response("No vitals trend data found for this patient.")

    # Group readings by vital code (keep last 3 per vital)
    trends: dict[str, list[str]] = {code: [] for code in vital_codes}

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        coding = resource.get("code", {}).get("coding", [{}])
        code = coding[0].get("code") if coding else None

        if not code or code not in trends:
            continue
        if len(trends[code]) >= 3:
            continue

        date_str = resource.get("effectiveDateTime", "unknown date")[:10]
        value_quantity = resource.get("valueQuantity", {})
        value = value_quantity.get("value")
        unit = value_quantity.get("unit", "")

        components = resource.get("component", [])
        if components:
            parts = []
            for comp in components:
                comp_val = comp.get("valueQuantity", {})
                parts.append(f"{comp_val.get('value')} {comp_val.get('unit', '')}".strip())
            trends[code].append(f"[{date_str}] {' / '.join(parts)}")
        elif value is not None:
            trends[code].append(f"[{date_str}] {value} {unit}".strip())

    lines = []
    for code, label in vital_codes.items():
        readings = trends.get(code, [])
        if readings:
            lines.append(f"{label}:")
            for r in readings:
                lines.append(f"  {r}")

    if not lines:
        return create_text_response("No vitals trend data could be parsed for this patient.")

    return create_text_response("Last 3 vitals readings:\n" + "\n".join(lines))
