# Migrador de metacursos Canvas (16 → N semanas)

Herramienta local para el equipo editorial. El revisor solo **sube el Excel de ajustes** que elaboró tras acordar los cambios con el docente (el Excel ya trae el link del curso viejo, la reubicación de temas por semana y los temas eliminados); el sistema trae el curso de Canvas, cruza los temas, deja revisar y genera el curso nuevo con la plantilla nueva — migrando imágenes, focalizadores, tablas e iframes del viejo al nuevo.

## Instalación (una vez)

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask requests python-docx openpyxl
```

Crea un archivo `.env` en la misma carpeta:

```
CANVAS_TOKEN="tu_token_de_canvas"
CANVAS_BASE="https://utpl.instructure.com"
CANVAS_ACCOUNT_ID="1"
```

El token se saca en Canvas → Cuenta → Configuración → Nuevo token de acceso.

## Uso

```bash
source venv/bin/activate
python3 app.py
```

Abre **http://localhost:5000**. Ahí el revisor:

1. Sube el **Excel de ajustes** (`Ajustes_XXXX.xlsx`). El link del curso viejo puede pegarse o dejarse vacío: se lee de la fila `URL` del Excel.
2. (Legado) También se acepta el Word de distribución del docente.
3. Pulsa **Procesar** → aparece el tablero con los temas clasificados por semana:
   - **Mantener** (verde) · **Modificar** (amarillo) · **Eliminar** (rojo: todo tema del Canvas que no aparezca en el Excel, p. ej. los de la fila "Temas eliminados") · **Contenido nuevo** (azul).
   - Cada tema muestra sus assets y un **"ver contenido Canvas"** para revisar imágenes/focalizadores.
   - Se puede **arrastrar** entre semanas o a la papelera, cambiar la acción y dejar notas.
4. Pulsa **Generar curso nuevo** → crea el curso en Canvas (páginas en **borrador**, sin publicar), copia los archivos y aplica la plantilla nueva. Al final abre el curso para revisar.

## Piezas

| Archivo | Rol |
|---|---|
| `app.py` | Backend local (Flask). Orquesta todo. |
| `index.html` | Interfaz del revisor (tablero). La sirve el backend. |
| `parsear_ajustes.py` | **Excel de ajustes del revisor → JSON** (semanas, RA, unidades, temas reubicados/eliminados; completa títulos y textos de RA desde el propio Canvas). |
| `parsear_distribucion.py` | (Legado) Word del docente → JSON (detecta resaltado = modificar). |
| `extraer_canvas.py` | Curso Canvas → JSON (páginas, quizzes, actividades). |
| `canvas_assets.py` | Inventario y migración de imágenes/focalizadores/iframes/tablas. |
| `generar_curso.py` | Construye y crea el curso nuevo. |
| `plantilla.py` | **Molde de la plantilla nueva — rellénalo.** |

## Pendiente: la plantilla nueva

`plantilla.py > render_semana()` tiene un ejemplo. Reemplázalo con la estructura real de la plantilla nueva (clases `cu-*`, menú de semana, hero, etc.). Mientras tanto, el generador usa un fallback que reusa la estructura vieja, así el pipeline ya corre completo.

Los huecos que llenará el agente IA quedan marcados en el HTML con `data-ia="contextualizacion|actividad|autoevaluacion"`.

## Seguridad

- El token vive solo en tu `.env` local, nunca llega al navegador.
- La generación crea las páginas **sin publicar** por defecto. Revísalas antes de publicar.
- Nada se borra del curso viejo: solo se lee y se copian archivos al nuevo.

## Importante: carpeta `plantilla_recursos/`

El previsualizador y el empaquetado sirven los recursos locales desde
`plantilla_recursos/`. Esa carpeta debe contener **todas** las carpetas del
metacurso, no solo `Plantilla`:

```
plantilla_recursos/
├── Plantilla/     (íconos, encabezados, focalizadores)
├── Metacurso/     (íconos de actividades evaluadas, imágenes reutilizables, documentos)
└── Contenido/     (figuras propias del curso)
```

Si falta una carpeta (p. ej. `Metacurso`), el previsualizador ahora lo avisa
en la alerta de "Revisión previa" con la lista de archivos rotos, en lugar de
mostrar imágenes vacías en silencio.
