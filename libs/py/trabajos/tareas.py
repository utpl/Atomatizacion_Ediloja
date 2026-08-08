"""Lo que ejecuta el worker.

Una regla que atraviesa todo el archivo: **el worker abre su propia sesión de
base de datos**. No recibe objetos de SQLAlchemy como argumento, solo enteros.

El motivo es que RQ serializa los argumentos y los manda por Redis: un objeto
ORM no sobrevive a ese viaje, y aunque sobreviviera vendría atado a una sesión
que ya se cerró en el proceso de la API. Pasar ids y volver a cargar es la
forma correcta y además hace la tarea reintentable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from libs.py.agente.cliente import MODELO, llamar_modelo
from libs.py.agente.generador import ErrorDeGeneracion, generar_guia
from libs.py.db.modelos_contenido import VersionGuia
from libs.py.db.modelos_dominio import CuotaPagina, SolicitudGeneracion
from libs.py.db.session import SesionLocal
from libs.py.esquema.validador import validar


def _ahora() -> datetime:
    return datetime.now(UTC)


def _sha256(documento: dict) -> str:
    return hashlib.sha256(
        json.dumps(documento, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def generar_guia_completa(solicitud_id: int, *, llamador=None) -> dict:
    """Genera una guía entera y la guarda como versión nueva.

    `llamador` existe para poder inyectar un modelo simulado en las pruebas.
    En producción no se pasa y usa el cliente real.
    """
    sesion = SesionLocal()
    try:
        solicitud = sesion.get(SolicitudGeneracion, solicitud_id)
        if solicitud is None:
            raise ValueError(f"No existe la solicitud {solicitud_id}")

        solicitud.estado = "ejecutando"
        solicitud.iniciada_en = _ahora()
        solicitud.intentos += 1
        solicitud.modelo_usado = MODELO
        sesion.commit()

        guia = solicitud.guia
        datos = {
            "codigo_banner": guia.codigo_banner,
            "asignatura": guia.nombre_asignatura,
            "periodo": guia.periodo,
            "total_semanas": guia.total_semanas,
            **solicitud.requerimientos,
        }

        try:
            curso, telemetria = generar_guia(
                datos,
                plan=solicitud.requerimientos.get("plan"),
                bibliografia=solicitud.requerimientos.get("bibliografia"),
                llamador=llamador or llamar_modelo,
                validar=validar,
            )
        except ErrorDeGeneracion as exc:
            # Un fallo técnico NO descuenta cuota: el docente no ha gastado una
            # de sus tres oportunidades porque el sistema no supo generar.
            solicitud.estado = "fallida"
            solicitud.mensaje_error = str(exc)
            solicitud.terminada_en = _ahora()
            sesion.commit()
            raise

        # La versión anterior deja de ser la actual. Se hace antes de insertar
        # la nueva para que nunca haya dos marcadas a la vez.
        for anterior in guia.versiones:
            anterior.es_actual = False

        numero = max((v.numero for v in guia.versiones), default=0) + 1
        version = VersionGuia(
            guia_id=guia.id,
            numero=numero,
            origen="agente_ia",
            solicitud_id=solicitud.id,
            contenido=curso,
            version_esquema=curso.get("version_esquema", "1.0.0"),
            sha256=_sha256(curso),
            semaforo=curso.get("validaciones", {}).get("semaforo"),
            alertas=curso.get("validaciones", {}).get("alertas"),
            congelada=False,
            es_actual=True,
            creada_por=solicitud.solicitada_por,
        )
        sesion.add(version)

        solicitud.estado = "completada"
        solicitud.progreso = 100
        solicitud.tokens_entrada = telemetria.get("tokens_entrada")
        solicitud.tokens_salida = telemetria.get("tokens_salida")
        solicitud.terminada_en = _ahora()
        sesion.commit()

        return {
            "version_id": version.id,
            "numero": numero,
            "semaforo": version.semaforo,
            "tokens": telemetria,
        }
    finally:
        sesion.close()


def regenerar_una_pagina(solicitud_id: int, *, llamador=None) -> dict:
    """Regenera una sola semana. Descuenta cuota solo si sale bien.

    Se importa aquí dentro y no arriba porque `regenerar_pagina` trabaja sobre
    un curso ya cargado, y así queda claro que esta función y la de arriba no
    comparten camino.
    """
    from libs.py.agente.generador import regenerar_pagina

    sesion = SesionLocal()
    try:
        solicitud = sesion.get(SolicitudGeneracion, solicitud_id)
        if solicitud is None:
            raise ValueError(f"No existe la solicitud {solicitud_id}")

        solicitud.estado = "ejecutando"
        solicitud.iniciada_en = _ahora()
        solicitud.intentos += 1
        solicitud.modelo_usado = MODELO
        sesion.commit()

        guia = solicitud.guia
        version = next((v for v in guia.versiones if v.es_actual), None)
        if version is None:
            raise ValueError("La guía no tiene versión actual que regenerar")
        if version.congelada:
            raise ValueError("La versión está en revisión y no se puede regenerar")

        semana = int(solicitud.requerimientos["semana"])
        curso = dict(version.contenido)

        try:
            curso, telemetria = regenerar_pagina(
                curso,
                semana,
                datos_curso=curso.get("info_general"),
                bibliografia=solicitud.requerimientos.get("bibliografia"),
                llamador=llamador or llamar_modelo,
                validar=validar,
            )
        except ErrorDeGeneracion as exc:
            solicitud.estado = "fallida"
            solicitud.mensaje_error = str(exc)
            solicitud.terminada_en = _ahora()
            sesion.commit()  # sin tocar la cuota
            raise

        # Solo aquí, con la regeneración ya hecha, se descuenta.
        cuota = sesion.query(CuotaPagina).filter_by(
            guia_id=guia.id, pagina_id=solicitud.pagina_id
        ).first()
        if cuota is None:
            cuota = CuotaPagina(
                guia_id=guia.id, pagina_id=solicitud.pagina_id, usadas=0, maximas=3
            )
            sesion.add(cuota)
        cuota.usadas += 1

        version.contenido = curso
        version.sha256 = _sha256(curso)
        version.semaforo = curso.get("validaciones", {}).get("semaforo")
        version.alertas = curso.get("validaciones", {}).get("alertas")

        solicitud.estado = "completada"
        solicitud.progreso = 100
        solicitud.tokens_entrada = telemetria.get("tokens_entrada")
        solicitud.tokens_salida = telemetria.get("tokens_salida")
        solicitud.terminada_en = _ahora()
        sesion.commit()

        return {
            "version_id": version.id,
            "semana": semana,
            "semaforo": version.semaforo,
            "cuota_restante": cuota.disponibles,
        }
    finally:
        sesion.close()
