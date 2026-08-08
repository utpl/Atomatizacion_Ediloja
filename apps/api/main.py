"""API de la plataforma EdiLoja."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.rutas import auth, edicion, generacion, guias, versiones

app = FastAPI(
    title="API EdiLoja",
    description="Plataforma de producción de guías didácticas y metacursos.",
    version="0.1.0",
)

# En producción se listan solo los dominios reales, nunca "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(guias.router)

# Versiones y edición: lo que necesita el editor del docente.
app.include_router(edicion.router)
app.include_router(versiones.router)
app.include_router(versiones.router_guias)

# Generación con IA: encolar y sondear.
app.include_router(generacion.router)
app.include_router(generacion.router_trabajos)


@app.get("/salud", tags=["sistema"])
def salud() -> dict:
    return {"estado": "ok"}
