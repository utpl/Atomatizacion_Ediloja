"""Vistas HTML: el editor del docente, la galería y el tablero del revisor.

A diferencia del resto de routers, este NO devuelve JSON: devuelve HTML
renderizado con Jinja2. Convención de la especificación (§2):
    /api/*  → JSON
    /ui/*   → fragmentos HTML para htmx
Las páginas completas cuelgan de la raíz; los fragmentos, de /ui.
"""

import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.rutas._datos_demo import cargar_curso, indexar
from libs.py.agente.cliente import llamar_modelo
from libs.py.agente.unidades import ErrorDeUnidades, extraer_unidades, plan_desde_unidades
from libs.py.auth.alcance import guias_visibles
from libs.py.auth.dependencias import NOMBRE_COOKIE, usuario_web_opcional
from libs.py.auth.seguridad import crear_token, verificar_contrasena
from libs.py.canon import oferta, temas
from libs.py.db.modelos_auth import Usuario
from libs.py.db.modelos_contenido import EdicionBloque
from libs.py.db.modelos_dominio import Guia, SolicitudGeneracion
from libs.py.db.session import obtener_sesion
from libs.py.edicion.esquemas import ActualizarBloque
from libs.py.edicion.operaciones import ErrorDeEdicion, aplicar
from libs.py.esquema.validador import validar
from libs.py.trabajos import tareas
from libs.py.trabajos.cola import cola

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
    respuesta = RedirectResponse(url="/panel", status_code=303)
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
        "puede_publicar": usuario.tiene_rol("operador", "coordinador", "admin"),
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

    # Los requerimientos se guardan ya, sin encolar. Así el docente puede
    # revisarlos, cerrar la pestaña y volver, y la pantalla de generación
    # sabe de dónde leerlos. El trabajo se crea al pulsar "Generar".
    sesion.add(SolicitudGeneracion(
        guia_id=guia.id,
        solicitada_por=usuario.id,
        requerimientos=requerimientos,
        alcance="guia_completa",
        estado="borrador",
    ))
    sesion.commit()

    return plantillas.TemplateResponse("requerimientos_ok.html", {
        "request": request,
        "guia": guia,
        "requerimientos": requerimientos,
        # ensure_ascii=False: esta pantalla existe para que el docente
        # revise lo que se manda. "Psicolog\u00eda" no se puede revisar.
        "requerimientos_json": json.dumps(requerimientos, ensure_ascii=False, indent=2),
    })


