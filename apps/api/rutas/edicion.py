"""Endpoint de edición del docente.

Capa fina a propósito: permisos, estado, `operaciones.aplicar()`, guardar. La
lógica difícil está en `libs/py/edicion/operaciones.py`, que se prueba sin
base de datos.

Escrito contra los modelos reales de `modelos_contenido.py` y reutilizando
`puede_ver_guia` de `alcance.py`.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from libs.py.auth.alcance import puede_ver_guia
from libs.py.auth.dependencias import usuario_actual
from libs.py.db.modelos_auth import Usuario
from libs.py.db.modelos_contenido import EdicionBloque, VersionGuia
from libs.py.db.session import get_db
from libs.py.edicion.esquemas import PeticionEdicion, RespuestaEdicion
from libs.py.edicion.operaciones import ErrorDeEdicion, aplicar
from libs.py.esquema.validador import validar

router = APIRouter(prefix="/api/versiones", tags=["edicion"])


def _sha256(documento: dict) -> str:
    """Huella del contenido.

    `sort_keys=True` no es adorno: sin él, dos documentos idénticos con las
    claves en distinto orden darían huellas distintas y el control de
    concurrencia rechazaría ediciones legítimas.
    """
    crudo = json.dumps(documento, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


@router.post(
    "/{version_id}/editar",
    response_model=RespuestaEdicion,
    summary="Aplica un lote de operaciones de edición sobre una versión",
)
def editar_version(
    version_id: int,
    peticion: PeticionEdicion,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> RespuestaEdicion:
    version = db.get(VersionGuia, version_id)

    # 404 y no 403: si no puedes verla, no confirmamos que existe. Mismo
    # criterio que ya se aplica en /guias.
    if version is None or not puede_ver_guia(usuario, version.guia):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Versión no encontrada")

    # Congelada = está en revisión. 409: el recurso es tuyo, pero su estado no
    # admite esta operación.
    if version.congelada:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La versión está congelada porque se envió a revisión. "
            "Para seguir editando hay que crear una versión nueva.",
        )

    # Concurrencia optimista sobre el sha256 que la tabla ya guarda: no hace
    # falta columna nueva ni migración. Si el docente tiene el editor abierto
    # en dos pestañas, el segundo en guardar se entera en vez de pisar en
    # silencio el trabajo del primero.
    if peticion.sha256 is not None and peticion.sha256 != version.sha256:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La versión cambió mientras editabas. Recarga antes de guardar.",
        )

    try:
        curso_nuevo, registros = aplicar(version.contenido, peticion.operaciones)
    except ErrorDeEdicion as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    resultado = validar(curso_nuevo)
    curso_nuevo["validaciones"] = resultado.como_dict()

    # Reasignar (no mutar) es lo que hace que SQLAlchemy detecte el cambio en
    # la columna JSONB. Si algún día se edita el dict en su sitio, no se guarda
    # nada y NO salta ningún error: haría falta flag_modified(version, "contenido").
    version.contenido = curso_nuevo
    version.sha256 = _sha256(curso_nuevo)
    version.semaforo = resultado.semaforo
    version.alertas = resultado.como_dict()["alertas"]

    for registro in registros:
        db.add(
            EdicionBloque(
                version_id=version.id,
                operacion=registro["operacion"],
                bloque_id=registro.get("bloque_id"),
                pagina_id=registro.get("pagina_id"),
                antes=registro.get("antes"),
                despues=registro.get("despues"),
                realizada_por=usuario.id,
            )
        )

    db.commit()

    return RespuestaEdicion(
        sha256=version.sha256,
        semaforo=resultado.semaforo,
        alertas=resultado.como_dict()["alertas"],
        estadisticas=curso_nuevo.get("estadisticas", {}),
        ediciones=registros,
        curso=curso_nuevo,
    )
