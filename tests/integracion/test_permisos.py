"""Quién ve qué y quién puede hacer qué.

Cada prueba de aquí es una puerta que no debe abrirse. Un fallo de permisos
no se manifiesta como un error: se manifiesta como un docente viendo la guía
de otro, y nadie se entera.

El filtro va DENTRO de la consulta SQL. Traer todo y filtrar en Python
funciona con 50 guías y se cae con 5.000; y si algún día se olvida el filtro,
se exponen datos ajenos.
"""
import pytest

from libs.py.auth.alcance import guias_visibles
from libs.py.auth.seguridad import verificar_contrasena

pytestmark = pytest.mark.bd


# ---------------------------------------------------------------------------
# Usuarios y roles
# ---------------------------------------------------------------------------

def test_la_contrasena_no_se_guarda_en_claro(crear_usuario):
    usuario = crear_usuario("a@utpl.edu.ec")
    assert "clave-de-prueba" not in usuario.hash_contrasena
    assert verificar_contrasena("clave-de-prueba", usuario.hash_contrasena)


def test_una_contrasena_incorrecta_no_verifica(crear_usuario):
    usuario = crear_usuario("a@utpl.edu.ec")
    assert not verificar_contrasena("otra", usuario.hash_contrasena)


def test_un_usuario_puede_tener_varios_roles(crear_usuario):
    """Un docente que además publica es un usuario con los dos roles:
    usuarios_roles es una tabla, no una columna."""
    usuario = crear_usuario("a@utpl.edu.ec", roles=("docente", "operador"))
    assert usuario.codigos_de_rol() == {"docente", "operador"}


def test_tiene_rol_acepta_varios_codigos(crear_usuario):
    usuario = crear_usuario("a@utpl.edu.ec", roles=("qa",))
    assert usuario.tiene_rol("qa", "coordinador")
    assert not usuario.tiene_rol("operador", "docente")


def test_un_usuario_sin_roles_no_tiene_ninguno(crear_usuario):
    assert crear_usuario("a@utpl.edu.ec", roles=()).codigos_de_rol() == set()


# ---------------------------------------------------------------------------
# Alcance: qué guías ve cada uno
# ---------------------------------------------------------------------------

def test_el_docente_solo_ve_las_suyas(sesion, crear_usuario, crear_guia):
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    luis = crear_usuario("luis@utpl.edu.ec", roles=("docente",))
    mia = crear_guia(ana, codigo="MIA101")
    crear_guia(luis, codigo="SUYA101")

    vistas = list(sesion.scalars(guias_visibles(ana)).all())
    assert [g.id for g in vistas] == [mia.id]


def test_el_coordinador_ve_todas(sesion, crear_usuario, crear_guia):
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    coord = crear_usuario("coord@utpl.edu.ec", roles=("coordinador",))
    crear_guia(ana, codigo="UNA")
    crear_guia(ana, codigo="OTRA")

    ids = {g.id for g in sesion.scalars(guias_visibles(coord)).all()}
    mias = {g.id for g in sesion.scalars(guias_visibles(ana)).all()}
    assert mias <= ids


def test_el_admin_ve_todas(sesion, crear_usuario, crear_guia):
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    admin = crear_usuario("admin@utpl.edu.ec", roles=("admin",))
    guia = crear_guia(ana)
    ids = {g.id for g in sesion.scalars(guias_visibles(admin)).all()}
    assert guia.id in ids


def test_sin_rol_reconocido_no_ve_nada(sesion, crear_usuario, crear_guia):
    """Un usuario sin rol no debe caer en 'ver todo' por descuido."""
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    crear_guia(ana)
    nadie = crear_usuario("nadie@utpl.edu.ec", roles=())
    assert list(sesion.scalars(guias_visibles(nadie)).all()) == []


def test_el_revisor_solo_ve_las_asignadas(sesion, crear_usuario, crear_guia):
    from libs.py.db.modelos_dominio import AsignacionRevision

    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    qa = crear_usuario("qa@utpl.edu.ec", roles=("qa",))
    asignada = crear_guia(ana, codigo="ASIG")
    crear_guia(ana, codigo="NOASIG")
    sesion.add(AsignacionRevision(guia_id=asignada.id, revisor_id=qa.id,
                                  etapa="qa", asignada_por=ana.id))
    sesion.flush()

    vistas = list(sesion.scalars(guias_visibles(qa)).all())
    assert [g.id for g in vistas] == [asignada.id]


def test_el_operador_tampoco_ve_las_no_asignadas(sesion, crear_usuario, crear_guia):
    """Publicar no da acceso a todo: el operativo ve lo que le asignan."""
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    op = crear_usuario("op@utpl.edu.ec", roles=("operador",))
    crear_guia(ana, codigo="AJENA")
    assert list(sesion.scalars(guias_visibles(op)).all()) == []


def test_el_docente_con_rol_de_operador_ve_las_suyas_y_las_asignadas(
        sesion, crear_usuario, crear_guia):
    from libs.py.db.modelos_dominio import AsignacionRevision

    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente", "operador"))
    luis = crear_usuario("luis@utpl.edu.ec", roles=("docente",))
    mia = crear_guia(ana, codigo="MIA")
    asignada = crear_guia(luis, codigo="ASIG")
    ajena = crear_guia(luis, codigo="AJENA")
    sesion.add(AsignacionRevision(guia_id=asignada.id, revisor_id=ana.id,
                                  etapa="operacion", asignada_por=luis.id))
    sesion.flush()

    ids = {g.id for g in sesion.scalars(guias_visibles(ana)).all()}
    assert ids == {mia.id, asignada.id}
    assert ajena.id not in ids
