"""Crea los roles del sistema y un usuario administrador inicial.

Uso:
    python tools/sembrar_datos.py <correo> <nombre> <contrasena>
"""

import sys

from sqlalchemy import select

from libs.py.auth.seguridad import cifrar_contrasena
from libs.py.db.modelos_auth import Rol, Usuario, UsuarioRol
from libs.py.db.session import SesionLocal

ROLES = [
    ("docente", "Docente", "Crea y gestiona sus propias guías"),
    ("revisor_di", "Revisor de Diseño Instruccional", "Revisa guías asignadas"),
    ("qa", "Control de calidad", "Aprueba o devuelve guías en etapa de QA"),
    ("operador", "Operador de pipeline", "Ejecuta el pipeline y publica en Canvas"),
    ("coordinador", "Coordinador", "Ve todo su ámbito y asigna revisores"),
    ("admin", "Administrador", "Acceso total, incluida gestión de usuarios"),
]


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        raise SystemExit(1)

    correo, nombre, contrasena = sys.argv[1].lower(), sys.argv[2], sys.argv[3]

    with SesionLocal() as sesion:
        for codigo, nombre_rol, descripcion in ROLES:
            if sesion.scalar(select(Rol).where(Rol.codigo == codigo)) is None:
                sesion.add(Rol(codigo=codigo, nombre=nombre_rol, descripcion=descripcion))
                print(f"  + rol {codigo}")
        sesion.commit()

        if sesion.scalar(select(Usuario).where(Usuario.correo == correo)):
            print(f"El usuario {correo} ya existe.")
            return

        usuario = Usuario(
            correo=correo,
            nombre_completo=nombre,
            hash_contrasena=cifrar_contrasena(contrasena),
        )
        sesion.add(usuario)
        sesion.flush()

        # El administrador recibe también el rol docente, para poder probar
        # el flujo completo sin crear un segundo usuario.
        for codigo in ("admin", "docente"):
            rol = sesion.scalar(select(Rol).where(Rol.codigo == codigo))
            sesion.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol.id))

        sesion.commit()
        print(f"  + usuario {correo} con roles admin y docente")


if __name__ == "__main__":
    main()
