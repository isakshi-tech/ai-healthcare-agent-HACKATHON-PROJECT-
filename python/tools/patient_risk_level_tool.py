from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists
from mcp_utilities import create_text_response


def _news2_to_risk(score: int) -> tuple[str, str]:
    """Return (risk_level, clinical_response) based on NEWS2 score."""
    if score <= 4:
        return "LOW", "Ward-based monitoring. Reassess every 4–6 hours minimum."
    if score <= 6:
        return "MEDIUM", "Urgent review by ward doctor. Increase monitoring frequency."
    return "HIGH", "Emergency review required. Consider ICU/HDU escalation immediately."


def _get_latest_value(bundle: dict, target_code: str) -> float | None:
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        codings = resource.get("code", {}).get("coding", [])
        codes = [c.get("code") for c in codings]
        if target_code in codes:
            vq = resource.get("valueQuantity", {})
            if vq.get("value") is not None:
                return float(vq["value"])
            for comp in resource.get("component", []):
                comp_codes = [c.get("code") for c in comp.get("code", {}).get("coding", [])]
                if "8480-6" in comp_codes:
                    return float(comp.get("valueQuantity", {}).get("value", 0))
    return None


def _score_rr(rr: float) -> int:
    if rr <= 8: return 3
    if rr <= 11: return 1
    if rr <= 20: return 0
    if rr <= 24: return 2
    return 3


def _score_spo2(v: float) -> int:
    if v <= 91: return 3
    if v <= 93: return 2
    if v <= 95: return 1
    return 0


def _score_sbp(v: float) -> int:
    if v <= 90: return 3
    if v <= 100: return 2
    if v <= 110: return 1
    if v <= 219: return 0
    return 3


def _score_hr(v: float) -> int:
    if v <= 40: return 3
    if v <= 50: return 1
    if v <= 90: return 0
    if v <= 110: return 1
    if v <= 130: return 2
    return 3


def _score_temp(v: float) -> int:
    if v <= 35.0: return 3
    if v <= 36.0: return 1
    if v <= 38.0: return 0
    if v <= 39.0: return 1
    return 2


async def get_risk_level(
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
        Field(description="True if the patient is Alert, False otherwise (ACVPU)"),
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
        return create_text_response("No observations found to determine risk level.", is_error=True)

    rr = _get_latest_value(bundle, "9279-1")
    spo2 = _get_latest_value(bundle, "2708-6")
    sbp = _get_latest_value(bundle, "55284-4")
    hr = _get_latest_value(bundle, "8867-4")
    temp = _get_latest_value(bundle, "8310-5")

    missing = [n for n, v in [("RR", rr), ("SpO2", spo2), ("BP", sbp), ("HR", hr), ("Temp", temp)] if v is None]
    if missing:
        return create_text_response(
            f"Cannot determine risk level. Missing: {', '.join(missing)}.", is_error=True
        )

    if temp > 45:
        temp = (temp - 32) * 5 / 9

    score = (
        _score_rr(rr)
        + _score_spo2(spo2)
        + (2 if on_supplemental_oxygen else 0)
        + _score_sbp(sbp)
        + _score_hr(hr)
        + _score_temp(temp)
        + (0 if consciousness_alert else 3)
    )

    risk, response = _news2_to_risk(score)

    return create_text_response(
        f"Risk Level: {risk}\n"
        f"NEWS2 Score: {score} / 20\n"
        f"Recommended Response: {response}"
    )
