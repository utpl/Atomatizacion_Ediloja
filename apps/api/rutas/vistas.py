"""Vistas HTML: el editor del docente, la galería y el tablero del revisor.

A diferencia del resto de routers, este NO devuelve JSON: devuelve HTML
renderizado con Jinja2. Convención de la especificación (§2):
    /api/*  → JSON
    /ui/*   → fragmentos HTML para htmx
Las páginas completas cuelgan de la raíz; los fragmentos, de /ui.
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.rutas._datos_demo import cargar_curso, indexar
from libs.py.auth.alcance import guias_visibles
from libs.py.auth.dependencias import NOMBRE_COOKIE, usuario_web_opcional
from libs.py.auth.seguridad import crear_token, verificar_contrasena
from libs.py.canon import oferta
from libs.py.db.modelos_auth import Usuario
from libs.py.db.modelos_dominio import Guia
from libs.py.db.session import obtener_sesion

# apps/api/rutas/vistas.py → parents[3] es la raíz del repo.
# Se ancla al archivo y no al directorio de trabajo: si no, funciona o
# no según desde dónde arranques uvicorn.
RAIZ = Path(__file__).resolve().parents[3]
DIR_PLANTILLAS = RAIZ / "packages" / "plantillas"

plantillas = Jinja2Templates(directory=DIR_PLANTILLAS)

router = APIRouter(tags=["vistas"])


@router.get("/prueba")
def prueba(request: Request):
    return plantillas.TemplateResponse("prueba.html", {
        "request": request,
        "nombre": "EdiLoja",
        "numeros": [1, 2, 3, 4],
    })


@router.get("/curso")
@router.get("/curso/{pagina_id}")
def curso(request: Request, pagina_id: str | None = None):
    datos = cargar_curso()

    # ⚠️ Las páginas están en estructura.paginas, NO en la raíz del documento.
    paginas = datos["estructura"]["paginas"]
    actual = next((p for p in paginas if p["id"] == pagina_id), paginas[0])

    return plantillas.TemplateResponse("curso.html", {
        "request": request,
        "curso": datos,
        "paginas": paginas,
        "pagina": actual,
        "ctx": indexar(datos),
    })


@router.get("/entrar")
def formulario_login(request: Request):
    return plantillas.TemplateResponse("entrar.html", {"request": request, "error": None})


@router.post("/entrar")
def procesar_login(
    request: Request,
    correo: str = Form(...),
    contrasena: str = Form(...),
    sesion: Session = Depends(obtener_sesion),
):
    usuario = sesion.scalar(select(Usuario).where(Usuario.correo == correo.lower()))

    # Mismo mensaje para correo inexistente y contraseña mala: distinguirlos
    # regalaría la lista de correos válidos de la institución.
    if usuario is None or not verificar_contrasena(contrasena, usuario.hash_contrasena):
        return plantillas.TemplateResponse(
            "entrar.html",
            {"request": request, "error": "Correo o contraseña incorrectos"},
            status_code=401,
        )
    if not usuario.activo:
        return plantillas.TemplateResponse(
            "entrar.html",
            {"request": request, "error": "Esta cuenta está desactivada"},
            status_code=403,
        )

    token = crear_token(usuario.id, sorted(usuario.codigos_de_rol()))

    # 303 y no 302: obliga al navegador a convertir el POST en GET. Sin esto,
    # recargar la página de destino reenvía el formulario.
    respuesta = RedirectResponse(url="/guias-vista", status_code=303)
    respuesta.set_cookie(
        NOMBRE_COOKIE, token,
        httponly=True,      # JavaScript no puede leerla
        samesite="lax",     # otra web no puede disparar peticiones con ella
        secure=False,       # ⚠️ en producción (HTTPS) esto va en True
        max_age=60 * 60 * 8,
    )
    return respuesta


@router.get("/salir")
def salir():
    respuesta = RedirectResponse(url="/entrar", status_code=303)
    respuesta.delete_cookie(NOMBRE_COOKIE)
    return respuesta


@router.get("/guias-vista")
def lista_guias(
    request: Request,
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    # Una vista HTML no devuelve 401: redirige al login. Por eso usamos la
    # dependencia "opcional" y decidimos aquí, en vez de dejar que lance.
    if usuario is None:
        return RedirectResponse(url="/entrar", status_code=303)

    # Misma consulta que usa GET /guias. El filtrado por rol vive en un solo
    # sitio: si mañana cambia, cambia para la API y para la vista a la vez.
    guias = list(sesion.scalars(guias_visibles(usuario)).all())

    return plantillas.TemplateResponse("guias.html", {
        "request": request,
        "usuario": usuario,
        "guias": guias,
        "puede_crear": usuario.tiene_rol("docente", "admin"),
    })


@router.get("/guias-vista/nueva")
def formulario_guia(request: Request, usuario=Depends(usuario_web_opcional)):
    if usuario is None:
        return RedirectResponse(url="/entrar", status_code=303)
    if not usuario.tiene_rol("docente", "admin"):
        return RedirectResponse(url="/guias-vista", status_code=303)
    return plantillas.TemplateResponse("guia_nueva.html", {"request": request, "error": None})


@router.post("/guias-vista/nueva")
def crear_guia(
    request: Request,
    codigo_banner: str = Form(...),
    nombre_asignatura: str = Form(...),
    periodo: str = Form(...),
    total_semanas: int = Form(8),
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    if usuario is None:
        return RedirectResponse(url="/entrar", status_code=303)
    if not usuario.tiene_rol("docente", "admin"):
        return RedirectResponse(url="/guias-vista", status_code=303)

    # 8 o 16, no otro número: es regla del esquema, no una preferencia.
    # Se comprueba aquí porque un <select> se puede manipular desde fuera.
    if total_semanas not in (8, 16):
        return plantillas.TemplateResponse(
            "guia_nueva.html",
            {"request": request, "error": "Las semanas solo pueden ser 8 o 16"},
            status_code=422,
        )

    guia = Guia(
        codigo_banner=codigo_banner.strip().upper(),
        nombre_asignatura=nombre_asignatura.strip(),
        periodo=periodo.strip(),
        total_semanas=total_semanas,
        autor_id=usuario.id,      # ← esto es lo que aísla a cada docente
    )
    sesion.add(guia)
    sesion.commit()
    sesion.refresh(guia)

    return RedirectResponse(url=f"/guias-vista/{guia.id}/generar", status_code=303)


# Fragmentos para la cascada del formulario. Cuelgan de /ui/* por la
# convención: /api/* devuelve JSON, /ui/* devuelve HTML para htmx.
@router.get("/ui/modalidades")
def ui_modalidades(request: Request, level: str = ""):
    return plantillas.TemplateResponse("_opciones.html", {
        "request": request,
        "opciones": oferta.modalidades(level),
        "vacio": "Seleccione una modalidad",
    })


@router.get("/ui/facultades")
def ui_facultades(request: Request, level: str = "", modality: str = ""):
    return plantillas.TemplateResponse("_opciones.html", {
        "request": request,
        "opciones": oferta.facultades(level, modality),
        "vacio": "Seleccione una facultad",
    })


@router.get("/ui/carreras")
def ui_carreras(request: Request, level: str = "", modality: str = "", faculty: str = ""):
    return plantillas.TemplateResponse("_opciones.html", {
        "request": request,
        "opciones": oferta.carreras(level, modality, faculty),
        "vacio": "Seleccione una carrera",
    })


@router.get("/guias-vista/{guia_id}/generar")
def formulario_requerimientos(
    guia_id: int,
    request: Request,
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    if usuario is None:
        return RedirectResponse(url="/entrar", status_code=303)

    guia = sesion.get(Guia, guia_id)

    # 404 y no 403: un 403 confirmaría que la guía existe. Con 404, quien
    # husmee ids ajenos no averigua nada.
    if guia is None or (guia.autor_id != usuario.id and not usuario.tiene_rol("admin")):
        return plantillas.TemplateResponse(
            "no_encontrado.html", {"request": request}, status_code=404
        )

    return plantillas.TemplateResponse("requerimientos.html", {
        "request": request,
        "guia": guia,
        "niveles": oferta.NIVELES,
        "error": None,
    })


@router.post("/guias-vista/{guia_id}/requerimientos")
def guardar_requerimientos(
    guia_id: int,
    request: Request,
    level: str = Form(...),
    modality: str = Form(...),
    faculty: str = Form(...),
    program: str = Form(...),
    subjectCode: str = Form(...),
    academicPeriod: str = Form(...),
    subjectName: str = Form(...),
    weeks: int = Form(...),
    credits: str = Form(...),
    learningOutcome: str = Form(...),
    contents: str = Form(...),
    methodology: str = Form(...),
    bibliography: str = Form(...),
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    if usuario is None:
        return RedirectResponse(url="/entrar", status_code=303)

    guia = sesion.get(Guia, guia_id)
    if guia is None or (guia.autor_id != usuario.id and not usuario.tiene_rol("admin")):
        return plantillas.TemplateResponse(
            "no_encontrado.html", {"request": request}, status_code=404
        )

    if weeks not in (8, 16):
        return plantillas.TemplateResponse(
            "requerimientos.html",
            {"request": request, "guia": guia, "niveles": oferta.NIVELES,
             "error": "La duración solo puede ser de 8 o 16 semanas"},
            status_code=422,
        )

    # Al modelo le llegan las etiquetas legibles, no los identificadores.
    # "facultad-ciencias-economicas-empresariales" en el prompt degradaría el
    # contexto sin que nadie lo notara.
    mods = oferta.modalidades(level)
    facs = oferta.facultades(level, modality)
    progs = oferta.carreras(level, modality, faculty)

    requerimientos = {
        "level": dict(oferta.NIVELES).get(level, level),
        "modality": oferta.etiqueta(mods, modality),
        "faculty": oferta.etiqueta(facs, faculty),
        "program": oferta.etiqueta(progs, program),
        "subjectCode": subjectCode.strip(),
        "academicPeriod": academicPeriod.strip(),
        "subjectName": subjectName.strip(),
        "weeks": weeks,
        "credits": credits.strip(),
        "learningOutcome": learningOutcome.strip(),
        "contents": contents.strip(),
        "methodology": methodology.strip(),
        "bibliography": bibliography.strip(),
    }

    # La guía se sincroniza con lo que el docente acaba de escribir: son los
    # mismos datos con otro nombre, y dos copias divergentes serían peor.
    guia.codigo_banner = requerimientos["subjectCode"]
    guia.nombre_asignatura = requerimientos["subjectName"]
    guia.periodo = requerimientos["academicPeriod"]
    guia.total_semanas = weeks
    sesion.commit()

    return plantillas.TemplateResponse("requerimientos_ok.html", {
        "request": request,
        "guia": guia,
        "requerimientos": requerimientos,
        # ensure_ascii=False: esta pantalla existe para que el docente
        # revise lo que se manda. "Psicolog\u00eda" no se puede revisar.
        "requerimientos_json": json.dumps(requerimientos, ensure_ascii=False, indent=2),
    })
