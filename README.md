# App-Ediloja

![CI](https://github.com/utpl/Atomatizacion_Ediloja/actions/workflows/ci.yml/badge.svg)

Plataforma de producción de guías didácticas y metacursos de Canvas para **EdiLoja**, la
unidad editorial de la UTPL.

Un agente de IA genera la guía en JSON, el docente la revisa y edita desde un editor web,
un validador comprueba las reglas institucionales, y el resultado se publica en Canvas.

---

## El contrato central

Todo el sistema gira alrededor de un único documento: **`curso.json`**, definido en
`packages/esquemas/curso.schema.json` (v1.0.0). Es la salida del agente, lo que edita el
docente, lo que se valida y la entrada del render.

Doce tipos de bloque: `parrafo`, `encabezado`, `lista`, `tabla`, `caja`, `focalizador`,
`cita`, `imagen`, `diagrama`, `recurso_ediloja`, `autoevaluacion`, `actividades`.

**Dos capas de validación, y la distinción importa:**

- **JSON Schema** → integridad estructural. Si falla, el documento se **rechaza**.
- **Validador Python** → reglas institucionales. Si fallan, se emite una **alerta** con
  severidad y el docente corrige. Semáforo verde / amarillo / rojo.

Un esquema no puede expresar "las citas deben apuntar a una referencia que exista"; una
regla de negocio no debería tumbar un documento por una coma. Por eso son dos cosas.

---

## Arquitectura

```
apps/
  api/              FastAPI: autenticación, guías, versiones, edición
  migrador-canvas/  Flask: migración de cursos existentes desde Canvas
  pipeline-canvas/  Render y publicación
libs/py/
  agente/           Generación de guías con IA
  auth/             JWT, roles, alcance por rol
  db/               Modelos SQLAlchemy y sesión
  edicion/          Operaciones semánticas sobre el curso.json
  esquema/          Validador de reglas de negocio
packages/
  esquemas/         curso.schema.json — el contrato
  canon/            Vocabulario controlado (18 focalizadores)
  plantillas/       CSS y plantillas del tema de Canvas
datos_ejemplo/
  fixtures/         curso.json de ejemplo, usados como prueba de contrato
tools/              Utilidades: sembrar datos, verificar secretos
tests/              Pruebas
```

**Stack:** Python 3.13 · FastAPI · PostgreSQL 17 · Redis + RQ · SQLAlchemy 2 · Alembic ·
JWT + Argon2 · htmx + Jinja2 en el frontend, **sin Node ni paso de compilación**.

**Convención de rutas:** `/api/*` devuelve JSON, `/ui/*` devuelve fragmentos HTML para htmx.

---

## Arrancar en local

Requisitos: Python 3.13, Docker Desktop **abierto**.

```bash
git clone git@github.com:utpl/Atomatizacion_Ediloja.git
cd Atomatizacion_Ediloja

python3 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -e .                    # sin esto, los imports de libs/ fallan

cp .env.example .env                # y rellena los valores

docker compose up -d                # PostgreSQL 17 + Redis 7
alembic upgrade head                # crea las 12 tablas
python tools/sembrar_datos.py       # roles y usuario de prueba

make api                            # http://localhost:8000/docs
```

En el IDE, selecciona el intérprete de `.venv`: `Cmd+Shift+P` → *Python: Select Interpreter*.
Es el paso que más se olvida y produce errores que parecen otra cosa.

### Comandos

| Comando | Qué hace |
|---|---|
| `make api` | Levanta la API con recarga automática |
| `make test` | Ejecuta las pruebas |
| `make lint` | Comprueba estilo con ruff |
| `make format` | Formatea |
| `make secretos` | Busca credenciales en el código |
| `make bd` | Levanta PostgreSQL y Redis |

---

## Roles

Seis, con alcance aplicado **dentro de la consulta SQL**, no filtrando en Python:

| Rol | Ve |
|---|---|
| `docente` | Sus propias guías |
| `revisor_di`, `qa`, `operador` | Las que tienen asignadas |
| `coordinador`, `admin` | Todas |

Dos detalles de seguridad deliberados: el login dice "correo o contraseña incorrectos" sin
revelar cuál falló, y pedir una guía ajena devuelve **404, no 403** — un 403 confirmaría que
esa guía existe, y eso ya es información.

---

## Editar contenido

El editor no manda parches de JSON: manda **operaciones semánticas**.

```
POST /api/versiones/{id}/editar
{
  "sha256": "…",
  "operaciones": [
    {"operacion": "actualizar_bloque", "bloque_id": "b7f3a9c2",
     "campos": {"texto": "…"}}
  ]
}
```

Ocho operaciones: `actualizar_bloque`, `eliminar_bloque`, `insertar_bloque`, `mover_bloque`,
`insertar_pagina`, `eliminar_pagina`, `mover_pagina`, `actualizar_pagina`.

Un índice se invalida en cuanto otra operación inserta algo antes; un id, no. Y una
operación con nombre se puede auditar y deshacer.

El `sha256` es control de concurrencia optimista: si no coincide, **409** y hay que
recargar. Sin él, el docente con el editor abierto en dos pestañas se pisa su propio
trabajo en silencio.

Al enviar a revisión la versión se **congela** y la edición devuelve 409. Solo un revisor
puede devolverla.

---

## Despliegue

Imágenes: `Dockerfile.api` y `Dockerfile.worker`. Comparten base a propósito — si divergen,
acabas depurando por qué algo funciona en la API y falla en el worker.

Todo se lee del entorno con `pydantic-settings`, así que **lo único que cambia entre local
y AWS es `DATABASE_URL`**. Destino: RDS PostgreSQL 17, ElastiCache, ECS Fargate, S3 y
Secrets Manager.

Las credenciales **nunca** van en archivos. `tools/verificar_secretos.sh` corre en el hook
de pre-commit y en CI.

---

## Documentación

- `docs/01-arquitectura.md`
- `docs/02-reglas-de-negocio.md` — reglas institucionales de EdiLoja
- `docs/03-deuda-tecnica.md`
- `docs/adr/` — decisiones de arquitectura y por qué se tomaron
- `docs/contrato-frontend-backend.md`
