# Construye tu monorepo desde cero — guía paso a paso

**Para quién es esto:** para ti, que ya tienes cinco sistemas funcionando y quieres unificarlos
haciéndolo con tus propias manos, entendiendo cada paso y practicando las herramientas que se piden
en cualquier oferta de desarrollo.

**Cómo usar esta guía:** cada paso tiene tres partes.

> **Escribes:** el comando o el archivo exacto.
> **Qué hace:** qué acaba de pasar en tu máquina.
> **Por qué importa:** el concepto detrás, y por qué un entrevistador se fija en eso.

No copies todo de golpe. Haz un paso, mira el resultado, entiende qué cambió, y sigue.

**Tiempo estimado:** de 6 a 10 horas repartidas en varios días. No es una carrera.

---

## Índice

- [Antes de empezar](#antes-de-empezar)
- [Parte 0 — Preparar la máquina](#parte-0--preparar-la-máquina)
- [Parte 1 — Crear el repositorio](#parte-1--crear-el-repositorio)
- [Parte 2 — Seguridad primero](#parte-2--seguridad-primero)
- [Parte 3 — Diseñar la estructura](#parte-3--diseñar-la-estructura)
- [Parte 4 — El entorno de Python](#parte-4--el-entorno-de-python)
- [Parte 5 — Herramientas de calidad](#parte-5--herramientas-de-calidad)
- [Parte 6 — Migrar los artefactos compartidos](#parte-6--migrar-los-artefactos-compartidos)
- [Parte 7 — Migrar la ingesta de Word](#parte-7--migrar-la-ingesta-de-word)
- [Parte 8 — Migrar el validador web](#parte-8--migrar-el-validador-web)
- [Parte 9 — Migrar el pipeline Canvas](#parte-9--migrar-el-pipeline-canvas)
- [Parte 10 — Migrar el migrador de metacursos](#parte-10--migrar-el-migrador-de-metacursos)
- [Parte 11 — Migrar el generador con IA](#parte-11--migrar-el-generador-con-ia)
- [Parte 12 — Resolver la duplicación](#parte-12--resolver-la-duplicación)
- [Parte 13 — Extraer bibliotecas comunes](#parte-13--extraer-bibliotecas-comunes)
- [Parte 14 — Pruebas](#parte-14--pruebas)
- [Parte 15 — Integración continua](#parte-15--integración-continua)
- [Parte 16 — Publicar y presentar](#parte-16--publicar-y-presentar)
- [Chuleta de comandos](#chuleta-de-comandos)

---

## Antes de empezar

### Tus cinco sistemas

| Proyecto original | Qué hace | Tamaño |
|---|---|---|
| `pipeline_fable` | Word → JSON canónico, determinista + re-estilador | ~2.500 líneas Py |
| `docx_parser 2` | Pipeline completo Word → JSON → Canvas, con dashboard Flask | **17.339 líneas Py, 42 scripts** |
| `MIGRADOR` | Migración de metacursos Canvas 16 → N semanas | ~5.500 líneas Py |
| `app-creacion-asignaturas` | Generación de guías con IA, servidor MCP | ~2.500 líneas TS/JS |
| *(validadores HTML)* | Validación en navegador, sin servidor | ~1.500 líneas JS |

En total, **cerca de 30.000 líneas**. Esto no es un proyecto de práctica: es un sistema real. Eso
juega a tu favor.

### Una advertencia sobre el orden

Vas a migrar de lo simple a lo complejo, no en el orden en que los escribiste. Primero lo que no
tiene dependencias (datos y plantillas), después lo pequeño, y al final el monstruo de 17.000 líneas.
Así, cuando llegues a lo difícil, ya dominas el flujo de trabajo.

---

## Parte 0 — Preparar la máquina

### Paso 0.1 — Comprobar qué tienes

> **Escribes:**
> ```bash
> git --version
> python3 --version
> node --version
> ```

> **Qué hace:** te dice si están instalados y en qué versión.

> **Por qué importa:** antes de instalar nada, se comprueba. Media hora de depuración se ahorra con
> tres comandos. Si alguno falla, instálalo: Git y Python vienen con las Command Line Tools de
> macOS (`xcode-select --install`); Node se instala mejor con `nvm`.

### Paso 0.2 — Configurar tu identidad en Git

> **Escribes:**
> ```bash
> git config --global user.name "Tu Nombre"
> git config --global user.email "tu@correo.com"
> git config --global init.defaultBranch main
> ```

> **Qué hace:** cada commit que hagas llevará tu nombre. La tercera línea hace que la rama principal
> se llame `main` en vez de `master`.

> **Por qué importa:** el correo del commit es lo que enlaza tu trabajo con tu perfil de GitHub. Si
> está mal, tus contribuciones no aparecen en tu perfil — y ese perfil es parte de tu currículum.

---

## Parte 1 — Crear el repositorio

### Paso 1.1 — La carpeta

> **Escribes:**
> ```bash
> mkdir plataforma-contenidos
> cd plataforma-contenidos
> ```

> **Qué hace:** crea la carpeta raíz y entra.

> **Por qué importa:** el nombre. `plataforma-contenidos` describe **qué es**, no cómo está hecho.
> Nombres como `mi-proyecto`, `sistema-final-v2` o `docx_parser 2` (con espacio, que rompe scripts)
> dicen que no se pensó. Todo en minúsculas, con guiones, sin espacios ni tildes.

### Paso 1.2 — Inicializar Git

> **Escribes:**
> ```bash
> git init
> ```

> **Qué hace:** crea la carpeta oculta `.git`. A partir de ahora Git observa todo lo que pasa aquí
> dentro.

> **Por qué importa:** esto es lo que convierte una carpeta en un proyecto. El historial que
> construyas a partir de aquí es la prueba de cómo trabajas: si haces un solo commit gigante llamado
> "subida inicial", eso también se ve.

### Paso 1.3 — El primer archivo

> **Escribes:** crea `README.md` con este contenido mínimo:
> ```markdown
> # Plataforma de Contenidos Académicos
>
> Monorepo con los sistemas de automatización de la producción de guías
> didácticas y metacursos en Canvas LMS.
>
> **Estado:** en construcción.
> ```

> **Qué hace:** nada técnico. Es texto.

> **Por qué importa:** el README es lo primero (y a veces lo único) que lee alguien que llega a tu
> repositorio. Lo empiezas ahora y lo vas completando; al final de la guía será el mapa del proyecto.

### Paso 1.4 — Tu primer commit

> **Escribes:**
> ```bash
> git add README.md
> git commit -m "docs: iniciar el repositorio con el README"
> ```

> **Qué hace:** `add` marca el archivo para incluirlo; `commit` guarda una foto permanente del
> estado del proyecto con ese mensaje.

> **Por qué importa:** fíjate en el prefijo `docs:`. Es la convención **Conventional Commits**, y se
> usa en la mayoría de equipos profesionales:
>
> | Prefijo | Cuándo |
> |---|---|
> | `feat:` | funcionalidad nueva |
> | `fix:` | corrección de un error |
> | `docs:` | solo documentación |
> | `refactor:` | reorganizar sin cambiar comportamiento |
> | `chore:` | mantenimiento, dependencias, configuración |
> | `test:` | pruebas |
>
> Un historial con estos prefijos se lee de un vistazo y permite generar changelogs automáticamente.
> Es un detalle pequeño que distingue a alguien que ha trabajado en equipo.

---

## Parte 2 — Seguridad primero

Esta parte va **antes** de mover un solo archivo, y por una razón muy concreta: en tu proyecto
`MIGRADOR` había un archivo `variables_entorno.txt` con tu clave de Anthropic, tu token de Canvas y
una clave de Gemini en texto plano. Si ese archivo entra en un commit, queda en el historial de Git
**para siempre**, aunque lo borres después.

### Paso 2.1 — Revocar lo expuesto

> **Escribes:** nada. Vas a las consolas y revocas:
> - Anthropic → API Keys → revocar la clave expuesta, crear una nueva
> - Canvas → Cuenta → Configuración → eliminar ese token de acceso
> - Google AI Studio → revocar la clave de Gemini

> **Por qué importa:** una clave expuesta se considera comprometida desde el momento en que sale de
> tu máquina. No importa que "solo tú tengas el ZIP". Revocar es gratis; una factura de API ajena o
> un acceso indebido a Canvas, no.

### Paso 2.2 — El `.gitignore`

> **Escribes:** crea `.gitignore`:
> ```gitignore
> # ─── Credenciales: NUNCA ───
> .env
> .env.*
> !.env.example
> *variables_entorno*
> *token*.txt
> *.pem
> *.key
>
> # ─── Python ───
> venv/
> .venv/
> __pycache__/
> *.py[cod]
> .pytest_cache/
> .ruff_cache/
>
> # ─── Node ───
> node_modules/
> dist/
>
> # ─── macOS ───
> .DS_Store
> __MACOSX/
>
> # ─── Salidas y temporales ───
> salida/
> resultados/
> *.bak
> *.log
> _archivo/
>
> # ─── Binarios pesados ───
> *.zip
> !packages/plantillas/**/*.zip
> ```

> **Qué hace:** Git ignora todo lo que coincida con estos patrones. La línea `!.env.example` es una
> excepción: ese sí se sube.

> **Por qué importa:** tres detalles que valen la pena entender:
> - **`.env` fuera, `.env.example` dentro.** El primero tiene tus claves reales; el segundo tiene las
>   mismas variables vacías, para que otra persona sepa qué necesita configurar. Es el patrón
>   estándar.
> - **`venv/` y `node_modules/` fuera.** Son dependencias reinstalables, no código tuyo. Un
>   `node_modules` puede pesar cientos de megas. Esa es, casi seguro, la razón de que tu proyecto
>   pesara 90 MB.
> - **`.DS_Store` fuera.** Archivos de macOS que no aportan nada. Tus ZIP venían llenos de ellos y de
>   carpetas `__MACOSX`.

### Paso 2.3 — El `.env.example`

> **Escribes:** crea `.env.example`:
> ```bash
> # Copiar como .env y rellenar. El .env NUNCA se sube.
>
> # Canvas LMS
> CANVAS_URL=https://utpl.test.instructure.com
> CANVAS_TOKEN=
> CANVAS_ACCOUNT_ID=1
>
> # Proveedores de IA
> ANTHROPIC_API_KEY=
> GEMINI_API_KEY=
> OPENAI_API_KEY=
>
> # Rutas
> RUTA_PLANTILLAS=./packages/plantillas
> RUTA_CANON=./packages/canon
> ```

> **Por qué importa:** es documentación ejecutable. Alguien clona tu repositorio, hace
> `cp .env.example .env`, rellena y funciona. Sin esto, tiene que leer todo el código buscando
> `os.getenv(...)` para adivinar qué variables existen.

### Paso 2.4 — Un detector de secretos

> **Escribes:** crea `tools/verificar_secretos.sh`:
> ```bash
> #!/usr/bin/env bash
> set -uo pipefail
>
> PATRONES='sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,}|[0-9]{4}~[A-Za-z0-9]{40,}|AIza[A-Za-z0-9_-]{30,}|AKIA[0-9A-Z]{16}'
>
> HALLAZGOS=$(grep -rEIn --exclude-dir={.git,node_modules,.venv,venv} \
>   --exclude=".env" --exclude="verificar_secretos.sh" \
>   "$PATRONES" . 2>/dev/null || true)
>
> if [ -n "$HALLAZGOS" ]; then
>   echo "✖ CREDENCIALES ENCONTRADAS — no hagas commit:"
>   echo "$HALLAZGOS" | cut -c1-100
>   exit 1
> fi
> echo "✔ Sin credenciales detectadas."
> ```
> Y lo haces ejecutable:
> ```bash
> chmod +x tools/verificar_secretos.sh
> bash tools/verificar_secretos.sh
> ```

> **Qué hace:** busca patrones de claves conocidas en todo el proyecto. Devuelve código de salida 1
> si encuentra algo, que es lo que permite usarlo en automatismos.

> **Por qué importa:** en el paso 5.3 lo vas a enganchar a un *hook* de Git para que se ejecute solo
> antes de cada commit. Automatizar la seguridad en vez de confiar en la memoria es exactamente el
> tipo de decisión que se valora.

### Paso 2.5 — Guardar

> **Escribes:**
> ```bash
> git add .gitignore .env.example tools/
> git commit -m "chore: configurar gitignore, plantilla de entorno y detector de secretos"
> ```

---

## Parte 3 — Diseñar la estructura

### Paso 3.1 — Crear las carpetas

> **Escribes:**
> ```bash
> mkdir -p apps packages libs/py libs/js docs/adr docs/heredado tools datos_ejemplo
> ```

> **Qué hace:** crea el esqueleto. `-p` crea las carpetas intermedias que falten.

> **Por qué importa:** esta es la decisión de arquitectura más importante de todo el proyecto, así
> que vale la pena entender el criterio:
>
> | Carpeta | Qué va aquí | Criterio |
> |---|---|---|
> | `apps/` | Cosas que **se ejecutan** | ¿Tiene un punto de entrada? ¿Se lanza? → aquí |
> | `packages/` | **Datos** compartidos: plantillas, diccionarios, esquemas | ¿Es un artefacto que varias apps consumen y que no es código? → aquí |
> | `libs/` | **Código** reutilizable | ¿Lo importan varias apps pero no se ejecuta solo? → aquí |
> | `docs/` | Conocimiento | |
> | `tools/` | Scripts de mantenimiento del propio repo | |
> | `datos_ejemplo/` | Muestras para probar | Sin datos personales reales |
>
> La distinción clave, y la que demuestra criterio, es **`packages/` frente a `libs/`**: tu
> `config_canonico.json` y tu plantilla `.dotx` no son código, son **datos institucionales**. Que
> vivan en su propio sitio deja claro que son la fuente de verdad y que no se duplican.

### Paso 3.2 — Dar nombre a las aplicaciones

> **Escribes:**
> ```bash
> mkdir -p apps/ingesta-word apps/validador-web apps/pipeline-canvas apps/migrador-canvas apps/generador-guias
> mkdir -p packages/canon packages/plantillas packages/esquemas
> ```

> **Qué hace:** crea el hueco de cada sistema.

> **Por qué importa:** fíjate en el cambio de nombres:
>
> | Antes | Ahora | Por qué |
> |---|---|---|
> | `pipeline_fable` | `ingesta-word` | "fable" no dice nada a nadie |
> | `docx_parser 2` | `pipeline-canvas` | Tenía **espacio en el nombre**, que rompe scripts, y el "2" era una versión |
> | `MIGRADOR` | `migrador-canvas` | Mayúsculas y sin contexto |
> | `app-creacion-asignaturas` | `generador-guias` | Describe lo que hace |
>
> Regla: el nombre de una carpeta debe responder *"¿qué hace esto?"* sin abrir nada. Y nunca, jamás,
> espacios ni números de versión en nombres de carpeta — para eso está Git.

### Paso 3.3 — Marcar las carpetas vacías

> **Escribes:**
> ```bash
> find apps packages libs docs datos_ejemplo -type d -empty -exec touch {}/.gitkeep \;
> git add . && git commit -m "chore: crear la estructura de carpetas del monorepo"
> ```

> **Qué hace:** Git no guarda carpetas vacías, solo archivos. `.gitkeep` es un archivo vacío por
> convención para forzar que la carpeta exista.

> **Por qué importa:** es un truco pequeño, pero si no lo sabes te preguntas por qué desaparecen tus
> carpetas al clonar en otra máquina.

---

## Parte 4 — El entorno de Python

### Paso 4.1 — Crear el entorno virtual

> **Escribes:**
> ```bash
> python3 -m venv .venv
> source .venv/bin/activate
> ```
> Tu prompt cambia y empieza por `(.venv)`.

> **Qué hace:** crea una instalación de Python aislada dentro del proyecto. Todo lo que instales con
> `pip` a partir de ahora vive ahí, no en tu sistema.

> **Por qué importa:** sin esto, cada proyecto pelea por las versiones de las bibliotecas del
> sistema. Instalas `python-docx 1.1` para uno y rompes otro que usaba la `0.8`. En tu volcado de
> entorno se veía Anaconda mezclado con un venv y con Homebrew: ese es exactamente el escenario que
> el aislamiento evita.
>
> Nota: `.venv` con punto delante (queda oculto y agrupado) es la convención más extendida hoy.

### Paso 4.2 — Consolidar las dependencias

> **Escribes:** crea `requirements.txt`:
> ```
> # ─── Documentos ───
> python-docx==1.1.2
> openpyxl==3.1.5
> beautifulsoup4==4.12.2
> lxml==5.3.0
>
> # ─── Canvas y HTTP ───
> requests==2.32.3
> canvasapi==3.6.0
>
> # ─── Interfaz local ───
> Flask==3.1.3
>
> # ─── IA ───
> anthropic==0.111.0
>
> # ─── Utilidades ───
> python-dotenv==1.0.1
>
> # ─── Desarrollo ───
> pytest==8.3.4
> ruff==0.8.4
> ```
> Y lo instalas:
> ```bash
> pip install -r requirements.txt
> ```

> **Qué hace:** instala solo lo que realmente usas, con versiones fijas.

> **Por qué importa:** tu `MIGRADOR/requirements.txt` tenía **135 líneas**, porque salió de un
> `pip freeze` que vuelca todo lo instalado, incluidas las dependencias de tus dependencias y cosas
> que nunca importaste (`Faker`, `matplotlib`, `CairoSVG`…).
>
> La diferencia:
> - `pip freeze` → todo lo que hay instalado, sin distinguir qué necesitas
> - Un `requirements.txt` escrito a mano → **lo que tu código importa de verdad**
>
> El segundo se lee, se entiende y se mantiene. Y las versiones fijadas con `==` hacen que el
> proyecto se instale igual dentro de un año.
>
> Para comprobar qué importas realmente:
> ```bash
> grep -rhE "^(import|from) " --include="*.py" . | awk '{print $2}' | cut -d. -f1 | sort -u
> ```

### Paso 4.3 — Guardar

> **Escribes:**
> ```bash
> git add requirements.txt && git commit -m "chore: definir dependencias mínimas de Python"
> ```

---

## Parte 5 — Herramientas de calidad

### Paso 5.1 — El formateador y linter

> **Escribes:** crea `pyproject.toml`:
> ```toml
> [tool.ruff]
> line-length = 100
> target-version = "py311"
>
> [tool.ruff.lint]
> select = ["E", "F", "I", "UP", "B"]
> ignore = ["E501"]
>
> [tool.pytest.ini_options]
> testpaths = ["tests"]
> ```
> Y lo pruebas:
> ```bash
> ruff check .
> ruff format .
> ```

> **Qué hace:** `ruff check` busca problemas (variables sin usar, importaciones desordenadas, errores
> comunes). `ruff format` reformatea el código con un estilo consistente.

> **Por qué importa:** los códigos que activaste significan: `E` errores de estilo, `F` errores
> lógicos, `I` orden de importaciones, `UP` sintaxis anticuada, `B` errores frecuentes.
>
> El valor real no es la estética: es que **desaparecen las discusiones sobre formato** y los
> *diffs* de Git solo muestran cambios de fondo. Ruff está escrito en Rust y es tan rápido que
> puedes ejecutarlo en cada guardado.

### Paso 5.2 — El Makefile

> **Escribes:** crea `Makefile` (ojo: la indentación **debe ser tabulador**, no espacios):
> ```makefile
> .PHONY: setup lint format test secretos limpiar
>
> setup:
> 	python3 -m venv .venv
> 	.venv/bin/pip install -U pip
> 	.venv/bin/pip install -r requirements.txt
>
> lint:
> 	ruff check .
>
> format:
> 	ruff format .
>
> test:
> 	pytest -q
>
> secretos:
> 	bash tools/verificar_secretos.sh
>
> limpiar:
> 	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
> 	find . -name ".DS_Store" -delete
> ```
> Pruébalo:
> ```bash
> make lint
> ```

> **Qué hace:** da nombres cortos a comandos largos.

> **Por qué importa:** es la interfaz de tu proyecto. Alguien llega, escribe `make setup` y ya está
> funcionando, sin leer el README completo. Make tiene cuarenta años y sigue siendo el estándar de
> facto para esto.

### Paso 5.3 — El hook de pre-commit

> **Escribes:** crea `.git/hooks/pre-commit`:
> ```bash
> #!/usr/bin/env bash
> echo "→ Verificando credenciales..."
> bash tools/verificar_secretos.sh || exit 1
> echo "→ Lint..."
> ruff check . || exit 1
> ```
> Y:
> ```bash
> chmod +x .git/hooks/pre-commit
> ```

> **Qué hace:** Git ejecuta esto automáticamente antes de cada commit. Si algo devuelve error, el
> commit se cancela.

> **Por qué importa:** es imposible ahora subir una credencial por descuido. El principio general —
> **automatiza lo que no puedes permitirte olvidar** — es lo que se valora, no el script en sí.
>
> Detalle a saber: los hooks viven en `.git/`, que **no se sube al repositorio**. Para compartirlos
> con un equipo existe la herramienta `pre-commit` (en Python). Menciónalo si te preguntan.

> **Escribes:**
> ```bash
> git add pyproject.toml Makefile && git commit -m "chore: añadir ruff, Makefile y hook de pre-commit"
> ```

---

## Parte 6 — Migrar los artefactos compartidos

Empiezas por aquí porque **no dependen de nada**. Son datos.

### Paso 6.1 — El diccionario canónico

> **Escribes:**
> ```bash
> cp /ruta/a/pipeline_fable/config_canonico.json packages/canon/
> ```

> **Qué hace:** copia (no mueve) el archivo. El original sigue donde estaba.

> **Por qué importa:** copia, nunca muevas, hasta que todo funcione. Si algo sale mal, tienes el
> original intacto.
>
> Este archivo es, probablemente, **el activo más valioso de los cinco proyectos**: contiene todas
> las variantes reales con que los docentes escriben la estructura, incluidos los typos del corpus
> (`APRENIZAJE`, `CONTABILIDA`). Reconstruirlo significaría volver a analizar decenas de guías.

### Paso 6.2 — Documentar por qué es importante

> **Escribes:** crea `packages/canon/README.md`:
> ```markdown
> # Diccionario canónico
>
> `config_canonico.json` es la **única fuente de verdad** para la nomenclatura
> estructural de las guías.
>
> Contiene las variantes de anclas, las expresiones regulares de marcadores
> (semana, resultado de aprendizaje, unidad, autoevaluación), los 18
> focalizadores, la tolerancia difusa y el prefijo de estilos `GD-`.
>
> ## Regla
>
> Para añadir una variante nueva se edita **este archivo, nunca el código**.
> Si mañana aparece "Sesión" en lugar de "Semana", se agrega aquí.
>
> Incluye deliberadamente typos reales del corpus (`APRENIZAJE`,
> `CONTABILIDA`). No son errores: son variantes que hay que seguir aceptando.
>
> ## Quién lo consume
>
> - `apps/ingesta-word/pipeline_word_a_json.py`
> - `apps/validador-web/nucleo_pipeline.js`
> ```

> **Por qué importa:** un README por paquete es lo que separa un monorepo navegable de un vertedero.
> Y ese párrafo sobre los typos es conocimiento que se perdería si te vas.

### Paso 6.3 — Las plantillas

> **Escribes:**
> ```bash
> cp /ruta/a/pipeline_fable/EdiLoja_Plantilla_Guia_Didactica.dotx packages/plantillas/
> cp /ruta/a/pipeline_fable/tema_canvas_red3.css packages/plantillas/
> cp -r /ruta/a/MIGRADOR/plantilla_oficial packages/plantillas/canvas_oficial
> cp -r "/ruta/a/docx_parser 2/assets/plantilla" packages/plantillas/assets
> ```

> **Por qué importa:** aquí resuelves una duplicación real. Tenías la plantilla de Canvas en
> `MIGRADOR/plantilla_oficial/` **y** en `docx_parser 2/assets/`. Dos copias que pueden divergir sin
> que nadie se entere. Ahora hay una sola, y las apps la referencian.
>
> Este es literalmente el argumento a favor de un monorepo. Si te preguntan en una entrevista "¿por
> qué monorepo?", esta es tu respuesta con ejemplo propio.

### Paso 6.4 — Cuidado con el peso

> **Escribes:**
> ```bash
> du -sh packages/plantillas/
> find packages/plantillas -type f -size +5M
> ```

> **Qué hace:** te dice cuánto ocupa y qué archivos son grandes.

> **Por qué importa:** Git guarda **cada versión** de cada archivo binario. Un `.zip` de 15 MB
> modificado cinco veces son 75 MB de historial que nunca se recuperan. Si algo pesa mucho:
> - Los SVG e iconos pequeños: van al repo sin problema.
> - Los ZIP de recursos y las imágenes grandes: fuera del repo, o con **Git LFS**.
>
> Tu `docx_parser 2` traía `imagenes 2.zip` de 15 MB y `Archivo.zip` de 500 KB. Esos no entran.

> **Escribes:**
> ```bash
> git add packages/ && git commit -m "feat: consolidar diccionario canónico y plantillas institucionales"
> ```

---

## Parte 7 — Migrar la ingesta de Word

### Paso 7.1 — Copiar solo el código

> **Escribes:**
> ```bash
> cd apps/ingesta-word
> cp /ruta/a/pipeline_fable/pipeline_word_a_json.py .
> cp /ruta/a/pipeline_fable/reestilar_word.py .
> cp /ruta/a/pipeline_fable/extraer_estructura.py .
> cd ../..
> ```

> **Qué hace:** copia los tres scripts. **No** copies los `.docx` de ejemplo, ni los HTML gigantes,
> ni los `__pycache__`.

> **Por qué importa:** disciplina de migración. Cada archivo que copias, te preguntas: *¿esto es
> código fuente, o es una salida?* Los `.docx` de ejemplo van a `datos_ejemplo/`; los archivos
> generados no van a ninguna parte.

### Paso 7.2 — Arreglar la ruta del diccionario

> **Escribes:** busca en `pipeline_word_a_json.py` dónde carga el diccionario:
> ```bash
> grep -n "config_canonico" apps/ingesta-word/pipeline_word_a_json.py
> ```
> Y ajusta la ruta para que apunte a `packages/canon/`. Algo como:
> ```python
> from pathlib import Path
>
> RAIZ = Path(__file__).resolve().parents[2]
> RUTA_CANON = RAIZ / "packages" / "canon" / "config_canonico.json"
> ```

> **Qué hace:** `Path(__file__)` es la ruta de este archivo; `.parents[2]` sube dos niveles
> (`ingesta-word` → `apps` → raíz).

> **Por qué importa:** este es **el paso donde de verdad se integra el monorepo**. Antes cada
> proyecto tenía su copia; ahora todos apuntan al mismo sitio.
>
> Y hay un detalle que debes resolver: tu pipeline tiene una **copia embebida del diccionario**
> dentro del código, como respaldo por si no encuentra el archivo. Elimínala. Un respaldo silencioso
> que puede divergir de la fuente real es peor que un error ruidoso.

### Paso 7.3 — Probar que sigue funcionando

> **Escribes:**
> ```bash
> cp /ruta/a/una_guia.docx datos_ejemplo/
> python apps/ingesta-word/pipeline_word_a_json.py datos_ejemplo/una_guia.docx /tmp/salida/
> ls /tmp/salida/
> ```

> **Por qué importa:** **regla de oro de toda migración: mover, probar, commit.** Nunca muevas cinco
> cosas y pruebes al final, porque si algo falla no sabes cuál fue.

### Paso 7.4 — README y commit

> **Escribes:** crea `apps/ingesta-word/README.md` explicando qué hace, cómo se usa y qué produce.
> Luego:
> ```bash
> git add apps/ingesta-word datos_ejemplo
> git commit -m "feat: migrar la ingesta Word a JSON al monorepo"
> ```

---

## Parte 8 — Migrar el validador web

### Paso 8.1 — Entender antes de copiar

Tu validador **se compila**: `plantilla_validador.html` tiene marcadores `__NUCLEO__`,
`__CANVASGEN__` y `__TEMA_CSS__` que se sustituyen por el contenido de otros archivos, produciendo
`validador_guias_word_json.html`.

> **Por qué importa:** hay que distinguir **fuente** de **artefacto compilado**. La fuente se edita y
> se versiona; el compilado se genera. Si editas el compilado, pierdes el cambio en la siguiente
> compilación.

### Paso 8.2 — Copiar las fuentes

> **Escribes:**
> ```bash
> cd apps/validador-web
> cp /ruta/a/pipeline_fable/plantilla_validador.html .
> cp /ruta/a/pipeline_fable/generador_canvas.js .
> cp /ruta/a/pipeline_fable/previsualizador_guias_canvas.html .
> cd ../..
> ```

> **Atención:** falta `nucleo_pipeline.js`, el motor JavaScript. Tu documentación lo cita pero no
> estaba en el ZIP. **Búscalo antes de seguir**: sin él no puedes recompilar el validador. Si no
> aparece, anótalo como deuda conocida en el README.

### Paso 8.3 — Escribir el script de compilación

> **Escribes:** crea `apps/validador-web/build.py`:
> ```python
> #!/usr/bin/env python3
> """Compila el validador inyectando los scripts en la plantilla."""
> from pathlib import Path
>
> AQUI = Path(__file__).parent
> RAIZ = AQUI.parents[1]
>
> plantilla = (AQUI / "plantilla_validador.html").read_text(encoding="utf-8")
>
> reemplazos = {
>     "__NUCLEO__": AQUI / "nucleo_pipeline.js",
>     "__CANVASGEN__": AQUI / "generador_canvas.js",
>     "__TEMA_CSS__": RAIZ / "packages/plantillas/tema_canvas_red3.css",
> }
>
> for marcador, ruta in reemplazos.items():
>     if not ruta.exists():
>         raise SystemExit(f"Falta: {ruta}")
>     plantilla = plantilla.replace(marcador, ruta.read_text(encoding="utf-8"))
>
> salida = AQUI / "validador_guias_word_json.html"
> salida.write_text(plantilla, encoding="utf-8")
> print(f"✔ Generado: {salida} ({salida.stat().st_size // 1024} KB)")
> ```

> **Qué hace:** automatiza lo que antes hacías a mano.

> **Por qué importa:** convertir un proceso manual en un script reproducible es de las cosas más
> valoradas en desarrollo. Además, ahora el compilado puede ir al `.gitignore`: se genera cuando hace
> falta.

> **Escribes:** añade al `.gitignore`:
> ```gitignore
> apps/validador-web/validador_guias_word_json.html
> ```
> Y al `Makefile`:
> ```makefile
> validador:
> 	python apps/validador-web/build.py
> ```

---

## Parte 9 — Migrar el pipeline Canvas

Este es el grande: **17.339 líneas en 42 scripts**. No lo copies de golpe.

### Paso 9.1 — Entender el orden del pipeline

Tu propio `preparar_curso.sh` documenta el flujo. Léelo primero. El orden es:

```
Word del docente
   │
   ├─ etiquetar_auto.py          aplica estilos GD-
   ├─ clasificar_docx.py         semáforo verde/amarillo/rojo
   ├─ docx_a_json.py             → salida.json
   │
   ├─ curar_contextualizaciones.py   (IA) → salida_contextualizada.json
   ├─ curar_autoevaluaciones.py      (IA) → salida_curada.json
   ├─ generar_imagenes.py            (IA)
   ├─ generar_diagramas.py           (IA)
   │
   ├─ render_inicio_ed.py        → HTML de inicio
   ├─ render_ed.py               → HTML de semanas  (el más complejo)
   ├─ render_fuentes_ed.py
   ├─ render_encuentros_ed.py
   │
   └─ canvas_subir_plantilla.py  → mapa_plantilla.json
      canvas_subir_imagenes.py   → mapa_imagenes.json
      canvas_crear_modulos.py
      canvas_crear_paginas.py
      canvas_llenar_*.py         → curso publicado
```

> **Por qué importa:** con 42 scripts, la única forma de no perderte es tener el mapa antes de tocar
> nada. Y ese diagrama va directo al README de la aplicación.

### Paso 9.2 — Organizar por función, no en plano

> **Escribes:**
> ```bash
> cd apps/pipeline-canvas
> mkdir -p ingesta agentes render canvas diagnostico
> cd ../..
> ```
> Y copias agrupando:
> ```bash
> P="/ruta/a/docx_parser 2"
> D="apps/pipeline-canvas"
>
> # Ingesta
> cp "$P"/{docx_a_json.py,etiquetar_auto.py,clasificar_docx.py,validar_entrada.py} $D/ingesta/
>
> # Agentes de IA
> cp "$P"/{curar_contextualizaciones.py,curar_autoevaluaciones.py} $D/agentes/
> cp "$P"/{generar_imagenes.py,generar_diagramas.py,generar_recurso_educativo.py} $D/agentes/
>
> # Renders
> cp "$P"/render_*.py $D/render/
> cp "$P"/plantilla_config.py $D/render/
>
> # Canvas
> cp "$P"/canvas_*.py $D/canvas/
>
> # Diagnóstico
> cp "$P"/{diagnostico_*.py,inspeccionar_*.py,verificar_imagenes.py} $D/diagnostico/
>
> # Orquestador
> cp "$P"/{server.py,preview_ediloja.py,preparar_curso.sh} $D/
> ```

> **Qué hace:** convierte 42 archivos en plano en cinco grupos con significado.

> **Por qué importa:** esto es **refactorización estructural**, y es de lo más valorado. No cambias
> ni una línea de lógica; cambias la capacidad de alguien de entender el sistema. Un directorio con
> 42 archivos sueltos es ilegible; cinco carpetas nombradas por función se entienden en treinta
> segundos.
>
> Nota lo que **no** copiaste: `server_ORIGINAL_respaldo.py`. Los respaldos manuales no van al
> repositorio — para eso está Git. Si necesitas esa versión, está en el historial.

### Paso 9.3 — Arreglar las importaciones

Al mover archivos a subcarpetas, los `import` entre ellos se rompen.

> **Escribes:**
> ```bash
> python -c "import apps.pipeline_canvas.render.render_ed" 2>&1 | head -5
> ```
> o simplemente ejecuta un script y mira el error.

> **Por qué importa:** aquí vas a aprender el sistema de paquetes de Python a golpes, que es como se
> aprende de verdad. La solución limpia: añade un `__init__.py` vacío en cada subcarpeta y usa
> importaciones relativas (`from ..ingesta import docx_a_json`), o define el proyecto como paquete
> instalable con `pip install -e .`.
>
> Es la parte más tediosa de toda la guía. Tómatela con calma y ve arreglando script por script,
> probando cada uno.

### Paso 9.4 — Commits pequeños

> **Escribes:** haz un commit por grupo, no uno gigante:
> ```bash
> git add apps/pipeline-canvas/ingesta && git commit -m "feat: migrar módulo de ingesta del pipeline Canvas"
> git add apps/pipeline-canvas/agentes && git commit -m "feat: migrar agentes de IA del pipeline Canvas"
> git add apps/pipeline-canvas/render && git commit -m "feat: migrar renderizadores de plantilla institucional"
> git add apps/pipeline-canvas/canvas && git commit -m "feat: migrar módulo de subida a Canvas"
> git add apps/pipeline-canvas && git commit -m "feat: migrar orquestador y diagnósticos"
> ```

> **Por qué importa:** si algo se rompe, `git bisect` encuentra el commit culpable en minutos. Con
> un commit de 17.000 líneas, no. Además, un historial así **se lee como la crónica del trabajo**, y
> eso es exactamente lo que un entrevistador técnico mira cuando le pasas un repositorio.

---

## Parte 10 — Migrar el migrador de metacursos

Ya conoces el procedimiento. Lo nuevo aquí es que hay una app Flask con frontend.

> **Escribes:**
> ```bash
> M="/ruta/a/MIGRADOR"
> D="apps/migrador-canvas"
> mkdir -p $D/static $D/templates
>
> cp $M/{app.py,generar_curso.py,plantilla.py,canvas_assets.py} $D/
> cp $M/{extraer_canvas.py,banco_preguntas.py,parsear_ajustes.py} $D/
> cp $M/{parsear_distribucion.py,renumerar.py} $D/
> cp $M/index.html $D/templates/
> cp $M/{style.css,interaction.js} $D/static/
> ```

> **Por qué importa:** `templates/` y `static/` son la convención de Flask. Ponerlos donde el
> framework los espera ahorra configuración y, sobre todo, **cualquier desarrollador de Flask
> reconoce esa estructura al instante**. Seguir las convenciones del framework es una señal de
> madurez.

Los tres agentes de IA van a `libs/`, porque los usan varias apps:

> **Escribes:**
> ```bash
> mkdir -p libs/py/agentes_ia
> cp $M/agente_{semana,autoevaluacion,contextualizacion}.py libs/py/agentes_ia/
> touch libs/py/agentes_ia/__init__.py
> ```

> **Escribes:** crea `libs/py/agentes_ia/README.md` con esta advertencia:
> ```markdown
> # Agentes de IA
>
> > Los *prompts* de este directorio son **configuración aprobada
> > institucionalmente, no código**. El `SYSTEM_PROMPT` de `agente_semana.py`
> > es el texto oficial entregado por el equipo, verbatim, y no se modifica
> > sin acta de reunión.
> ```

> **Por qué importa:** distinguir *código* de *configuración aprobada* es una decisión de diseño
> real, y documentarla evita que alguien "mejore" un prompt y rompa un acuerdo institucional.

---

## Parte 11 — Migrar el generador con IA

Este es TypeScript, así que introduce Node en el monorepo.

> **Escribes:**
> ```bash
> cp -r /ruta/a/app-creacion-asignaturas/{src,public,package.json,tsconfig.json} apps/generador-guias/
> cd apps/generador-guias && npm install && cd ../..
> ```

> **Por qué importa:** ahora tu repositorio es **políglota**: Python y TypeScript conviviendo. Eso es
> normal y correcto, pero necesita una regla explícita, que vas a escribir como decisión de
> arquitectura en el paso siguiente.
>
> Verifica que `node_modules/` está en el `.gitignore` **antes** de hacer commit. Es el error número
> uno de quien empieza con Node.

---

## Parte 12 — Resolver la duplicación

Este paso es el que más demuestra criterio técnico, y sale de un hallazgo real al revisar tus
proyectos.

### Paso 12.1 — El problema

Tienes **dos extractores de Word que hacen lo mismo**:

| | `ingesta-word` | `pipeline-canvas` |
|---|---|---|
| Archivo | `pipeline_word_a_json.py` | `ingesta/docx_a_json.py` |
| Líneas | ~2.500 | 1.445 |
| Esquema | `config_canonico.json` | `esquema_canonico.schema.json` |
| Gemelo JS | Sí, con paridad verificada | No |
| Corpus de prueba | 10 guías reales | — |

Y **dos definiciones distintas del JSON canónico**. Eso significa que el JSON que produce uno puede
no ser el que espera el otro.

### Paso 12.2 — Documentar la decisión antes de tocar código

> **Escribes:** crea `docs/adr/0003-unificar-extractores.md`:
> ```markdown
> # ADR 0003 — Unificar los dos extractores de Word
>
> **Fecha:** agosto de 2026
> **Estado:** propuesto
>
> ## Contexto
>
> Existen dos extractores `.docx → JSON` desarrollados por separado, con dos
> esquemas canónicos distintos. Un JSON producido por uno no es necesariamente
> válido para el otro.
>
> ## Opciones
>
> 1. **Mantener ambos.** Coste: divergencia garantizada, doble mantenimiento.
> 2. **Quedarse con `pipeline_word_a_json.py`.** Tiene gemelo JavaScript con
>    paridad verificada y está probado sobre 10 guías reales.
> 3. **Quedarse con `docx_a_json.py`.** Está integrado en el pipeline completo
>    hasta Canvas y tiene esquema formal (`.schema.json`).
>
> ## Decisión
>
> *(Pendiente: requiere comparar la salida de ambos sobre las mismas guías.)*
>
> ## Criterio de decisión
>
> Ejecutar ambos sobre el mismo corpus de 10 guías y comparar: cobertura de
> bloques, casos límite resueltos, alertas emitidas. Gana el que más casos
> reales resuelva; el esquema formal del perdedor se adopta como contrato.
> ```

> **Por qué importa:** un **ADR** (Architecture Decision Record) es un documento corto que registra
> una decisión y su porqué. Es una práctica muy extendida y muy poco común en perfiles junior.
> Tenerlos en tu repositorio dice: *esta persona no solo programa, piensa antes y deja constancia.*
>
> Y fíjate en que el estado es "propuesto", no "aceptado". **Está bien documentar una decisión
> pendiente.** Es más honesto que fingir que ya la tomaste.

### Paso 12.3 — Medir antes de decidir

> **Escribes:** crea `tools/comparar_extractores.py` que ejecute ambos sobre las mismas guías y
> compare: número de bloques, semanas detectadas, autoevaluaciones encontradas y alertas.

> **Por qué importa:** *decidir con datos, no con intuición.* Si en una entrevista cuentas que
> resolviste una duplicación **midiendo** en vez de eligiendo la que más te gustaba, eso vale más que
> cualquier certificación.

---

## Parte 13 — Extraer bibliotecas comunes

### Paso 13.1 — Encontrar lo repetido

> **Escribes:**
> ```bash
> grep -rn "CANVAS_TOKEN\|instructure.com" --include="*.py" apps/ | cut -d: -f1 | sort | uniq -c | sort -rn
> ```

> **Qué hace:** te dice cuántos archivos hablan con Canvas.

> **Por qué importa:** vas a encontrar que `MIGRADOR`, `pipeline-canvas` y los scripts `canvas_*.py`
> tienen **tres implementaciones distintas del mismo cliente HTTP de Canvas**: tres formas de
> autenticar, tres de paginar, tres de tratar errores.

### Paso 13.2 — Un cliente único

> **Escribes:** crea `libs/py/canvas/cliente.py` con una clase que centralice: autenticación,
> paginación, reintentos ante error 429 y registro de llamadas. Después ve sustituyendo cada uso.

> **Por qué importa:** esto es **refactorización de verdad**, y el ejemplo perfecto para una
> entrevista: *"tenía tres clientes de Canvas duplicados; los unifiqué en uno con reintentos y
> control de límite de tasa, y el resto del código quedó más corto y más fiable."* Eso es una
> historia técnica concreta y verificable en tu historial de Git.
>
> Hazlo **al final y poco a poco**, sustituyendo un uso cada vez y probando. No lo hagas al principio
> ni de golpe.

---

## Parte 14 — Pruebas

No necesitas cobertura total. Necesitas **empezar**.

### Paso 14.1 — La primera prueba

> **Escribes:**
> ```bash
> mkdir -p tests
> ```
> Crea `tests/test_canon.py`:
> ```python
> """El diccionario canónico debe ser válido y completo."""
> import json
> from pathlib import Path
>
> RAIZ = Path(__file__).resolve().parents[1]
> CANON = RAIZ / "packages" / "canon" / "config_canonico.json"
>
>
> def test_canon_existe():
>     assert CANON.exists(), "Falta el diccionario canónico"
>
>
> def test_canon_es_json_valido():
>     json.loads(CANON.read_text(encoding="utf-8"))
>
>
> def test_canon_tiene_18_focalizadores():
>     datos = json.loads(CANON.read_text(encoding="utf-8"))
>     focalizadores = datos.get("focalizadores", [])
>     assert len(focalizadores) == 18, f"Se esperaban 18, hay {len(focalizadores)}"
> ```
> Ejecuta:
> ```bash
> pytest -v
> ```

> **Por qué importa:** fíjate en la tercera prueba. No comprueba código: comprueba una **regla de
> negocio** (hay 18 focalizadores). Si alguien borra uno por accidente, la prueba falla.
>
> Las pruebas más útiles no verifican que el código funcione, sino que **las reglas del negocio
> siguen siendo ciertas**.

### Paso 14.2 — La prueba de regresión que ya tienes

Tu documentación menciona una regresión sobre 10 guías reales con paridad verificada entre los dos
motores. **Eso ya es una suite de pruebas**, solo que no está formalizada.

> **Escribes:** crea `tests/test_regresion_guias.py` que, por cada guía de `datos_ejemplo/`,
> ejecute el extractor y compare contra un JSON de referencia guardado.

> **Por qué importa:** las **pruebas de regresión** (o *golden tests*) son exactamente lo que
> protege un sistema con muchos casos límite como el tuyo. Y cuando el equipo nuevo llegue y quiera
> reescribir tu extractor, esta suite es la que demuestra si su versión está a la altura o no.
>
> Dicho de otro modo: **estas pruebas son la defensa de tu trabajo.**

---

## Parte 15 — Integración continua

### Paso 15.1 — El workflow

> **Escribes:** crea `.github/workflows/ci.yml`:
> ```yaml
> name: CI
>
> on:
>   push:
>     branches: [main]
>   pull_request:
>
> jobs:
>   calidad:
>     runs-on: ubuntu-latest
>     steps:
>       - uses: actions/checkout@v4
>
>       - uses: actions/setup-python@v5
>         with:
>           python-version: "3.11"
>           cache: pip
>
>       - name: Instalar dependencias
>         run: pip install -r requirements.txt
>
>       - name: Verificar que no hay credenciales
>         run: bash tools/verificar_secretos.sh
>
>       - name: Lint
>         run: ruff check .
>
>       - name: Pruebas
>         run: pytest -q
> ```

> **Qué hace:** cada vez que subas código a GitHub, se ejecuta automáticamente en un servidor limpio:
> se instalan las dependencias, se busca credenciales, se pasa el linter y se ejecutan las pruebas.

> **Por qué importa:** dos cosas.
>
> Primero, la práctica: **CI comprueba que tu proyecto funciona en una máquina que no es la tuya.**
> El clásico "en mi equipo funciona" desaparece.
>
> Segundo, y esto es muy concreto para buscar empleo: cuando alguien abre tu repositorio en GitHub,
> ve una **insignia verde**. Es una señal inmediata de que sabes lo que es integración continua.
> Muchos candidatos junior no tienen ni un workflow.

### Paso 15.2 — La insignia

> **Escribes:** añade al principio de tu `README.md`:
> ```markdown
> ![CI](https://github.com/TU_USUARIO/plataforma-contenidos/actions/workflows/ci.yml/badge.svg)
> ```

---

## Parte 16 — Publicar y presentar

### Paso 16.1 — Última revisión de seguridad

> **Escribes:**
> ```bash
> bash tools/verificar_secretos.sh
> git log -p --all | grep -iE "sk-ant|sk-[a-zA-Z0-9]{20}|[0-9]{4}~" | head
> ```

> **Qué hace:** el segundo comando busca en **todo el historial**, no solo en los archivos actuales.

> **Por qué importa:** si aparece algo, no basta con borrar el archivo: hay que reescribir el
> historial con `git filter-repo` o BFG, y **revocar la clave igualmente**. Por eso hicimos la
> Parte 2 antes de copiar nada.

### Paso 16.2 — El README final

Tu README debe responder cinco preguntas, en este orden:

1. **¿Qué es esto?** Una frase.
2. **¿Qué problema resuelve?** Dos o tres frases con contexto real: *"la institución convierte ~900 guías Word en cursos de Canvas cada semestre; el proceso manual es caro."*
3. **¿Cómo está organizado?** La tabla de aplicaciones y el diagrama del flujo.
4. **¿Cómo lo pruebo?** `make setup` y tres comandos.
5. **¿Dónde está lo demás?** Enlaces a `docs/`.

> **Por qué importa:** el número 2 es el que casi nadie escribe, y es el que más impresiona. Un
> repositorio que explica **el problema de negocio** demuestra que entiendes para qué sirve el
> código, no solo cómo se escribe.

### Paso 16.3 — Subir a GitHub

> **Escribes:**
> ```bash
> # crea el repositorio vacío en github.com primero
> git remote add origin https://github.com/TU_USUARIO/plataforma-contenidos.git
> git push -u origin main
> ```

> **Consideración importante:** ¿repositorio público o privado? Este código es propiedad de la
> institución. **Consúltalo antes de publicarlo.** Si no puedes hacerlo público, tienes dos
> alternativas perfectamente válidas:
> - Repositorio privado, y das acceso puntual a un entrevistador.
> - Un repositorio público aparte con la **arquitectura y la documentación**, sin el código
>   propietario: los ADR, el diagrama del pipeline, el README, la estructura. Eso ya demuestra
>   criterio, y no compromete nada.

### Paso 16.4 — Cómo contarlo

Cuando te pregunten por este proyecto, tienes cuatro historias concretas. Son mucho mejores que
"hice un sistema en Python":

**1. Consolidación.** *"Unifiqué cinco sistemas desarrollados por separado, unas 30.000 líneas entre
Python, TypeScript y JavaScript, en un monorepo. Al hacerlo encontré tres implementaciones distintas
del cliente de Canvas y dos extractores de Word duplicados con esquemas incompatibles."*

**2. Seguridad.** *"Encontré credenciales en texto plano en uno de los proyectos. Las revoqué,
moví todo a variables de entorno y automaticé la detección con un hook de pre-commit y un paso de
CI, para que no dependa de que alguien se acuerde."*

**3. Decisión con datos.** *"Tenía dos extractores duplicados. En vez de elegir por intuición,
escribí un comparador que los ejecuta sobre el mismo corpus de 10 guías reales y mide cobertura y
casos límite resueltos. Documenté la decisión en un ADR."*

**4. Conocimiento en riesgo.** *"El sistema resolvía casos límite muy específicos: 59 encabezados con
`outlineLvl` oculto en el XML, 62 cuadros de texto invisibles a la extracción normal, cuatro
formatos incompatibles de autoevaluación. Todo eso existía solo dentro de condicionales. Lo extraje a
un documento de reglas de negocio para que sobreviviera a una reescritura."*

Esa última es la más valiosa, porque habla de algo que casi nadie hace: **pensar en lo que pasa con
el sistema cuando tú ya no estés.**

---

## Chuleta de comandos

```bash
# Entorno
source .venv/bin/activate          # activar
deactivate                         # salir

# Calidad
make lint                          # revisar
make format                        # formatear
make test                          # probar
make secretos                      # buscar credenciales

# Git del día a día
git status                         # qué ha cambiado
git diff                           # ver los cambios
git add <archivo>                  # preparar
git commit -m "tipo: mensaje"      # guardar
git log --oneline --graph          # ver el historial
git push                           # subir

# Rescates
git restore <archivo>              # descartar cambios no guardados
git reset --soft HEAD~1            # deshacer el último commit, conservar cambios
git stash                          # guardar temporalmente
git stash pop                      # recuperarlo
```

---

## Orden recomendado por sesiones

| Sesión | Partes | Duración |
|---|---|---|
| 1 | 0 a 3 — base y estructura | 1 h |
| 2 | 4 y 5 — entorno y calidad | 1 h |
| 3 | 6 y 7 — artefactos e ingesta | 1,5 h |
| 4 | 8 — validador | 1 h |
| 5 | 9 — pipeline Canvas (la más larga) | 2-3 h |
| 6 | 10 y 11 — migrador y generador | 1,5 h |
| 7 | 12 y 13 — duplicación y bibliotecas | 2 h |
| 8 | 14 a 16 — pruebas, CI y publicación | 2 h |

Haz una sesión por día. Al final de cada una, un commit y el README un poco más completo. En ocho
días tienes un repositorio que puedes enseñar sin dar explicaciones.
