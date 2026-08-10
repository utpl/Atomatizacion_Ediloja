"""Base de datos de prueba, en transacción que se deshace al terminar.

Cada prueba trabaja sobre datos limpios y no ensucia la base de desarrollo.
Alternativa descartada: una base aparte por prueba; es más lento y no aporta.
"""
import uuid

import pytest
from sqlalchemy.orm import Session

from libs.py.auth.seguridad import cifrar_contrasena
from libs.py.db.modelos_auth import Rol, Usuario, UsuarioRol
from libs.py.db.modelos_dominio import Guia
from libs.py.db.session import engine

CLAVE = "clave-de-prueba"


@pytest.fixture
def sesion():
    """Sesión en transacción anidada, que se deshace al terminar.

    join_transaction_mode="create_savepoint" hace que un commit de la prueba
    (o del código probado) solo cierre un savepoint, no la transacción
    envolvente. Sin esto, el primer commit desliga la sesión y las pruebas
    siguientes fallan con 'transaction already deassociated'.
    """
    conexion = engine.connect()
    transaccion = conexion.begin()
    s = Session(bind=conexion, join_transaction_mode="create_savepoint")
    try:
        yield s
    finally:
        s.close()
        transaccion.rollback()
        conexion.close()


@pytest.fixture
def crear_usuario(sesion):
    """Crea un usuario con sus roles.

    Los roles pasan por UsuarioRol, que es tabla intermedia: una persona puede
    tener varios y cada uno puede limitarse a una facultad o carrera.
    """
    def _crear(correo, roles=("docente",), activo=True):
        # Sufijo único: la base de desarrollo ya tiene admin@utpl.edu.ec y
        # otros de la semilla, y el correo es único. Sin esto, la prueba
        # choca con datos que no son suyos.
        correo = f"{uuid.uuid4().hex[:8]}.{correo}"
        usuario = Usuario(correo=correo, nombre_completo=f"Prueba {correo}",
                          hash_contrasena=cifrar_contrasena(CLAVE), activo=activo)
        sesion.add(usuario)
        sesion.flush()
        for codigo in roles:
            rol = sesion.query(Rol).filter_by(codigo=codigo).first()
            if rol is None:
                rol = Rol(codigo=codigo, nombre=codigo.capitalize())
                sesion.add(rol)
                sesion.flush()
            sesion.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol.id,
                                  ambito_tipo="global"))
        sesion.flush()
        sesion.refresh(usuario)
        return usuario

    return _crear


@pytest.fixture
def crear_guia(sesion):
    def _crear(autor, codigo="TEST101", estado="borrador", semanas=8):
        guia = Guia(codigo_banner=codigo, nombre_asignatura="Prueba",
                    periodo="2026-1", total_semanas=semanas,
                    autor_id=autor.id, estado=estado)
        sesion.add(guia)
        sesion.flush()
        return guia

    return _crear
