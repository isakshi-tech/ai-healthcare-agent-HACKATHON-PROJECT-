from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists
from mcp_utilities import create_text_response


def _news2_risk(score: int) -> str:
    if score <= 4:
        return "LOW"
    if score <= 6:
        return "MEDIUM"
    return "HIGH"


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


async def generate_alert(
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
        Field(description="True if Alert (ACVPU), False otherwise"),
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

    # ── Patient demographics ──────────────────────────────────────────────
    patient = await fhir_client.read(f"Patient/{patientId}")
    if not patient:
        return create_text_response("Patient could not be found.", is_error=True)

    name_list = patient.get("name", [{}])
    given = " ".join(name_list[0].get("given", [])) if name_list else ""
    family = name_list[0].get("family", "") if name_list else ""
    patient_name = f"{given} {family}".strip() or patientId
    dob = patient.get("birthDate", "Unknown")

    # ── Vitals ────────────────────────────────────────────────────────────
    obs_bundle = await fhir_client.search(
        "Observation",
        {
            "patient": patientId,
            "code": "8867-4,2708-6,55284-4,8310-5,9279-1",
            "_sort": "-date",
            "_count": "10",
        },
    )

    rr = _get_latest_value(obs_bundle or {}, "9279-1")
    spo2 = _get_latest_value(obs_bundle or {}, "2708-6")
    sbp = _get_latest_value(obs_bundle or {}, "55284-4")
    hr = _get_latest_value(obs_bundle or {}, "8867-4")
    temp = _get_latest_value(obs_bundle or {}, "8310-5")

    vitals_available = all(v is not None for v in [rr, spo2, sbp, hr, temp])
    news2_score: int | None = None
    risk_level = "UNKNOWN"

    if vitals_available:
        if temp > 45:
            temp = (temp - 32) * 5 / 9

        def s_rr(v):
            if v <= 8: return 3
            if v <= 11: return 1
            if v <= 20: return 0
            if v <= 24: return 2
            return 3

        def s_spo2(v):
            if v <= 91: return 3
            if v <= 93: return 2
            if v <= 95: return 1
            return 0

        def s_sbp(v):
            if v <= 90: return 3
            if v <= 100: return 2
            if v <= 110: return 1
            if v <= 219: return 0
            return 3

        def s_hr(v):
            if v <= 40: return 3
            if v <= 50: return 1
            if v <= 90: return 0
            if v <= 110: return 1
            if v <= 130: return 2
            return 3

        def s_temp(v):
            if v <= 35.0: return 3
            if v <= 36.0: return 1
            if v <= 38.0: return 0
            if v <= 39.0: return 1
            return 2

        news2_score = (
            s_rr(rr) + s_spo2(spo2) + (2 if on_supplemental_oxygen else 0)
            + s_sbp(sbp) + s_hr(hr) + s_temp(temp) + (0 if consciousness_alert else 3)
        )
        risk_level = _news2_risk(news2_score)

    # ── Active diagnoses ──────────────────────────────────────────────────
    dx_bundle = await fhir_client.search(
        "Condition", {"patient": patientId, "clinical-status": "active"}
    )
    diagnoses = []
    if dx_bundle and dx_bundle.get("entry"):
        for e in dx_bundle["entry"]:
            res = e.get("resource", {})
            code = res.get("code", {})
            dx = code.get("text") or (code.get("coding") or [{}])[0].get("display", "")
            if dx:
                diagnoses.append(dx)

    # ── Active medications ────────────────────────────────────────────────
    med_bundle = await fhir_client.search(
        "MedicationRequest", {"patient": patientId, "status": "active"}
    )
    meds = []
    if med_bundle and med_bundle.get("entry"):
        for e in med_bundle["entry"]:
            res = e.get("resource", {})
            mc = res.get("medicationCodeableConcept", {})
            name = mc.get("text") or (mc.get("coding") or [{}])[0].get("display", "")
            if name:
                meds.append(name)

    # ── Compose alert text ────────────────────────────────────────────────
    lines = [
        "=" * 60,
        "  CLINICAL ALERT",
        "=" * 60,
        f"  Patient  : {patient_name}",
        f"  ID       : {patientId}",
        f"  DOB      : {dob}",
        "-" * 60,
        "  CURRENT VITALS",
        "-" * 60,
    ]

    if vitals_available:
        lines += [
            f"  HR       : {hr} bpm",
            f"  SpO2     : {spo2}%",
            f"  BP (sys) : {sbp} mmHg",
            f"  Temp     : {temp:.1f} °C",
            f"  RR       : {rr} breaths/min",
            f"  O2 Supp  : {'Yes' if on_supplemental_oxygen else 'No'}",
            f"  ACVPU    : {'Alert' if consciousness_alert else 'Impaired'}",
        ]
    else:
        lines.append("  Vitals data unavailable.")

    lines += [
        "-" * 60,
        "  NEWS2 ASSESSMENT",
        "-" * 60,
        f"  Score    : {news2_score if news2_score is not None else 'N/A'} / 20",
        f"  Risk     : {risk_level}",
        "-" * 60,
        "  ACTIVE DIAGNOSES",
        "-" * 60,
    ]
    lines += [f"  • {d}" for d in diagnoses] if diagnoses else ["  None recorded."]
    lines += [
        "-" * 60,
        "  ACTIVE MEDICATIONS",
        "-" * 60,
    ]
    lines += [f"  • {m}" for m in meds] if meds else ["  None recorded."]
    lines.append("=" * 60)

    return create_text_response("\n".join(lines))
