from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_audio import router as audio_router
from app.api.routes_audio import v1_router as audio_v1_router
from app.api.routes_audit import router as audit_router
from app.api.routes_ia import router as ia_router
from app.api.routes_ia import v1_router as ia_v1_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_questionnaire import router as questionnaire_router
from app.api.routes_review import router as review_router
from app.api.routes_sessions import router as sessions_router

app = FastAPI(
    title="Reconocimiento Medico IA",
    version="0.1.0",
    description="Servicio IA para generar sugerencias codificadas contra el cuestionario medico.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3010",
        "http://127.0.0.1:3010",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(questionnaire_router, prefix="/api/questionnaire", tags=["questionnaire"])
app.include_router(ia_router, prefix="/api/ia", tags=["ia"])
app.include_router(ia_v1_router, prefix="/api/v1/ia", tags=["ia-v1"])
app.include_router(audio_router, prefix="/api/audio", tags=["audio"])
app.include_router(audio_v1_router, prefix="/api/v1/audio", tags=["audio-v1"])
app.include_router(jobs_router, prefix="/api/v1", tags=["jobs-v1"])
app.include_router(audit_router, prefix="/api/v1/audit", tags=["audit-v1"])
app.include_router(review_router, prefix="/api/v1", tags=["review-v1"])
app.include_router(sessions_router, prefix="/api/v1", tags=["sessions-v1"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
