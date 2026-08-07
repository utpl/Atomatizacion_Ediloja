# Diccionario canónico

`config_canonico.json` es el vocabulario controlado del sistema.

## Qué contiene hoy

- Los **18 focalizadores** con su rótulo. Alimentan el `enum` de
  `packages/esquemas/curso.schema.json`.
- Variantes de nomenclatura y expresiones regulares heredadas de la
  extracción de Word.

## Cambio de función (agosto 2026)

Antes servía para **reconocer** cómo escribía el docente en Word: variantes de
"Semana", "Unidad", typos reales del corpus (`APRENIZAJE`, `CONTABILIDA`) y
tolerancia difusa.

Con el agente generando JSON estructurado, esa parte ya no se usa. Lo que sigue
vigente es el catálogo de focalizadores.

Las expresiones regulares se conservan por valor histórico hasta confirmar que
no hacen falta para la migración de cursos existentes desde Canvas.

## Regla

Para añadir un focalizador nuevo se edita **este archivo y el `enum` del
esquema**, nunca el código.

## Quién lo consume

- `packages/esquemas/curso.schema.json` (los 18 focalizadores)
- `apps/pipeline-canvas/render/plantilla_config.py` (mapeo a iconos)
