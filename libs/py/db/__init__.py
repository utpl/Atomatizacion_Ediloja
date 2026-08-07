"""Paquete de base de datos.

Importa TODOS los módulos de modelos para que el registro de SQLAlchemy esté
completo. Sin esto, una relación declarada por nombre (por ejemplo
`Guia.versiones -> "VersionGuia"`) no resuelve si nadie importó el módulo
donde vive esa clase.
"""

from libs.py.db.session import Base, SesionLocal, engine, obtener_sesion

from libs.py.db import modelos_auth  # noqa: F401, E402
from libs.py.db import modelos_dominio  # noqa: F401, E402
from libs.py.db import modelos_contenido  # noqa: F401, E402

__all__ = ["Base", "SesionLocal", "engine", "obtener_sesion"]
