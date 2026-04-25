from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_utilities import get_patient_id_if_context_exists
from mcp_utilities import create_text_response
from tools.patient_vitals_tool import get_patient_vitals
from tools.patient_vitals_trend_tool import get_vitals_trend

from tools.patient_risk_level_tool import get_risk_level
from tools.patient_medications_tool import get_medications
from tools.drug_food_interaction_tool import get_drug_food_interactions
from tools.nutritional_alert_tool import get_nutritional_alerts
from tools.patient_diagnosis_tool import get_diagnoses
from tools.nurse_note_tool import get_nurse_note
from tools.generate_alert_tool import generate_alert


async def full_assessment(
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
        Field(description="True if the patient is Alert (ACVPU), False otherwise"),
    ] = True,
    ctx: Context = None,
) -> str:
    if not patientId:
        patientId = get_patient_id_if_context_exists(ctx)
        if not patientId:
            raise ValueError("No patient context found")

    # ── Run all tools ─────────────────────────────────────────────────────
    sections: dict[str, str] = {}

    async def _run(label: str, coro):
        try:
            sections[label] = await coro
        except Exception as exc:  # noqa: BLE001
            sections[label] = f"[Error: {exc}]"

    await _run("Current Vitals", get_patient_vitals(patientId=patientId, ctx=ctx))
    await _run("Vitals Trend (last 3)", get_vitals_trend(patientId=patientId, ctx=ctx))
    await _run(
        "NEWS2 Score",
        calculate_news2(
            patientId=patientId,
            on_supplemental_oxygen=on_supplemental_oxygen,
            consciousness_alert=consciousness_alert,
            ctx=ctx,
        ),
    )
    await _run(
        "Risk Level",
        get_risk_level(
            patientId=patientId,
            on_supplemental_oxygen=on_supplemental_oxygen,
            consciousness_alert=consciousness_alert,
            ctx=ctx,
        ),
    )
    await _run("Active Medications", get_medications(patientId=patientId, ctx=ctx))
    await _run("Drug–Food Interactions", get_drug_food_interactions(patientId=patientId, ctx=ctx))
    await _run("Nutritional Recommendations", get_nutritional_alerts(patientId=patientId, ctx=ctx))
    await _run("Active Diagnoses", get_diagnoses(patientId=patientId, ctx=ctx))
    await _run("Last Nurse Note", get_nurse_note(patientId=patientId, ctx=ctx))
    await _run(
        "Full Alert",
        generate_alert(
            patientId=patientId,
            on_supplemental_oxygen=on_supplemental_oxygen,
            consciousness_alert=consciousness_alert,
            ctx=ctx,
        ),
    )

    # ── Assemble report ───────────────────────────────────────────────────
    divider = "=" * 60
    report_lines = [divider, "  FULL PATIENT ASSESSMENT", divider, ""]

    for label, content in sections.items():
        report_lines.append(f"── {label.upper()} {'─' * max(0, 54 - len(label))}")
        report_lines.append(content)
        report_lines.append("")

    report_lines.append(divider)

    return create_text_response("\n".join(report_lines))
