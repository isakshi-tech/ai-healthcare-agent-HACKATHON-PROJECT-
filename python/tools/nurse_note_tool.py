from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists
from mcp_utilities import create_text_response


async def get_nurse_note(
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

    # Search for the most recent nursing clinical note
    bundle = await fhir_client.search(
        "DocumentReference",
        {
            "patient": patientId,
            "type": "34746-8",  # LOINC: Nurse Note
            "_sort": "-date",
            "_count": "1",
        },
    )

    # Fallback: try ClinicalImpression if no DocumentReference found
    if not bundle or not bundle.get("entry"):
        bundle = await fhir_client.search(
            "ClinicalImpression",
            {
                "patient": patientId,
                "_sort": "-date",
                "_count": "1",
            },
        )

    if not bundle or not bundle.get("entry"):
        return create_text_response("No nurse notes found for this patient.")

    entry = bundle["entry"][0]
    resource = entry.get("resource", {})
    resource_type = resource.get("resourceType", "")

    if resource_type == "DocumentReference":
        date_str = resource.get("date", "")[:10]
        author_list = resource.get("author", [])
        author = author_list[0].get("display", "Unknown") if author_list else "Unknown"

        content_list = resource.get("content", [])
        note_text = ""
        for content in content_list:
            attachment = content.get("attachment", {})
            note_text = attachment.get("data", "") or attachment.get("url", "")
            if note_text:
                break

        if not note_text:
            note_text = resource.get("description", "No content available.")

        return create_text_response(
            f"Last nurse note [{date_str}] by {author}:\n\n{note_text}"
        )

    if resource_type == "ClinicalImpression":
        date_str = resource.get("date", "")[:10]
        assessor = resource.get("assessor", {}).get("display", "Unknown")
        summary = resource.get("summary", "No summary available.")
        return create_text_response(
            f"Last clinical note [{date_str}] by {assessor}:\n\n{summary}"
        )

    return create_text_response("No nurse notes could be parsed for this patient.")
