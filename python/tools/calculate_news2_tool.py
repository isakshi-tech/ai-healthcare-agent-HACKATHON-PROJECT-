from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists
from mcp_utilities import create_text_response


# ---------------------------------------------------------------------------
# NEWS2 scoring helpers
# ---------------------------------------------------------------------------

def _score_respiration_rate(rr: float) -> int:
    if rr <= 8:
        return 3
    if rr <= 11:
        return 1
    if rr <= 20:
        return 0
    if rr <= 24:
        return 2
    return 3


def _score_spo2(spo2: float, on_o2: bool) -> int:
    """Scale 1 (default, no known hypercapnic respiratory failure)."""
    if spo2 <= 91:
        return 3
    if spo2 <= 93:
        return 2
    if spo2 <= 95:
        return 1
    return 0


def _score_systolic_bp(sbp: float) -> int:
    if sbp <= 90:
        return 3
    if sbp <= 100:
        return 2
    if sbp <= 110:
        return 1
    if sbp <= 219:
        return 0
    return 3


def _score_heart_rate(hr: float) -> int:
    if hr <= 40:
        return 3
    if hr <= 50:
        return 1
    if hr <= 90:
        return 0
    if hr <= 110:
        return 1
    if hr <= 130:
        return 2
    return 3


def _score_temperature(temp_c: float) -> int:
    if temp_c <= 35.0:
        return 3
    if temp_c <= 36.0:
        return 1
    if temp_c <= 38.0:
        return 0
    if temp_c <= 39.0:
        return 1
    return 2


def _score_consciousness(alert: bool) -> int:
    return 0 if alert else 3


def _score_supplemental_o2(on_o2: bool) -> int:
    return 2 if on_o2 else 0


def _get_latest_value(bundle: dict, target_code: str) -> float | None:
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        codings = resource.get("code", {}).get("coding", [])
        codes = [c.get("code") for c in codings]
        if target_code in codes:
            vq = resource.get("valueQuantity", {})
            if vq.get("value") is not None:
                return float(vq["value"])
            # BP systolic from component
            for comp in resource.get("component", []):
                comp_codes = [c.get("code") for c in comp.get("code", {}).get("coding", [])]
                if "8480-6" in comp_codes:  # systolic LOINC
                    return float(comp.get("valueQuantity", {}).get("value", 0))
    return None


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

async def calculate_news2(
    patientId: Annotated[  # noqa: N803
        str | None,
        Field(description="The id of the patient. This is optional if patient context already exists"),
    ] = None,
    on_supplemental_oxygen: Annotated[
        bool,
        Field(description="Whether the patient is currently on supplemental oxygen"),
    ] = False,
    consciousness_alert: Annotated[
        bool,
        Field(description="True if the patient is Alert (A on ACVPU), False if confused/voice/pain/unresponsive"),
    ] = True,
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
        "Observation",
        {
            "patient": patientId,
            "code": "8867-4,2708-6,55284-4,8310-5,9279-1",
            "_sort": "-date",
            "_count": "10",
        },
    )

    if not bundle or not bundle.get("entry"):
        return create_text_response("No observations found to calculate NEWS2.", is_error=True)

    rr = _get_latest_value(bundle, "9279-1")
    spo2 = _get_latest_value(bundle, "2708-6")
    sbp = _get_latest_value(bundle, "55284-4")
    hr = _get_latest_value(bundle, "8867-4")
    temp = _get_latest_value(bundle, "8310-5")

    missing = [
        name for name, val in [("RR", rr), ("SpO2", spo2), ("BP", sbp), ("HR", hr), ("Temp", temp)]
        if val is None
    ]
    if missing:
        return create_text_response(
            f"Cannot calculate NEWS2. Missing observations: {', '.join(missing)}.",
            is_error=True,
        )

    # Convert temp to Celsius if stored in Fahrenheit
    if temp > 45:
        temp = (temp - 32) * 5 / 9

    scores = {
        "Respiration Rate": _score_respiration_rate(rr),
        "SpO2": _score_spo2(spo2, on_supplemental_oxygen),
        "Supplemental O2": _score_supplemental_o2(on_supplemental_oxygen),
        "Systolic BP": _score_systolic_bp(sbp),
        "Heart Rate": _score_heart_rate(hr),
        "Temperature": _score_temperature(temp),
        "Consciousness": _score_consciousness(consciousness_alert),
    }

    total = sum(scores.values())

    score_lines = "\n".join(f"  {k}: {v}" for k, v in scores.items())
    return create_text_response(
        f"NEWS2 Score: {total} / 20\n\nBreakdown:\n{score_lines}\n\n"
        f"Values used: RR={rr}, SpO2={spo2}%, SBP={sbp}mmHg, HR={hr}bpm, Temp={temp:.1f}°C"
    )
