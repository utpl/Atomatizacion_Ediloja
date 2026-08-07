"""Reglas de alcance: qué guías puede ver cada usuario.

El filtro se aplica DENTRO de la consulta SQL, no después en Python.
Traer todo y filtrar en memoria funciona con 50 guías y se cae con 5.000;
y si algún día olvidas el filtro, expones datos ajenos.
"""

from sqlalchemy import Select, or_, select

from libs.py.db.modelos_auth import Usuario
from libs.py.db.modelos_dominio import AsignacionRevision, Guia


def guias_visibles(usuario: Usuario) -> Select:
    """Devuelve la consulta de guías que este usuario puede ver."""
    roles = usuario.codigos_de_rol()
    consulta = select(Guia)

    # Admin y coordinación ven todo
    if roles & {"admin", "coordinador"}:
        return consulta

    condiciones = []

    # El docente ve solo las suyas
    if "docente" in roles:
        condiciones.append(Guia.autor_id == usuario.id)

    # Los revisores ven las que tienen asignadas
    if roles & {"revisor_di", "qa", "operador"}:
        condiciones.append(
            Guia.id.in_(
                select(AsignacionRevision.guia_id).where(
                    AsignacionRevision.revisor_id == usuario.id
                )
            )
        )

    if not condiciones:
        # Sin rol reconocido: no ve nada
        return consulta.where(Guia.id == -1)

    return consulta.where(or_(*condiciones))


def puede_ver_guia(usuario: Usuario, guia: Guia) -> bool:
    roles = usuario.codigos_de_rol()
    if roles & {"admin", "coordinador"}:
        return True
    if guia.autor_id == usuario.id:
        return True
    return any(a.revisor_id == usuario.id for a in guia.asignaciones)
