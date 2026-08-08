# Siguientes pasos — P15, P16 y P12

Con esto cierras **tres** de los seis pendientes. Ninguno depende de la UTPL ni de mí.

---

## 1. Instalar (30 segundos)

```
cd ~/Desktop/App-Ediloja
unzip -o ~/Downloads/ci-docker-readme.zip -d .
ls .github/workflows/ Dockerfile.* README.md
```

**Abre el README y corrige lo que no cuadre** con tu repo real: la URL de la insignia, y
los comandos del `Makefile` si alguno tiene otro nombre.

La prueba del README, y merece la pena hacerla de verdad: **arranca el proyecto siguiendo
solo lo que está escrito**, sin usar lo que ya sabes. Si te falta un paso, al que llegue
nuevo le faltarán tres.

---

## 2. P15 — CI (5 minutos)

```
git add .github/ Dockerfile.api Dockerfile.worker README.md
git commit -m "P15+P16: CI, Dockerfiles para AWS y README"
git push
```

Entra a la pestaña **Actions** de GitHub. En un minuto tienes tick verde o rojo.

**Si sale rojo, léelo de abajo arriba** y mándame solo las últimas 15 líneas.

Los tres fallos probables:

| Fallo | Causa |
|---|---|
| `No module named 'libs'` | falta `pip install -e .` en el workflow (ya está, pero comprueba que `pyproject.toml` esté commiteado) |
| `tools/verificar_secretos.sh: not found` | el script no está en el repo o no tiene permisos |
| `ruff check .` falla | hay archivos sin lintear que el hook no vio porque nunca se commitearon |

Dejé comentado el paso de `ruff format --check`. Actívalo cuando hayas pasado
`make format` una vez sobre todo el repo — si lo dejas activo desde el principio, el
primer push sale rojo y arrancas con la insignia en rojo.

**Por qué esto importa más de lo que parece:** la insignia verde en el README dice que hay
proceso, no solo esfuerzo. En una entrevista o en una reunión donde se decide si montar un
equipo, esa señal pesa más que mil líneas de código.

---

## 3. P12 — Migrador (20 minutos, lo haces tú entero)

Sobrevive intacto: nunca dependió de Word. Es la migración de menor riesgo del proyecto.

**Primero define la ruta y verifícala.** No copies rutas literales de ningún documento:

```
export ORIGEN=~/Desktop/Automatizacion-ediloja
ls "$ORIGEN"
```

Si no lista nada, la ruta está mal. Y recuerda que la variable **no sobrevive si abres otra
terminal**.

```
ls "$ORIGEN/MIGRADOR/"
mkdir -p apps/migrador-canvas
cp -r "$ORIGEN/MIGRADOR/"* apps/migrador-canvas/
```

**Antes de commitear, comprueba dos cosas:**

```
ls apps/migrador-canvas/ | head -20
make secretos
```

Lo segundo no es opcional. En el ZIP del MIGRADOR había un
`variables_entorno.txt` con la clave de Anthropic, el token de Canvas y la de Gemini **en
texto plano**. Si eso entra al repo, entra al historial de git y ya no se borra: hay que
revocar las tres claves. Si `make secretos` avisa, **borra el archivo antes de `git add`**.

Luego, anota la deuda en `docs/03-deuda-tecnica.md`:

> `extraer_canvas.py` emite un JSON con forma propia, no el `curso.json` canónico. Hay que
> adaptarlo para que la migración desde Canvas entre por la misma puerta que el agente.

Anotarla vale más que arreglarla ahora. Deuda escrita es deuda gestionada; deuda en la
cabeza de una persona es una bomba con temporizador.

```
git add apps/migrador-canvas docs/03-deuda-tecnica.md
git commit -m "P12: migrar el MIGRADOR al monorepo, con deuda anotada"
```

---

## Lo que queda después de esto

| | Qué | Bloqueado por |
|---|---|---|
| 1 | Cola RQ + `generar` / `trabajos` | **UTPL**: proveedor y modelo |
| 2 | P11 render | necesito tus `render_*.py` |
| 3 | P13 extraer reglas y archivar | necesito `docx_a_json.py`, `etiquetar_auto.py`, `clasificar_docx.py` |

Y dos tareas sueltas de cinco minutos:

- **Cambiar la contraseña `123456`** antes de tocar AWS.
- `UniqueConstraint(codigo_banner, periodo)` en `guias` — tienes 3 "Banca" duplicadas.

Para el 2 y el 3, súbeme esos archivos en un solo mensaje y te devuelvo ambos hechos.

**El 3 tiene prisa aunque no lo parezca.** Ese código de ingesta Word es la única
documentación que existe de cómo son de verdad las guías de la UTPL: los cuatro formatos de
autoevaluación, los dos patrones de figura, y el cotejo pregunta-respuesta que **no va por
posición**. Si se archiva sin vaciarlo antes, ese conocimiento no se recupera.
