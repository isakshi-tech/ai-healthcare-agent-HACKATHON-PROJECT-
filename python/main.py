from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mcp_instance import mcp

__all__ = [
    "calculate_news2",
    "find_patient_id",
    "full_assessment",
    "generate_alert",
    "get_diagnoses",
    "get_drug_food_interactions",
    "get_medications",
    "get_nurse_note",
    "get_nutritional_alerts",
    "get_patient_age",
    "get_patient_allergies",
    "get_risk_level",
    "get_patient_vitals",
    "get_vitals_trend",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/tools")
async def list_tools():
    return {"tools": __all__}


app.mount("/", mcp.streamable_http_app())