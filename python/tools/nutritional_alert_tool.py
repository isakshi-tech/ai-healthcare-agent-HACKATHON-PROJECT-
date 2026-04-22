from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists
from mcp_utilities import create_text_response


# ---------------------------------------------------------------------------
# Condition → nutritional guidance
# Key: lowercase substring to match condition display text
# ---------------------------------------------------------------------------
_CONDITION_NUTRITION: dict[str, str] = {
    "diabetes": "Low glycaemic index diet. Limit refined sugars and white carbohydrates. Regular meal timing. Monitor carbohydrate intake.",
    "hypertension": "DASH diet recommended. Restrict sodium to <2g/day. Increase potassium-rich foods (unless on K-sparing diuretics). Limit alcohol.",
    "heart failure": "Fluid restriction (typically 1.5–2L/day). Low sodium (<2g/day). Monitor daily weight. Small frequent meals to reduce cardiac workload.",
    "chronic kidney": "Limit potassium, phosphorus, and sodium. Moderate protein restriction. Fluid restriction if oliguric. Avoid high-potassium foods.",
    "renal failure": "Limit potassium, phosphorus, and sodium. Moderate protein restriction. Fluid restriction if oliguric.",
    "celiac": "Strict gluten-free diet. Avoid wheat, barley, rye. Ensure adequate calcium and vitamin D supplementation.",
    "crohn": "Low-residue diet during flares. Adequate caloric intake. Vitamin B12 and iron monitoring. Consider nutritional supplements.",
    "ulcerative colitis": "Low-residue diet during flares. Adequate hydration. Avoid trigger foods. Vitamin D and calcium supplementation.",
    "liver": "Adequate protein intake (unless hepatic encephalopathy). Limit alcohol completely. Sodium restriction if ascites present.",
    "obesity": "Calorie-controlled diet. Increase fibre. Reduce saturated fats and ultra-processed foods. Regular meal structure.",
    "malnutrition": "High-calorie, high-protein diet. Consider oral nutritional supplements. Dietitian referral recommended.",
    "anaemia": "Increase iron-rich foods (red meat, legumes, fortified cereals). Vitamin C with iron-rich meals to aid absorption. Folate and B12 sources.",
    "osteoporosis": "Adequate calcium (1000–1200mg/day) and vitamin D. Dairy, leafy greens, fortified foods. Limit alcohol and caffeine.",
    "gout": "Limit purine-rich foods (red meat, shellfish, organ meats). Avoid fructose-sweetened drinks. Stay well hydrated. Limit alcohol especially beer.",
    "hyperlipidaemia": "Reduce saturated and trans fats. Increase soluble fibre (oats, beans). Omega-3 rich foods. Limit dietary cholesterol.",
    "dysphagia": "Texture-modified diet as per IDDSI framework. Thickened fluids if required. Risk of aspiration — involve speech and language therapy.",
}


async def get_nutritional_alerts(
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
        return create_text_response("No active conditions found — no nutritional recommendations available.")

    recommendations: list[str] = []
    seen: set[str] = set()

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        code = resource.get("code", {})
        condition_name = code.get("text") or (code.get("coding") or [{}])[0].get("display", "")

        if not condition_name:
            continue

        condition_lower = condition_name.lower()
        for key, advice in _CONDITION_NUTRITION.items():
            if key in condition_lower and key not in seen:
                seen.add(key)
                recommendations.append(f"  📋 {condition_name}:\n     {advice}")

    if not recommendations:
        return create_text_response(
            "No specific nutritional recommendations found for this patient's active conditions."
        )

    return create_text_response(
        f"Nutritional recommendations ({len(recommendations)}):\n\n"
        + "\n\n".join(recommendations)
    )
