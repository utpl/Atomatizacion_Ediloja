# App-Ediloja

Monorepo con los sistemas de automatización de la producción de guías
didácticas y metacursos en Canvas LMS.

## El problema

La institución convierte cientos de guías didácticas en Word en cursos
completos de Canvas cada semestre. El proceso manual es lento y propenso a
errores. Estos sistemas lo automatizan.

## Estructura

| Carpeta | Contenido |
|---|---|
| `apps/` | Aplicaciones ejecutables |
| `packages/` | Artefactos compartidos: diccionario canónico, plantillas, esquemas |
| `libs/` | Código reutilizable entre aplicaciones |
| `docs/` | Documentación y decisiones de arquitectura |
| `tools/` | Scripts de mantenimiento del repositorio |
| `tests/` | Pruebas |
| `datos_ejemplo/` | Muestras para pruebas, sin datos personales |

## Aplicaciones

| Aplicación | Qué hace | Lenguaje |
|---|---|---|
| `ingesta-word` | Guía `.docx` → JSON canónico | Python |
| `validador-web` | Validación en el navegador, sin servidor | JavaScript |
| `pipeline-canvas` | Pipeline completo Word → JSON → Canvas | Python |
| `migrador-canvas` | Migración de metacursos 16 → N semanas | Python |
| `generador-guias` | Generación asistida por IA | TypeScript |

## Estado

En construcción. Consolidando cinco sistemas desarrollados por separado.