@router.post("/guias-vista/{guia_id}/generar")
def lanzar_generacion(
    guia_id: int,
    request: Request,
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    """Extrae las unidades, encola el trabajo y lleva a la pantalla de progreso."""
    if usuario is None:
        return RedirectResponse(url="/entrar", status_code=303)

    guia = sesion.get(Guia, guia_id)
    if guia is None or (guia.autor_id != usuario.id and not usuario.tiene_rol("admin")):
        return plantillas.TemplateResponse(
            "no_encontrado.html", {"request": request}, status_code=404
        )

    ultima = (
        sesion.query(SolicitudGeneracion)
        .filter_by(guia_id=guia.id)
        .order_by(SolicitudGeneracion.id.desc())
        .first()
    )
    if ultima is None or not ultima.requerimientos:
        return RedirectResponse(url=f"/guias-vista/{guia.id}/generar", status_code=303)

    # Una sola generación viva por guía: dos clics seguidos pagarían el doble
    # de tokens. Misma regla que aplica POST /api/guias/{id}/generar.
    en_curso = (
        sesion.query(SolicitudGeneracion)
        .filter(
            SolicitudGeneracion.guia_id == guia.id,
            SolicitudGeneracion.estado.in_(("pendiente", "ejecutando")),
        )
        .first()
    )
    if en_curso is not None:
        return RedirectResponse(url=f"/guias-vista/{guia.id}/progreso/{en_curso.id}",
                                status_code=303)

    reqs = dict(ultima.requerimientos)

    # Las unidades salen del texto libre ANTES de encolar, no dentro del
    # worker: si el docente escribió los contenidos de forma que no se pueden
    # repartir, tiene que enterarse ahora y no tras ocho llamadas al modelo.
    try:
        unidades = extraer_unidades(
            reqs.get("contents", ""), guia.total_semanas, llamar_modelo,
            resultado=reqs.get("learningOutcome", ""),
        )
    except ErrorDeUnidades as exc:
        return plantillas.TemplateResponse(
            "requerimientos.html",
            {"request": request, "guia": guia, "niveles": oferta.NIVELES,
             "error": f"No se pudo repartir el temario por semanas: {exc}"},
            status_code=422,
        )

    # El learningOutcome del formulario es UNO para toda la asignatura, y el
    # esquema lo quiere en estructura.resultados_aprendizaje[] enlazado desde
    # cada unidad. Sin esto el dato que escribe el docente se pierde y la guia
    # se publica sin resultado de aprendizaje, que es lo primero que mira DI.
    ra_texto = (reqs.get("learningOutcome") or "").strip()
    if ra_texto:
        reqs["resultados_aprendizaje"] = [
            {"id": "ra1", "numero": 1, "texto": ra_texto}
        ]
        for u in unidades:
            u["resultado_aprendizaje_id"] = "ra1"

    reqs["unidades"] = unidades
    reqs["plan"] = plan_desde_unidades(unidades)
    reqs["bibliografia"] = [
        linea.strip() for linea in reqs.get("bibliography", "").splitlines() if linea.strip()
    ]

    solicitud = SolicitudGeneracion(
        guia_id=guia.id,
        solicitada_por=usuario.id,
        requerimientos=reqs,
        alcance="guia_completa",
        estado="pendiente",
    )
    sesion.add(solicitud)
    sesion.commit()
    sesion.refresh(solicitud)

    cola().enqueue(tareas.generar_guia_completa, solicitud.id)

    return RedirectResponse(url=f"/guias-vista/{guia.id}/progreso/{solicitud.id}",
                            status_code=303)


@router.get("/guias-vista/{guia_id}/progreso/{trabajo_id}")
def progreso(
    guia_id: int,
    trabajo_id: int,
    request: Request,
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    if usuario is None:
        return RedirectResponse(url="/entrar", status_code=303)

    solicitud = sesion.get(SolicitudGeneracion, trabajo_id)
    if solicitud is None or solicitud.guia_id != guia_id:
        return plantillas.TemplateResponse(
            "no_encontrado.html", {"request": request}, status_code=404
        )

    guia = solicitud.guia
    if guia.autor_id != usuario.id and not usuario.tiene_rol("admin"):
        return plantillas.TemplateResponse(
            "no_encontrado.html", {"request": request}, status_code=404
        )

    return plantillas.TemplateResponse("progreso.html", {
        "request": request, "guia": guia, "trabajo": solicitud,
    })


@router.get("/ui/trabajo/{trabajo_id}")
def ui_trabajo(
    trabajo_id: int,
    request: Request,
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    """Fragmento que htmx recarga cada dos segundos."""
    solicitud = sesion.get(SolicitudGeneracion, trabajo_id)
    if usuario is None or solicitud is None:
        return plantillas.TemplateResponse(
            "_trabajo.html", {"request": request, "trabajo": None}, status_code=404
        )

    guia = solicitud.guia
    if guia.autor_id != usuario.id and not usuario.tiene_rol("admin"):
        return plantillas.TemplateResponse(
            "_trabajo.html", {"request": request, "trabajo": None}, status_code=404
        )

    # La sesión puede tener la fila cacheada de la petición anterior; sin esto
    # el progreso se quedaría congelado aunque el worker fuera avanzando.
    sesion.refresh(solicitud)

    return plantillas.TemplateResponse("_trabajo.html", {
        "request": request, "trabajo": solicitud, "guia": guia,
    })


def _version_de(guia_id: int, usuario, sesion: Session):
    """Versión actual de una guía, si el usuario puede verla.

    Devuelve (guia, version) o (None, None). Las vistas deciden qué hacer;
    aquí no se lanza 404 porque una vista puede querer redirigir.
    """
    guia = sesion.get(Guia, guia_id)
    if guia is None or (guia.autor_id != usuario.id and not usuario.tiene_rol("admin")):
        return None, None
    version = next((v for v in guia.versiones if v.es_actual), None)
    return guia, version


@router.get("/guias-vista/{guia_id}/editor")
@router.get("/guias-vista/{guia_id}/editor/{pagina_id}")
def editor(
    guia_id: int,
    request: Request,
    pagina_id: str | None = None,
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    if usuario is None:
        return RedirectResponse(url="/entrar", status_code=303)

    guia, version = _version_de(guia_id, usuario, sesion)
    if guia is None:
        return plantillas.TemplateResponse("no_encontrado.html", {"request": request}, status_code=404)
    if version is None:
        return RedirectResponse(url=f"/guias-vista/{guia_id}/generar", status_code=303)

    curso = version.contenido
    paginas = curso["estructura"]["paginas"]
    actual = next((p for p in paginas if p["id"] == pagina_id), paginas[0])

    return plantillas.TemplateResponse("editor.html", {
        "request": request,
        "guia": guia,
        "version": version,
        "curso": curso,
        "paginas": paginas,
        "pagina": actual,
        "ctx": {
            "recursos": {r["ref"]: r for r in curso.get("recursos", [])},
            "refs": {r["id"]: r for r in curso.get("finales", {}).get("referencias", [])},
            # En el editor los iconos salen del disco; al publicar, el macro
            # deja @@PLANTILLA@@ y canvas_assets lo sustituye por la URL del
            # archivo ya subido al curso. Un solo macro, dos destinos.
            "base_plantilla": "/estatico/recursos",
        },
        # Más adelante saldrá de la guía: cada una podrá llevar su tema.
        "hojas_tema": temas.hojas_de(),
        # Congelada = en revisión: todo en modo lectura.
        "editable": not version.congelada,
    })


def _buscar(pagina: dict, bloque_id: str):
    """Busca un bloque en la página, incluidos los hijos de los contenedores."""
    for b in pagina.get("bloques", []):
        if b.get("id") == bloque_id:
            return b
        for h in b.get("bloques", []) or []:
            if h.get("id") == bloque_id:
                return h
    return None


@router.get("/ui/bloque/{guia_id}/{pagina_id}/{bloque_id}/editar")
def ui_editar_bloque(
    guia_id: int, pagina_id: str, bloque_id: str,
    request: Request,
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    """Cambia el bloque por su formulario. Devuelve un fragmento, no una página."""
    if usuario is None:
        return HTMLResponse("", status_code=401)

    guia, version = _version_de(guia_id, usuario, sesion)
    if version is None or version.congelada:
        return HTMLResponse("", status_code=404)

    pagina = next((p for p in version.contenido["estructura"]["paginas"]
                   if p["id"] == pagina_id), None)
    bloque = _buscar(pagina, bloque_id) if pagina else None
    if bloque is None:
        return HTMLResponse("", status_code=404)

    return plantillas.TemplateResponse("_editar_bloque.html", {
        "request": request, "guia": guia, "pagina": pagina, "b": bloque,
    })


@router.post("/ui/bloque/{guia_id}/{pagina_id}/{bloque_id}")
def ui_guardar_bloque(
    guia_id: int, pagina_id: str, bloque_id: str,
    request: Request,
    texto: str = Form(...),
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    if usuario is None:
        return HTMLResponse("", status_code=401)

    guia, version = _version_de(guia_id, usuario, sesion)
    if version is None:
        return HTMLResponse("", status_code=404)
    if version.congelada:
        return HTMLResponse(
            '<p class="ed-aviso">La versión está en revisión y no se puede editar.</p>',
            status_code=409)

    # Se llama a aplicar() directamente, no a POST /api/versiones/{id}/editar:
    # el servidor llamándose a sí mismo por HTTP añade latencia y una capa más
    # de autenticación que depurar. La lógica vive en un solo sitio igualmente.
    op = ActualizarBloque(bloque_id=bloque_id, campos={"texto": texto})
    try:
        curso_nuevo, registros = aplicar(version.contenido, [op])
    except ErrorDeEdicion as exc:
        return HTMLResponse(f'<p class="ed-aviso">{exc}</p>', status_code=422)

    resultado = validar(curso_nuevo)
    curso_nuevo["validaciones"] = resultado.como_dict()

    # Reasignar, no mutar: SQLAlchemy solo detecta el cambio en la columna
    # JSONB si el objeto es distinto. Mutando en su sitio no se guarda nada
    # y NO salta ningún error.
    version.contenido = curso_nuevo
    version.sha256 = _sha256_curso(curso_nuevo)
    version.semaforo = resultado.semaforo
    version.alertas = resultado.como_dict()["alertas"]

    for r in registros:
        sesion.add(EdicionBloque(
            version_id=version.id, operacion=r["operacion"],
            bloque_id=r.get("bloque_id"), pagina_id=r.get("pagina_id"),
            antes=r.get("antes"), despues=r.get("despues"),
            realizada_por=usuario.id,
        ))
    sesion.commit()

    pagina = next(p for p in curso_nuevo["estructura"]["paginas"] if p["id"] == pagina_id)
    return plantillas.TemplateResponse("_bloque.html", {
        "request": request, "guia": guia, "pagina": pagina,
        "b": _buscar(pagina, bloque_id), "ctx": {}, "editable": True,
    })


def _sha256_curso(documento: dict) -> str:
    return hashlib.sha256(
        json.dumps(documento, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


@router.get("/ui/bloque/{guia_id}/{pagina_id}/{bloque_id}/ver")
def ui_ver_bloque(
    guia_id: int, pagina_id: str, bloque_id: str,
    request: Request,
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    if usuario is None:
        return HTMLResponse("", status_code=401)
    guia, version = _version_de(guia_id, usuario, sesion)
    if version is None:
        return HTMLResponse("", status_code=404)
    pagina = next((p for p in version.contenido["estructura"]["paginas"]
                   if p["id"] == pagina_id), None)
    return plantillas.TemplateResponse("_bloque.html", {
        "request": request, "guia": guia, "pagina": pagina,
        "b": _buscar(pagina, bloque_id), "ctx": {},
        "editable": not version.congelada,
    })


@router.get("/guias-vista/{guia_id}/publicar")
def formulario_publicar(
    guia_id: int, request: Request,
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    if usuario is None:
        return RedirectResponse(url="/entrar", status_code=303)
    if not usuario.tiene_rol("operador", "coordinador", "admin"):
        return plantillas.TemplateResponse("no_encontrado.html", {"request": request}, 404)

    guia = sesion.get(Guia, guia_id)
    if guia is None:
        return plantillas.TemplateResponse("no_encontrado.html", {"request": request}, 404)

    version = next((v for v in guia.versiones if v.es_actual), None)
    return plantillas.TemplateResponse("publicar.html", {
        "request": request, "guia": guia, "version": version,
        # Publicar un borrador se salta la revisión, que es justo lo que el
        # ciclo de vida existe para impedir.
        "puede": guia.estado in ("aprobada", "publicada"),
        "error": None,
    })


@router.post("/guias-vista/{guia_id}/publicar")
def lanzar_publicacion(
    guia_id: int, request: Request,
    canvas_curso_id: int = Form(...),
    canvas_url: str = Form("https://utpl.test.instructure.com"),
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    if usuario is None:
        return RedirectResponse(url="/entrar", status_code=303)
    if not usuario.tiene_rol("operador", "coordinador", "admin"):
        return plantillas.TemplateResponse("no_encontrado.html", {"request": request}, 404)

    guia = sesion.get(Guia, guia_id)
    if guia is None:
        return plantillas.TemplateResponse("no_encontrado.html", {"request": request}, 404)

    version = next((v for v in guia.versiones if v.es_actual), None)
    contexto = {"request": request, "guia": guia, "version": version, "puede": True}

    if guia.estado not in ("aprobada", "publicada"):
        contexto["error"] = (
            f"La guía está en estado «{guia.estado}». Solo se publica lo aprobado.")
        return plantillas.TemplateResponse("publicar.html", contexto, status_code=409)

    en_curso = (
        sesion.query(SolicitudGeneracion)
        .filter(SolicitudGeneracion.guia_id == guia.id,
                SolicitudGeneracion.estado.in_(("pendiente", "ejecutando")))
        .first()
    )
    if en_curso is not None:
        return RedirectResponse(
            url=f"/guias-vista/{guia.id}/progreso/{en_curso.id}", status_code=303)

    solicitud = SolicitudGeneracion(
        guia_id=guia.id, solicitada_por=usuario.id,
        requerimientos={"canvas_curso_id": canvas_curso_id, "canvas_url": canvas_url},
        alcance="publicacion", estado="pendiente",
    )
    sesion.add(solicitud)
    sesion.commit()
    sesion.refresh(solicitud)

    cola().enqueue(tareas.publicar_guia, solicitud.id)
    return RedirectResponse(
        url=f"/guias-vista/{guia.id}/progreso/{solicitud.id}", status_code=303)


# Qué acciones admite cada estado. Se declara aquí y no en la plantilla porque
# es una regla de negocio: si la guía está congelada no se edita, si no está
# aprobada no se publica. Que la plantilla decida eso acaba en dos verdades.
ACCIONES_POR_ESTADO = {
    "borrador":             {"editar", "generar"},
    "en_edicion":           {"editar", "generar"},
    "en_revision":          {"ver"},
    "cambios_solicitados":  {"editar", "generar"},
    "aprobada":             {"ver", "publicar"},
    "publicada":            {"ver", "publicar"},
}


@router.get("/panel")
def panel(
    request: Request,
    usuario=Depends(usuario_web_opcional),
    sesion: Session = Depends(obtener_sesion),
):
    if usuario is None:
        return RedirectResponse(url="/entrar", status_code=303)

    guias = list(sesion.scalars(guias_visibles(usuario)).all())
    roles = usuario.codigos_de_rol()

    filas = []
    for g in guias:
        version = next((v for v in g.versiones if v.es_actual), None)
        permitidas = ACCIONES_POR_ESTADO.get(g.estado, {"ver"})
        filas.append({
            "guia": g,
            "version": version,
            "semaforo": version.semaforo if version else None,
            "tiene_contenido": version is not None,
            "puede_editar": "editar" in permitidas
                            and roles & {"docente", "admin", "coordinador"}
                            and (g.autor_id == usuario.id or roles & {"admin", "coordinador"}),
            "puede_generar": "generar" in permitidas and version is None
                             and roles & {"docente", "admin", "coordinador"},
            "puede_publicar": "publicar" in permitidas
                              and roles & {"operador", "coordinador", "admin"},
        })

    # Un conteo por estado da el pulso del trabajo de un vistazo: cuántas
    # esperan revisión, cuántas listas para publicar.
    conteo = {}
    for g in guias:
        conteo[g.estado] = conteo.get(g.estado, 0) + 1

    return plantillas.TemplateResponse("panel.html", {
        "request": request,
        "usuario": usuario,
        "roles": sorted(roles),
        "filas": filas,
        "conteo": conteo,
        "puede_crear": bool(roles & {"docente", "admin"}),
        "es_revisor": bool(roles & {"revisor_di", "qa", "coordinador", "admin"}),
    })
