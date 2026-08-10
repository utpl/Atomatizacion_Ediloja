# Plan de pruebas — App-EdiLoja

> Documento ejecutable. Cada apartado trae el código de la prueba y el comando
> para lanzarla. No es una lista de intenciones: es lo que hay que escribir.
>
> **Fecha:** agosto 2026 · **Contrato:** `curso.json` v1.0.0

---

## Índice

1. [Por qué ahora](#1-por-qué-ahora)
2. [Qué se prueba y qué no](#2-qué-se-prueba-y-qué-no)
3. [Preparación](#3-preparación)
4. [Nivel 1 — Unitarias, sin dependencias](#nivel-1--unitarias-sin-dependencias)
5. [Nivel 2 — Con base de datos](#nivel-2--con-base-de-datos)
6. [Nivel 3 — Con la aplicación](#nivel-3--con-la-aplicación)
7. [Nivel 4 — Flujo completo con modelo simulado](#nivel-4--flujo-completo-con-modelo-simulado)
8. [Nivel 5 — Contra Canvas real](#nivel-5--contra-canvas-real)
9. [Lista de comprobación manual](#9-lista-de-comprobación-manual)
10. [Cómo se ejecuta todo](#10-cómo-se-ejecuta-todo)
11. [Los diez fallos que ya ocurrieron](#11-los-diez-fallos-que-ya-ocurrieron)

---

## 1. Por qué ahora

El proyecto tiene siete capas encadenadas: formulario → agente → `curso.json` →
editor → adaptador → plantilla → Canvas. Cada una se comprueba hoy **a mano**,
mirando una pantalla.

Eso ya es el cuello de botella. Durante el desarrollo aparecieron fallos que
solo se vieron tres capas más abajo: un campo que el modelo escribe con otro
nombre, una ruta relativa que se resuelve distinto según desde dónde arranques,
una regla duplicada en dos archivos que se desincronizó. Todos habrían saltado
en un segundo con una prueba.

**El objetivo no es cobertura.** Es poder tocar el código sin miedo, que es lo
que hace falta para el mes de trabajo que viene.

---

## 2. Qué se prueba y qué no

### Se prueba

| Qué | Por qué |
|---|---|
| Los contratos entre capas | Es donde han estado todos los fallos |
| Las reglas de negocio | 8 o 16 semanas, 10 preguntas, cuotas, roles |
| Los permisos | Un fallo aquí expone datos ajenos |
| Las conversiones | Normalizador, adaptador, analizador de HTML |
| El ciclo de vida | Congelado, aprobación, concurrencia |

### No se prueba, a propósito

**La calidad pedagógica del texto generado.** No es automatizable y no es
tuya: la juzga Diseño Instruccional.

**El aspecto visual.** Una prueba que compare píxeles se rompe con cada cambio
de CSS y no dice nada útil. Se comprueba con la lista manual del apartado 9.

**Los scripts heredados del pipeline.** Son 2000 líneas que funcionan contra
Canvas real. Se prueba lo que se les pasa y lo que devuelven, no su interior.

**La API de Canvas.** No es tuya. Se simula en las pruebas y se comprueba de
verdad solo en el nivel 5.

---

## 3. Preparación

### Dependencias

```bash
cd /Users/santiago/Desktop/App-Ediloja
pip install pytest pytest-cov
```

### Estructura

```bash
mkdir -p tests/{unitarias,integracion,extremo}
touch tests/__init__.py tests/unitarias/__init__.py \
      tests/integracion/__init__.py tests/extremo/__init__.py
ls tests/
```

Ojo: ya existe una carpeta `tests/`. Míra qué hay antes de escribir encima:

```bash
find tests -name "*.py" | head -20
```

### Configuración de pytest

`pyproject.toml`, añadir al final:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
markers = [
    "bd: necesita PostgreSQL levantado",
    "canvas: llama a Canvas de verdad; no se ejecuta en CI",
    "lento: tarda más de 5 segundos",
]
addopts = "-q --strict-markers"
```

`--strict-markers` obliga a declarar los marcadores. Sin eso, un marcador mal
escrito se ignora en silencio y la prueba se ejecuta cuando no debía.

### Fixtures compartidas

`tests/conftest.py`:

```python
"""Fixtures compartidas.

Los `curso.json` de prueba se construyen aquí y no se leen de
datos_ejemplo/fixtures: un fixture en disco cambia cuando alguien regenera y
las pruebas empiezan a fallar por motivos que no son el código.
"""
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def esquema():
    ruta = RAIZ / "packages" / "esquemas" / "curso.schema.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


@pytest.fixture
def curso_minimo():
    """El curso.json más pequeño que valida. Base para los demás."""
    return {
        "version_esquema": "1.0.0",
        "info_general": {
            "codigo_banner": "TEST101",
            "asignatura": "Asignatura de prueba",
            "periodo": "2026-1",
            "total_semanas": 8,
        },
        "estructura": {
            "resultados_aprendizaje": [
                {"id": "ra1", "numero": 1,
                 "texto": "Aplica los fundamentos de la materia en casos reales."}
            ],
            "unidades": [
                {"id": "u1", "numero": 1, "titulo": "Unidad de prueba",
                 "resultado_aprendizaje_id": "ra1",
                 "semana_inicio": 1, "semana_fin": 8}
            ],
            "paginas": [
                {"id": f"p{n}", "semana": n, "titulo": f"Semana {n}",
                 "unidad_id": "u1", "bloques": [
                     {"id": f"benc{n:03d}a", "tipo": "encabezado",
                      "nivel": 2, "texto": "Contenidos", "origen": "agente"},
                     {"id": f"bpar{n:03d}a", "tipo": "parrafo",
                      "texto": "Texto de la semana.", "origen": "agente"},
                 ]}
                for n in range(1, 9)
            ],
        },
        "finales": {
            "referencias": [
                {"id": "ref1", "apa": "Autor, A. (2020). Título de prueba. Editorial."}
            ]
        },
    }


@pytest.fixture
def pagina_todos_los_tipos():
    """Una página con los doce tipos de bloque. El caso que más rompe."""
    return {
        "id": "p1", "semana": 1, "titulo": "Semana 1",
        "unidad_id": "u1", "cierra_unidad": True,
        "bloques": [
            {"id": "b000001", "tipo": "encabezado", "nivel": 2, "texto": "Título"},
            {"id": "b000002", "tipo": "parrafo",
             "texto": "Texto con <strong>negrita</strong>."},
            {"id": "b000003", "tipo": "lista", "ordenada": False,
             "items": [{"texto": "Uno"},
                       {"texto": "Dos", "items": [{"texto": "Dos punto uno"}]}]},
            {"id": "b000004", "tipo": "tabla", "titulo": "Tabla 1",
             "encabezados": ["A", "B"], "filas": [["1", "2"], ["3", "4"]]},
            {"id": "b000005", "tipo": "caja", "titulo": "Aviso",
             "bloques": [{"id": "b000006", "tipo": "parrafo", "texto": "Dentro."}]},
            {"id": "b000007", "tipo": "focalizador", "focalizador": "recuerde",
             "bloques": [{"id": "b000008", "tipo": "parrafo", "texto": "Repase."}]},
            {"id": "b000009", "tipo": "cita", "texto": "Frase citada.",
             "referencia_id": "ref1", "pagina_citada": "p. 45"},
            {"id": "b000010", "tipo": "imagen", "recurso_ref": "r1",
             "alt": "Descripción", "numero_figura": 1},
            {"id": "b000011", "tipo": "diagrama", "recurso_ref": "r2",
             "alt": "Esquema", "numero_figura": 2},
            {"id": "b000012", "tipo": "recurso_ediloja",
             "titulo": "Videoclase", "url": "https://ejemplo.org/v"},
            {"id": "b000013", "tipo": "actividades",
             "titulo": "Actividades", "texto": "Participe en el foro."},
            {"id": "b000014", "tipo": "autoevaluacion", "preguntas": [
                {"id": f"q{i}", "numero": i,
                 "enunciado": f"Pregunta {i} de la autoevaluación",
                 "opciones": [{"letra": "a", "texto": "A"},
                              {"letra": "b", "texto": "B"}],
                 "correcta": "a", "retroalimentacion": "Porque sí."}
                for i in range(1, 11)
            ]},
        ],
    }


@pytest.fixture
def respuesta_modelo():
    """Fabrica una RespuestaModelo con el JSON que se le indique."""
    from libs.py.agente.cliente import RespuestaModelo

    def _fabricar(datos, tokens_entrada=100, tokens_salida=200):
        texto = datos if isinstance(datos, str) else json.dumps(datos, ensure_ascii=False)
        return RespuestaModelo(texto=texto, tokens_entrada=tokens_entrada,
                               tokens_salida=tokens_salida)

    return _fabricar
```

---

## Nivel 1 — Unitarias, sin dependencias

Sin base de datos, sin red, sin Canvas. Deben tardar **menos de dos segundos
en total**. Son las que se ejecutan constantemente mientras se programa.

### 1.1 El esquema y sus reglas

`tests/unitarias/test_esquema.py`:

```python
"""El esquema es el contrato central: si cede, cede todo lo demás."""
import copy

import jsonschema
import pytest


def validador(esquema):
    return jsonschema.Draft202012Validator(esquema)


def test_curso_minimo_valida(esquema, curso_minimo):
    assert list(validador(esquema).iter_errors(curso_minimo)) == []


def test_pagina_con_los_doce_tipos_valida(esquema, curso_minimo, pagina_todos_los_tipos):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0] = pagina_todos_los_tipos
    curso["recursos"] = [
        {"ref": "r1", "tipo": "imagen", "archivo": "r1.png", "mime": "image/png"},
        {"ref": "r2", "tipo": "diagrama", "archivo": "r2.svg", "mime": "image/svg+xml"},
    ]
    errores = list(validador(esquema).iter_errors(curso))
    assert errores == [], [e.message for e in errores[:3]]


@pytest.mark.parametrize("semanas", [0, 1, 4, 12, 20])
def test_total_semanas_solo_admite_8_o_16(esquema, curso_minimo, semanas):
    curso = copy.deepcopy(curso_minimo)
    curso["info_general"]["total_semanas"] = semanas
    assert list(validador(esquema).iter_errors(curso)) != []


def test_campo_de_mas_rechaza_el_documento_entero(esquema, curso_minimo):
    """additionalProperties: false no ignora el campo, tumba el documento."""
    curso = copy.deepcopy(curso_minimo)
    curso["campo_inventado"] = True
    assert list(validador(esquema).iter_errors(curso)) != []


def test_campo_de_mas_en_un_bloque_tambien_rechaza(esquema, curso_minimo):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0]["bloques"][0]["estilo"] = "negrita"
    assert list(validador(esquema).iter_errors(curso)) != []


@pytest.mark.parametrize("id_bloque", ["b123", "B123456", "1234567", "b-123456"])
def test_id_de_bloque_debe_seguir_el_patron(esquema, curso_minimo, id_bloque):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0]["bloques"][0]["id"] = id_bloque
    assert list(validador(esquema).iter_errors(curso)) != []


def test_focalizador_exige_hijos(esquema, curso_minimo):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0]["bloques"] = [
        {"id": "bfoc001", "tipo": "focalizador", "focalizador": "recuerde"}
    ]
    assert list(validador(esquema).iter_errors(curso)) != []


def test_focalizador_fuera_del_enum_no_valida(esquema, curso_minimo):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0]["bloques"] = [
        {"id": "bfoc001", "tipo": "focalizador", "focalizador": "inventado",
         "bloques": [{"id": "bfoch01", "tipo": "parrafo", "texto": "x"}]}
    ]
    assert list(validador(esquema).iter_errors(curso)) != []


def test_un_bloque_hoja_no_puede_anidar(esquema, curso_minimo):
    """Solo caja y focalizador anidan, y solo un nivel."""
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0]["bloques"] = [
        {"id": "bpar001", "tipo": "parrafo", "texto": "x",
         "bloques": [{"id": "bpar002", "tipo": "parrafo", "texto": "y"}]}
    ]
    assert list(validador(esquema).iter_errors(curso)) != []
```

### 1.2 El validador de reglas de negocio

`tests/unitarias/test_validador.py`:

```python
"""Las siete reglas institucionales y el semáforo."""
import copy

from libs.py.esquema.validador import validar


def codigos(resultado):
    return {a["codigo"] for a in resultado.como_dict()["alertas"]}


def test_curso_correcto_da_verde(curso_minimo):
    assert validar(curso_minimo).semaforo == "verde"


def test_semanas_incompletas_es_error(curso_minimo):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"] = curso["estructura"]["paginas"][:5]
    r = validar(curso)
    assert r.semaforo == "rojo"
    assert "semanas_incompletas" in codigos(r)


def test_semanas_desordenadas_es_error(curso_minimo):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][3]["semana"] = 9
    r = validar(curso)
    assert "semanas_desordenadas" in codigos(r)


def test_cita_a_referencia_inexistente_es_error(curso_minimo):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0]["bloques"].append(
        {"id": "bcit001", "tipo": "cita", "texto": "Frase.",
         "referencia_id": "ref99"})
    r = validar(curso)
    assert r.semaforo == "rojo"
    assert "cita_sin_referencia" in codigos(r)


def test_cierra_unidad_sin_autoevaluacion_es_error(curso_minimo):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][7]["cierra_unidad"] = True
    r = validar(curso)
    assert "falta_autoevaluacion" in codigos(r)


def test_autoevaluacion_con_menos_de_diez_es_aviso(curso_minimo, pagina_todos_los_tipos):
    """Aviso, no error: es criterio editorial, no un fallo estructural."""
    curso = copy.deepcopy(curso_minimo)
    pagina = copy.deepcopy(pagina_todos_los_tipos)
    autoev = [b for b in pagina["bloques"] if b["tipo"] == "autoevaluacion"][0]
    autoev["preguntas"] = autoev["preguntas"][:3]
    curso["estructura"]["paginas"][0] = pagina
    curso["recursos"] = [
        {"ref": "r1", "tipo": "imagen", "archivo": "r1.png", "mime": "image/png"},
        {"ref": "r2", "tipo": "diagrama", "archivo": "r2.svg", "mime": "image/svg+xml"},
    ]
    r = validar(curso)
    assert r.semaforo == "amarillo"
    assert "autoevaluacion_incompleta" in codigos(r)


def test_imagen_sin_alt_es_aviso(curso_minimo):
    curso = copy.deepcopy(curso_minimo)
    curso["recursos"] = [{"ref": "r1", "tipo": "imagen",
                          "archivo": "r1.png", "mime": "image/png"}]
    curso["estructura"]["paginas"][0]["bloques"].append(
        {"id": "bimg001", "tipo": "imagen", "recurso_ref": "r1"})
    r = validar(curso)
    assert r.semaforo == "amarillo"
    assert "falta_texto_alternativo" in codigos(r)


def test_imagen_decorativa_sin_alt_no_avisa(curso_minimo):
    curso = copy.deepcopy(curso_minimo)
    curso["recursos"] = [{"ref": "r1", "tipo": "imagen",
                          "archivo": "r1.png", "mime": "image/png"}]
    curso["estructura"]["paginas"][0]["bloques"].append(
        {"id": "bimg001", "tipo": "imagen", "recurso_ref": "r1", "decorativa": True})
    assert "falta_texto_alternativo" not in codigos(validar(curso))


def test_el_codigo_de_alerta_es_estable(curso_minimo):
    """Se filtra por código, nunca por el texto del mensaje."""
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"] = curso["estructura"]["paginas"][:3]
    for alerta in validar(curso).como_dict()["alertas"]:
        assert alerta["codigo"].replace("_", "").isalnum()
        assert alerta["nivel"] in ("error", "aviso")
```

### 1.3 El normalizador

`tests/unitarias/test_normalizar.py`:

```python
"""Traduce las variantes que produce el modelo. Cada caso aquí es un fallo
que ya ocurrió en una generación real."""
from libs.py.agente.normalizar import normalizar_bloque, normalizar_pagina


def test_contenido_se_traduce_a_bloques():
    b = normalizar_bloque({"tipo": "focalizador", "focalizador": "recuerde",
                           "contenido": [{"tipo": "parrafo", "texto": "x"}]})
    assert "bloques" in b and "contenido" not in b
    assert b["bloques"][0]["texto"] == "x"


def test_items_de_cadenas_se_convierten_en_objetos():
    b = normalizar_bloque({"tipo": "lista", "items": ["uno", "dos"]})
    assert b["items"] == [{"texto": "uno"}, {"texto": "dos"}]


def test_elementos_es_sinonimo_de_items():
    b = normalizar_bloque({"tipo": "lista", "elementos": ["uno"]})
    assert b["items"] == [{"texto": "uno"}]


def test_nivel_cinco_se_recorta_a_cuatro():
    assert normalizar_bloque({"tipo": "encabezado", "nivel": 5,
                              "texto": "x"})["nivel"] == 4


def test_claves_descartadas_desaparecen():
    b = normalizar_bloque({"tipo": "parrafo", "texto": "x", "estilo": "negrita"})
    assert "estilo" not in b


def test_pregunta_y_respuestacorrecta_se_renombran():
    b = normalizar_bloque({"tipo": "autoevaluacion", "preguntas": [
        {"pregunta": "¿Y?", "opciones": ["A", "B"], "respuestaCorrecta": "A"}]})
    p = b["preguntas"][0]
    assert p["enunciado"] == "¿Y?"
    assert p["correcta"] == "a"
    assert p["opciones"] == [{"letra": "a", "texto": "A"},
                             {"letra": "b", "texto": "B"}]


def test_correcta_como_indice_base_uno():
    b = normalizar_bloque({"tipo": "autoevaluacion", "preguntas": [
        {"enunciado": "x", "opciones": ["A", "B", "C"], "correcta": "2"}]})
    assert b["preguntas"][0]["correcta"] == "b"


def test_correcta_como_texto_de_la_opcion():
    b = normalizar_bloque({"tipo": "autoevaluacion", "preguntas": [
        {"enunciado": "x", "opciones": ["Sí", "No"], "correcta": "No"}]})
    assert b["preguntas"][0]["correcta"] == "b"


def test_recurso_sin_url_se_degrada_a_parrafo():
    """Sin url no valida y no hay forma de inventarla: mejor perder el
    formato que el contenido."""
    b = normalizar_bloque({"tipo": "recurso_ediloja", "titulo": "T",
                           "texto": "Descripción", "descripcion": "x"})
    assert b["tipo"] == "parrafo"
    assert "Descripción" in b["texto"]


def test_lo_que_ya_es_canonico_no_cambia():
    original = {"tipo": "parrafo", "texto": "x", "id": "b123456", "origen": "agente"}
    assert normalizar_bloque(dict(original)) == original


def test_normalizar_pagina_recorre_los_bloques():
    p = normalizar_pagina({"id": "p1", "semana": 1, "bloques": [
        {"tipo": "lista", "items": ["a"]}]})
    assert p["bloques"][0]["items"] == [{"texto": "a"}]
```

### 1.4 Unidades y plan de semanas

`tests/unitarias/test_unidades.py`:

```python
"""El reparto de semanas decide dónde va cada autoevaluación."""
import pytest

from libs.py.agente.unidades import (
    ErrorDeUnidades,
    extraer_unidades,
    plan_desde_unidades,
)


def llamador_que_devuelve(datos, respuesta_modelo):
    def _llamar(instrucciones, contenido):
        return respuesta_modelo(datos)
    return _llamar


def test_extrae_las_unidades_y_les_pone_id(respuesta_modelo):
    llamador = llamador_que_devuelve({"unidades": [
        {"numero": 1, "titulo": "Primera", "semana_inicio": 1, "semana_fin": 4},
        {"numero": 2, "titulo": "Segunda", "semana_inicio": 5, "semana_fin": 8},
    ]}, respuesta_modelo)
    unidades = extraer_unidades("temario", 8, llamador)
    assert [u["id"] for u in unidades] == ["u1", "u2"]


def test_rechaza_si_quedan_semanas_sin_unidad(respuesta_modelo):
    """Un hueco deja una semana sin resultado de aprendizaje y sin saber si
    cierra unidad."""
    llamador = llamador_que_devuelve({"unidades": [
        {"numero": 1, "titulo": "Única", "semana_inicio": 1, "semana_fin": 5},
    ]}, respuesta_modelo)
    with pytest.raises(ErrorDeUnidades, match="sin unidad"):
        extraer_unidades("temario", 8, llamador, intentos=1)


def test_rechaza_unidad_fuera_de_rango(respuesta_modelo):
    llamador = llamador_que_devuelve({"unidades": [
        {"numero": 1, "titulo": "Única", "semana_inicio": 1, "semana_fin": 12},
    ]}, respuesta_modelo)
    with pytest.raises(ErrorDeUnidades):
        extraer_unidades("temario", 8, llamador, intentos=1)


def test_rechaza_unidad_sin_titulo(respuesta_modelo):
    llamador = llamador_que_devuelve({"unidades": [
        {"numero": 1, "titulo": "", "semana_inicio": 1, "semana_fin": 8},
    ]}, respuesta_modelo)
    with pytest.raises(ErrorDeUnidades):
        extraer_unidades("temario", 8, llamador, intentos=1)


def test_reintenta_antes_de_rendirse(respuesta_modelo):
    intentos = {"n": 0}

    def llamador(instrucciones, contenido):
        intentos["n"] += 1
        if intentos["n"] < 3:
            return respuesta_modelo("esto no es JSON")
        return respuesta_modelo({"unidades": [
            {"numero": 1, "titulo": "Única", "semana_inicio": 1, "semana_fin": 8}]})

    assert len(extraer_unidades("temario", 8, llamador)) == 1
    assert intentos["n"] == 3


def test_el_plan_marca_cierra_unidad_en_la_ultima_semana():
    unidades = [
        {"id": "u1", "numero": 1, "titulo": "A", "semana_inicio": 1, "semana_fin": 4},
        {"id": "u2", "numero": 2, "titulo": "B", "semana_inicio": 5, "semana_fin": 8},
    ]
    plan = plan_desde_unidades(unidades)
    cierran = [p["semana"] for p in plan if p["cierra_unidad"]]
    assert cierran == [4, 8]


def test_el_plan_lleva_unidad_id():
    """generar_guia lee paso['unidad_id']; sin él las páginas salen sueltas."""
    unidades = [{"id": "u1", "numero": 1, "titulo": "A",
                 "semana_inicio": 1, "semana_fin": 2}]
    for paso in plan_desde_unidades(unidades):
        assert paso["unidad_id"] == "u1"


def test_el_plan_cubre_todas_las_semanas_en_orden():
    unidades = [
        {"id": "u1", "numero": 1, "titulo": "A", "semana_inicio": 1, "semana_fin": 3},
        {"id": "u2", "numero": 2, "titulo": "B", "semana_inicio": 4, "semana_fin": 8},
    ]
    plan = plan_desde_unidades(unidades)
    assert [p["semana"] for p in plan] == list(range(1, 9))
```

### 1.5 El prompt

`tests/unitarias/test_prompt.py`:

```python
"""El prompt es un contrato con el modelo. Si pierde una regla, la guía sale
mal y nadie sabe por qué."""
from libs.py.agente.prompt import (
    ETIQUETAS_INLINE,
    FOCALIZADORES,
    PROMPT_FORMATO,
    PROMPT_INSTITUCIONAL,
    TIPOS_DE_BLOQUE,
    construir_instrucciones,
)


def test_el_prompt_institucional_no_esta_vacio():
    assert "PENDIENTE" not in PROMPT_INSTITUCIONAL
    assert len(PROMPT_INSTITUCIONAL) > 500


def test_conserva_las_diez_reglas_obligatorias():
    for n in range(1, 11):
        assert f"{n}." in PROMPT_INSTITUCIONAL


def test_conserva_las_reglas_que_mas_importan():
    texto = PROMPT_INSTITUCIONAL.lower()
    for regla in ["no inventes", "apa 7", "et al", "diez preguntas", "tuteo"]:
        assert regla in texto, f"falta la regla: {regla}"


def test_hay_dieciocho_focalizadores():
    assert len(FOCALIZADORES) == 18
    assert len(set(FOCALIZADORES)) == 18


def test_hay_doce_tipos_de_bloque():
    assert len(TIPOS_DE_BLOQUE) == 12


def test_el_formato_menciona_los_doce_tipos():
    for tipo in TIPOS_DE_BLOQUE:
        assert tipo in PROMPT_FORMATO


def test_el_formato_avisa_de_los_errores_conocidos():
    """Cada NUNCA corresponde a un fallo real de una generación."""
    for aviso in ['NUNCA en "contenido"', '"enunciado"', 'url" es OBLIGATORIA']:
        assert aviso in PROMPT_FORMATO


def test_el_formato_declara_el_marcado_permitido():
    for etiqueta in ETIQUETAS_INLINE:
        assert f"<{etiqueta}>" in PROMPT_FORMATO


def test_las_dos_capas_van_separadas():
    completo = construir_instrucciones()
    assert PROMPT_INSTITUCIONAL in completo
    assert PROMPT_FORMATO in completo
    assert completo.index(PROMPT_INSTITUCIONAL) < completo.index(PROMPT_FORMATO)


def test_se_puede_inyectar_otro_institucional():
    completo = construir_instrucciones("TEXTO DE PRUEBA")
    assert "TEXTO DE PRUEBA" in completo
    assert PROMPT_INSTITUCIONAL not in completo
```

### 1.6 El ensamblado

`tests/unitarias/test_ensamblado.py`:

```python
"""El modelo genera contenido; el código lleva la contabilidad."""
import re

from libs.py.agente import ensamblado


def test_los_id_siguen_el_patron_del_esquema():
    for _ in range(50):
        assert re.match(r"^b[0-9a-z]{6,}$", ensamblado.nuevo_id_bloque())


def test_los_id_no_se_repiten():
    ids = {ensamblado.nuevo_id_bloque() for _ in range(1000)}
    assert len(ids) == 1000


def test_poner_ids_respeta_los_que_ya_existen():
    bloques = [{"tipo": "parrafo", "texto": "x", "id": "byaexiste1"},
               {"tipo": "parrafo", "texto": "y"}]
    ensamblado.poner_ids_y_origen(bloques, origen="agente")
    assert bloques[0]["id"] == "byaexiste1"
    assert bloques[1]["id"] != "byaexiste1"


def test_poner_ids_baja_a_los_hijos():
    bloques = [{"tipo": "focalizador", "focalizador": "recuerde",
                "bloques": [{"tipo": "parrafo", "texto": "x"}]}]
    ensamblado.poner_ids_y_origen(bloques, origen="agente")
    assert "id" in bloques[0]["bloques"][0]
    assert bloques[0]["bloques"][0]["origen"] == "agente"


def test_las_paginas_estan_en_estructura(curso_minimo):
    assert len(ensamblado.paginas_de(curso_minimo)) == 8


def test_los_hijos_solo_en_contenedores():
    assert ensamblado.hijos_de({"tipo": "parrafo", "bloques": [{}]}) is None
    assert ensamblado.hijos_de({"tipo": "caja", "bloques": [{"tipo": "parrafo"}]}) is not None
```

### 1.7 Las operaciones de edición

`tests/unitarias/test_edicion.py`:

```python
"""Ocho operaciones con nombre. Cada una se audita y se deshace."""
import copy

import pytest

from libs.py.edicion.esquemas import (
    ActualizarBloque,
    EliminarBloque,
    InsertarBloque,
    MoverBloque,
)
from libs.py.edicion.operaciones import ErrorDeEdicion, aplicar


def test_actualizar_bloque_cambia_el_texto(curso_minimo):
    op = ActualizarBloque(bloque_id="bpar001a", campos={"texto": "Nuevo"})
    curso, registros = aplicar(copy.deepcopy(curso_minimo), [op])
    bloque = curso["estructura"]["paginas"][0]["bloques"][1]
    assert bloque["texto"] == "Nuevo"
    assert len(registros) == 1


def test_editar_un_bloque_del_agente_lo_pasa_a_mixto(curso_minimo):
    """Alimenta estadisticas.por_origen, que es la métrica de si el agente
    está mejorando."""
    op = ActualizarBloque(bloque_id="bpar001a", campos={"texto": "Nuevo"})
    curso, _ = aplicar(copy.deepcopy(curso_minimo), [op])
    assert curso["estructura"]["paginas"][0]["bloques"][1]["origen"] == "mixto"


def test_el_registro_guarda_el_antes_y_el_despues(curso_minimo):
    op = ActualizarBloque(bloque_id="bpar001a", campos={"texto": "Nuevo"})
    _, registros = aplicar(copy.deepcopy(curso_minimo), [op])
    assert registros[0]["antes"]["texto"] != registros[0]["despues"]["texto"]


def test_eliminar_un_bloque_inexistente_falla_con_su_id(curso_minimo):
    with pytest.raises(ErrorDeEdicion, match="bnoexiste"):
        aplicar(copy.deepcopy(curso_minimo), [EliminarBloque(bloque_id="bnoexiste")])


def test_el_lote_es_todo_o_nada(curso_minimo):
    """Si la tercera falla, las dos primeras tampoco se aplican."""
    original = copy.deepcopy(curso_minimo)
    operaciones = [
        ActualizarBloque(bloque_id="bpar001a", campos={"texto": "A"}),
        ActualizarBloque(bloque_id="bpar002a", campos={"texto": "B"}),
        EliminarBloque(bloque_id="bnoexiste"),
    ]
    with pytest.raises(ErrorDeEdicion):
        aplicar(original, operaciones)
    assert original["estructura"]["paginas"][0]["bloques"][1]["texto"] != "A"


def test_marcado_no_permitido_se_rechaza(curso_minimo):
    """El backend devuelve 422: un editor enriquecido que meta <div> falla."""
    op = ActualizarBloque(bloque_id="bpar001a",
                          campos={"texto": "<div>malo</div>"})
    with pytest.raises(ErrorDeEdicion):
        aplicar(copy.deepcopy(curso_minimo), [op])


def test_marcado_permitido_se_acepta(curso_minimo):
    op = ActualizarBloque(
        bloque_id="bpar001a",
        campos={"texto": "<strong>a</strong> <em>b</em> <a href='#'>c</a><br>"})
    curso, _ = aplicar(copy.deepcopy(curso_minimo), [op])
    assert "<strong>" in curso["estructura"]["paginas"][0]["bloques"][1]["texto"]


def test_insertar_bloque_le_pone_id_y_origen_docente(curso_minimo):
    op = InsertarBloque(pagina_id="p1", indice=0,
                        bloque={"tipo": "parrafo", "texto": "Nuevo"})
    curso, _ = aplicar(copy.deepcopy(curso_minimo), [op])
    nuevo = curso["estructura"]["paginas"][0]["bloques"][0]
    assert nuevo["origen"] == "docente"
    assert nuevo["id"].startswith("b")


def test_mover_bloque_usa_el_indice_sobre_la_lista_final(curso_minimo):
    """No se resta uno al arrastrar hacia abajo: es donde viven los bugs."""
    op = MoverBloque(bloque_id="benc001a", pagina_id="p1", indice=1)
    curso, _ = aplicar(copy.deepcopy(curso_minimo), [op])
    assert curso["estructura"]["paginas"][0]["bloques"][1]["id"] == "benc001a"
```

### 1.8 El adaptador al esquema canónico

`tests/unitarias/test_adaptador.py`:

```python
"""Traduce curso.json al formato que consume el pipeline de publicación."""
import copy
import json
from pathlib import Path

import jsonschema
import pytest

from libs.py.publicacion.adaptador_canonico import _a_markdown, convertir

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture
def esquema_canonico():
    ruta = RAIZ / "packages" / "esquemas" / "esquema_canonico.schema.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def test_la_salida_valida_contra_el_esquema_canonico(
        esquema_canonico, curso_minimo, pagina_todos_los_tipos):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0] = pagina_todos_los_tipos
    salida = convertir(curso)
    errores = list(jsonschema.Draft202012Validator(esquema_canonico).iter_errors(salida))
    assert errores == [], [e.message for e in errores[:3]]


def test_las_autoevaluaciones_salen_como_seccion(curso_minimo, pagina_todos_los_tipos):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0] = pagina_todos_los_tipos
    tipos = [s["tipo"] for s in convertir(curso)["secciones"]]
    assert "autoevaluacion" in tipos


def test_el_resultado_de_aprendizaje_va_en_ras_globales_curados(curso_minimo):
    """render_ed no lee el bloque: los busca en esa clave."""
    salida = convertir(curso_minimo)
    ras = salida["ras_globales_curados"]
    assert ras and ras[0]["unidad_aplica"] == 1
    assert "fundamentos" in ras[0]["ra"].lower()


def test_la_contextualizacion_viaja_en_contextualizacion_final(curso_minimo):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["unidades"][0]["contextualizacion"] = "Texto largo " * 10
    ras = convertir(curso)["ras_globales_curados"]
    assert ras[0]["contextualizacion_final"].startswith("Texto largo")


def test_html_se_convierte_a_markdown():
    """md_inline() del pipeline escapa antes de traducir: un <strong> llegaría
    a Canvas como texto literal."""
    assert _a_markdown("<strong>a</strong>") == "**a**"
    assert _a_markdown("<em>a</em>") == "*a*"
    assert _a_markdown('<a href="http://x">y</a>') == "[y](http://x)"


def test_la_caja_se_aplana_conservando_el_contenido(curso_minimo):
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0]["bloques"] = [
        {"id": "bcaj001", "tipo": "caja", "titulo": "Aviso",
         "bloques": [{"id": "bcajh01", "tipo": "parrafo", "texto": "Dentro."}]}]
    bloques = convertir(curso)["secciones"][0]["unidades"][0]["bloques"]
    textos = json.dumps(bloques, ensure_ascii=False)
    assert "Dentro." in textos
    assert "Aviso" in textos


def test_los_apartados_del_prompt_no_acaban_como_pestanas(curso_minimo):
    """El modelo emite los siete apartados como encabezados; el resultado de
    aprendizaje y la contextualización ya se muestran arriba."""
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0]["bloques"] = [
        {"id": "benc001", "tipo": "encabezado", "nivel": 2,
         "texto": "Resultado de aprendizaje"},
        {"id": "bpar001", "tipo": "parrafo", "texto": "No debe salir."},
        {"id": "benc002", "tipo": "encabezado", "nivel": 2,
         "texto": "Desarrollo de contenidos"},
        {"id": "benc003", "tipo": "encabezado", "nivel": 3, "texto": "1.1. Tema real"},
        {"id": "bpar002", "tipo": "parrafo", "texto": "Contenido."},
    ]
    bloques = convertir(curso)["secciones"][0]["unidades"][0]["bloques"]
    titulos = [b["texto"] for b in bloques
               if b["tipo"] == "subtitulo" and b.get("nivel", 2) <= 2]
    assert not any("Resultado de aprendizaje" in t for t in titulos)
    assert any("Tema real" in t for t in titulos)


def test_la_jerarquia_sale_de_la_numeracion(curso_minimo):
    """'1.2. Objetivos' es tema; 'Objetivos de aseguramiento' es subapartado.
    El modelo los emite al mismo nivel."""
    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["paginas"][0]["bloques"] = [
        {"id": "benc001", "tipo": "encabezado", "nivel": 2,
         "texto": "Desarrollo de contenidos"},
        {"id": "benc002", "tipo": "encabezado", "nivel": 3, "texto": "1.2. Objetivos"},
        {"id": "benc003", "tipo": "encabezado", "nivel": 3,
         "texto": "Objetivos de aseguramiento"},
    ]
    bloques = convertir(curso)["secciones"][0]["unidades"][0]["bloques"]
    por_texto = {b["texto"]: b.get("nivel") for b in bloques if b["tipo"] == "subtitulo"}
    assert por_texto.get("Objetivos") == 2
    assert por_texto.get("Objetivos de aseguramiento") == 3
```

### 1.9 El analizador de HTML (migración)

`tests/unitarias/test_html_a_bloques.py`:

```python
"""Convierte el HTML de un curso migrado en bloques."""
from libs.py.publicacion.html_a_bloques import _inline, pagina_desde_html


def html_de(cuerpo):
    return f'<div class="ed-container"><section class="content">{cuerpo}</section></div>'


def test_el_focalizador_conserva_su_tipo():
    html = html_de(
        '<div class="ctab__panel"><div class="focuser reflection">'
        '<div class="content-focuser"><p>Reflexione.</p></div></div></div>')
    p = pagina_desde_html(html, 1, "u1", [])
    foc = [b for b in p["bloques"] if b["tipo"] == "focalizador"]
    assert foc and foc[0]["focalizador"] == "reflexione"


def test_la_tabla_se_convierte_con_encabezados_y_filas():
    html = html_de(
        '<div class="ctab__panel"><table class="table-general">'
        "<thead><tr><th>A</th><th>B</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr></tbody></table></div>")
    p = pagina_desde_html(html, 1, "u1", [])
    tabla = [b for b in p["bloques"] if b["tipo"] == "tabla"][0]
    assert tabla["encabezados"] == ["A", "B"]
    assert tabla["filas"] == [["1", "2"]]


def test_la_figura_crea_su_entrada_en_recursos():
    recursos = []
    html = html_de(
        '<div class="ctab__panel"><figure class="container-figure">'
        '<p><img src="https://x/y.png" alt="Un esquema"></p></figure></div>')
    p = pagina_desde_html(html, 1, "u1", recursos)
    img = [b for b in p["bloques"] if b["tipo"] == "imagen"][0]
    assert img["recurso_ref"] == recursos[0]["ref"]
    assert img["alt"] == "Un esquema"


def test_la_jerarquia_sale_de_la_numeracion():
    html = html_de(
        '<div class="ctab__panel">'
        "<h4><strong>1.2. Tema</strong></h4>"
        "<h4><strong>1.2.1. Subtema</strong></h4>"
        "<h4><strong>Sin numero</strong></h4></div>")
    p = pagina_desde_html(html, 1, "u1", [])
    niveles = {b["texto"]: b["nivel"] for b in p["bloques"] if b["tipo"] == "encabezado"}
    assert niveles["1.2. Tema"] == 2
    assert niveles["1.2.1. Subtema"] == 3
    assert niveles["Sin numero"] == 3


def test_los_titulos_no_llevan_marcado():
    """El <strong> dentro acaba como ** en la etiqueta de la pestaña."""
    html = html_de('<div class="ctab__panel"><h4><strong>1.1. Tema</strong></h4></div>')
    p = pagina_desde_html(html, 1, "u1", [])
    assert "<strong>" not in p["bloques"][0]["texto"]


def test_solo_se_conserva_el_marcado_permitido():
    from bs4 import BeautifulSoup
    sopa = BeautifulSoup(
        "<p>a <strong>b</strong> <span class='x'>c</span> <div>d</div></p>",
        "html.parser")
    salida = _inline(sopa.find("p"))
    assert "<strong>" in salida
    assert "<span" not in salida and "<div" not in salida
    assert "c" in salida and "d" in salida


def test_la_navegacion_no_se_importa_como_contenido():
    """El botón de inicio y los números de semana los repone el render."""
    html = html_de(
        '<section class="container-homepage-bnt"><a href="#">1</a></section>'
        '<div class="ctab__panel"><p>Contenido real.</p></div>')
    p = pagina_desde_html(html, 1, "u1", [])
    textos = " ".join(b.get("texto", "") for b in p["bloques"])
    assert "Contenido real." in textos
```

### 1.10 El catálogo académico

`tests/unitarias/test_oferta.py`:

```python
"""Las 12 variables de la UTPL y su cascada."""
from libs.py.canon import oferta


def test_hay_cuatro_niveles():
    assert len(oferta.NIVELES) == 4


def test_la_cascada_devuelve_carreras():
    for nivel, _ in oferta.NIVELES:
        for modalidad in oferta.modalidades(nivel):
            for facultad in oferta.facultades(nivel, modalidad["value"]):
                carreras = oferta.carreras(nivel, modalidad["value"], facultad["value"])
                assert carreras, f"{nivel}/{modalidad['value']}/{facultad['value']} vacío"


def test_hay_ciento_tres_carreras():
    total = sum(
        len(oferta.carreras(n, m["value"], f["value"]))
        for n, _ in oferta.NIVELES
        for m in oferta.modalidades(n)
        for f in oferta.facultades(n, m["value"])
    )
    assert total == 103


def test_etiqueta_devuelve_el_nombre_legible():
    """Al modelo le llega 'Facultad de...', no el identificador con guiones."""
    facs = oferta.facultades("grado", "en-linea")
    assert oferta.etiqueta(facs, facs[0]["value"]) == facs[0]["label"]


def test_valor_desconocido_no_revienta():
    assert oferta.modalidades("inventado") == []
    assert oferta.facultades("grado", "inventada") == []
```

### 1.11 El renderizador de plantillas

`tests/unitarias/test_macros.py`:

```python
"""Los doce tipos de bloque en HTML. El macro es la única fuente del HTML."""
import pytest
from jinja2 import Environment, FileSystemLoader

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture
def pintar():
    entorno = Environment(
        loader=FileSystemLoader(str(RAIZ / "packages" / "plantillas")))
    macros = entorno.get_template("macros/bloques.html").module

    def _pintar(bloque, ctx=None):
        return str(macros.bloque(bloque, ctx or {}))

    return _pintar


@pytest.mark.parametrize("tipo", [
    "parrafo", "encabezado", "lista", "tabla", "caja", "focalizador",
    "cita", "imagen", "diagrama", "recurso_ediloja", "autoevaluacion", "actividades",
])
def test_los_doce_tipos_se_pintan_sin_reventar(pintar, pagina_todos_los_tipos, tipo):
    bloque = [b for b in pagina_todos_los_tipos["bloques"] if b["tipo"] == tipo][0]
    html = pintar(bloque)
    assert html.strip()
    assert "no soportado" not in html


def test_un_tipo_desconocido_avisa_pero_no_rompe(pintar):
    """Regla de extensibilidad: nunca una página en blanco."""
    html = pintar({"id": "b000001", "tipo": "linea_de_tiempo", "texto": "x"})
    assert "no soportado" in html
    assert "linea_de_tiempo" in html


def test_el_focalizador_lleva_su_clase_y_su_icono(pintar):
    html = pintar({"id": "b000001", "tipo": "focalizador", "focalizador": "recuerde",
                   "bloques": [{"id": "b000002", "tipo": "parrafo", "texto": "x"}]})
    assert "focuser" in html
    assert 'data-focalizador="recuerde"' in html
    assert "f_recuerde.png" in html


def test_los_hijos_del_focalizador_se_pintan(pintar):
    html = pintar({"id": "b000001", "tipo": "focalizador", "focalizador": "nota",
                   "bloques": [{"id": "b000002", "tipo": "parrafo",
                                "texto": "CONTENIDO INTERIOR"}]})
    assert "CONTENIDO INTERIOR" in html


def test_una_lista_con_item_de_cadena_no_revienta(pintar):
    """Dato imperfecto: el renderizador pinta lo que puede."""
    html = pintar({"id": "b000001", "tipo": "lista", "items": ["suelto"]})
    assert "suelto" in html


def test_la_cita_huerfana_se_marca(pintar):
    html = pintar({"id": "b000001", "tipo": "cita", "texto": "x",
                   "referencia_id": "ref99"}, {"refs": {}})
    assert "no existe" in html


def test_el_marcado_en_linea_no_se_escapa(pintar):
    html = pintar({"id": "b000001", "tipo": "parrafo",
                   "texto": "con <strong>negrita</strong>"})
    assert "<strong>negrita</strong>" in html
```

### 1.12 Los iconos y los recursos

`tests/unitarias/test_recursos.py`:

```python
"""Los archivos que la plantilla necesita tienen que existir."""
from pathlib import Path

import pytest

from libs.py.agente.prompt import FOCALIZADORES

RAIZ = Path(__file__).resolve().parents[2]
ICONOS = RAIZ / "apps" / "pipeline-canvas" / "assets" / "plantilla" / "focalizadores"


@pytest.mark.parametrize("focalizador", FOCALIZADORES)
def test_cada_focalizador_tiene_su_icono(focalizador):
    assert (ICONOS / f"{focalizador}.png").exists(), \
        f"falta el icono de {focalizador}"


def test_el_esquema_y_el_prompt_declaran_los_mismos_focalizadores():
    """Dos listas del mismo vocabulario: si divergen, el modelo genera algo
    que el esquema rechaza."""
    import json
    esquema = json.loads(
        (RAIZ / "packages" / "esquemas" / "curso.schema.json").read_text(encoding="utf-8"))
    enum = esquema["$defs"]["bloque"]["properties"]["focalizador"]["enum"]
    assert set(enum) == set(FOCALIZADORES)


def test_los_tipos_de_bloque_coinciden_con_el_esquema():
    import json

    from libs.py.agente.prompt import TIPOS_DE_BLOQUE
    esquema = json.loads(
        (RAIZ / "packages" / "esquemas" / "curso.schema.json").read_text(encoding="utf-8"))
    enum = esquema["$defs"]["bloque"]["properties"]["tipo"]["enum"]
    assert set(enum) == set(TIPOS_DE_BLOQUE)
```

---

## Nivel 2 — Con base de datos

Necesitan PostgreSQL. Van marcadas con `@pytest.mark.bd`.

### Fixture de base de datos

`tests/integracion/conftest.py`:

```python
"""Base de datos de prueba, en transacción que se deshace al terminar.

Cada prueba trabaja sobre datos limpios y no ensucia la base de desarrollo.
Alternativa descartada: una base aparte por prueba. Es más lento y no aporta
nada aquí.
"""
import pytest
from sqlalchemy.orm import Session

from libs.py.db.modelos_auth import Rol, Usuario
from libs.py.db.modelos_dominio import Guia
from libs.py.db.session import engine


@pytest.fixture
def sesion():
    conexion = engine.connect()
    transaccion = conexion.begin()
    s = Session(bind=conexion)
    try:
        yield s
    finally:
        s.close()
        transaccion.rollback()
        conexion.close()


@pytest.fixture
def crear_usuario(sesion):
    from libs.py.auth.seguridad import hashear_contrasena

    def _crear(correo, roles=("docente",), activo=True):
        usuario = Usuario(correo=correo, nombre_completo=f"Prueba {correo}",
                          hash_contrasena=hashear_contrasena("clave-de-prueba"),
                          activo=activo)
        for codigo in roles:
            rol = sesion.query(Rol).filter_by(codigo=codigo).first()
            if rol is None:
                rol = Rol(codigo=codigo, nombre=codigo)
                sesion.add(rol)
            usuario.roles.append(rol)
        sesion.add(usuario)
        sesion.flush()
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
```

Ojo: `hashear_contrasena` puede llamarse de otra forma. Compruébalo:

```bash
grep -n "^def " libs/py/auth/seguridad.py
```

### 2.1 Usuarios, roles y autenticación

`tests/integracion/test_usuarios.py`:

```python
"""Un fallo de permisos expone datos ajenos: es lo que más hay que probar."""
import pytest

from libs.py.auth.seguridad import crear_token, leer_token, verificar_contrasena

pytestmark = pytest.mark.bd


def test_la_contrasena_no_se_guarda_en_claro(crear_usuario):
    usuario = crear_usuario("a@utpl.edu.ec")
    assert "clave-de-prueba" not in usuario.hash_contrasena
    assert verificar_contrasena("clave-de-prueba", usuario.hash_contrasena)


def test_una_contrasena_incorrecta_no_verifica(crear_usuario):
    usuario = crear_usuario("a@utpl.edu.ec")
    assert not verificar_contrasena("otra", usuario.hash_contrasena)


def test_un_usuario_puede_tener_varios_roles(crear_usuario):
    """Un docente que además publica es un usuario con los dos roles."""
    usuario = crear_usuario("a@utpl.edu.ec", roles=("docente", "operador"))
    assert usuario.codigos_de_rol() == {"docente", "operador"}


def test_tiene_rol_acepta_varios(crear_usuario):
    usuario = crear_usuario("a@utpl.edu.ec", roles=("qa",))
    assert usuario.tiene_rol("qa", "coordinador")
    assert not usuario.tiene_rol("operador")


def test_el_token_lleva_el_id_y_los_roles(crear_usuario):
    usuario = crear_usuario("a@utpl.edu.ec", roles=("docente",))
    carga = leer_token(crear_token(usuario.id, ["docente"]))
    assert int(carga["sub"]) == usuario.id


def test_un_token_manipulado_no_se_lee():
    import jwt
    with pytest.raises(jwt.PyJWTError):
        leer_token("no.es.un.token")
```

### 2.2 El alcance por rol

`tests/integracion/test_alcance.py`:

```python
"""El filtro va DENTRO de la consulta: traer todo y filtrar en Python se cae
con 5.000 guías, y si se olvida el filtro se exponen datos ajenos."""
import pytest

from libs.py.auth.alcance import guias_visibles

pytestmark = pytest.mark.bd


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
    crear_guia(ana)
    crear_guia(ana, codigo="OTRA")

    assert len(list(sesion.scalars(guias_visibles(coord)).all())) >= 2


def test_sin_rol_reconocido_no_ve_nada(sesion, crear_usuario, crear_guia):
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
    sesion.add(AsignacionRevision(guia_id=asignada.id, revisor_id=qa.id))
    sesion.flush()

    vistas = list(sesion.scalars(guias_visibles(qa)).all())
    assert [g.id for g in vistas] == [asignada.id]
```

### 2.3 Versiones, concurrencia y congelado

`tests/integracion/test_versiones.py`:

```python
"""Sin el sha256, el docente con dos pestañas se pisa su propio trabajo en
silencio: nadie se entera hasta que falta un párrafo."""
import hashlib
import json

import pytest

from libs.py.db.modelos_contenido import VersionGuia

pytestmark = pytest.mark.bd


def sha_de(documento):
    return hashlib.sha256(
        json.dumps(documento, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


@pytest.fixture
def version(sesion, crear_usuario, crear_guia, curso_minimo):
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    guia = crear_guia(ana)
    v = VersionGuia(guia_id=guia.id, numero=1, origen="agente_ia",
                    contenido=curso_minimo, version_esquema="1.0.0",
                    sha256=sha_de(curso_minimo), semaforo="verde",
                    congelada=False, es_actual=True, creada_por=ana.id)
    sesion.add(v)
    sesion.flush()
    return v


def test_el_sha_cambia_al_editar(sesion, version):
    antes = version.sha256
    contenido = dict(version.contenido)
    contenido["estructura"]["paginas"][0]["titulo"] = "Cambiado"
    version.contenido = contenido      # reasignar, no mutar
    version.sha256 = sha_de(contenido)
    sesion.flush()
    assert version.sha256 != antes


def test_mutar_el_json_en_su_sitio_no_se_guarda(sesion, version):
    """SQLAlchemy solo detecta el cambio en JSONB si el objeto es distinto.
    Mutando en su sitio no se guarda nada y NO salta ningún error."""
    version.contenido["info_general"]["asignatura"] = "MUTADO"
    sesion.flush()
    sesion.expire(version)
    assert version.contenido["info_general"]["asignatura"] != "MUTADO"


def test_solo_una_version_actual_por_guia(sesion, version, curso_minimo):
    for anterior in version.guia.versiones:
        anterior.es_actual = False
    nueva = VersionGuia(guia_id=version.guia_id, numero=2, origen="agente_ia",
                        contenido=curso_minimo, version_esquema="1.0.0",
                        sha256=sha_de(curso_minimo), congelada=False,
                        es_actual=True, creada_por=version.creada_por)
    sesion.add(nueva)
    sesion.flush()
    actuales = [v for v in version.guia.versiones if v.es_actual]
    assert len(actuales) == 1
```

### 2.4 Cuotas de regeneración

`tests/integracion/test_cuotas.py`:

```python
"""Tres regeneraciones POR SEMANA, no por guía. Un fallo técnico no descuenta."""
import pytest

from libs.py.db.modelos_dominio import CuotaPagina

pytestmark = pytest.mark.bd


def test_la_cuota_empieza_en_tres(sesion, crear_usuario, crear_guia):
    ana = crear_usuario("ana@utpl.edu.ec")
    guia = crear_guia(ana)
    cuota = CuotaPagina(guia_id=guia.id, pagina_id="p1", usadas=0, maximas=3)
    sesion.add(cuota)
    sesion.flush()
    assert cuota.disponibles == 3


def test_agotarla_deja_disponibles_en_cero(sesion, crear_usuario, crear_guia):
    ana = crear_usuario("ana@utpl.edu.ec")
    guia = crear_guia(ana)
    cuota = CuotaPagina(guia_id=guia.id, pagina_id="p1", usadas=3, maximas=3)
    sesion.add(cuota)
    sesion.flush()
    assert cuota.disponibles == 0


def test_la_cuota_es_por_pagina(sesion, crear_usuario, crear_guia):
    ana = crear_usuario("ana@utpl.edu.ec")
    guia = crear_guia(ana)
    sesion.add_all([
        CuotaPagina(guia_id=guia.id, pagina_id="p1", usadas=3, maximas=3),
        CuotaPagina(guia_id=guia.id, pagina_id="p2", usadas=0, maximas=3),
    ])
    sesion.flush()
    p2 = sesion.query(CuotaPagina).filter_by(guia_id=guia.id, pagina_id="p2").one()
    assert p2.disponibles == 3
```

---

## Nivel 3 — Con la aplicación

Usan el `TestClient` de FastAPI. Prueban rutas, permisos y códigos HTTP.

`tests/integracion/test_api.py`:

```python
"""Las rutas y sus códigos. El 404 en vez de 403 es deliberado: un 403
confirmaría que el recurso existe."""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

pytestmark = pytest.mark.bd


@pytest.fixture
def cliente():
    return TestClient(app)


def test_salud_responde(cliente):
    assert cliente.get("/salud").status_code == 200


def test_login_con_credenciales_malas_da_401(cliente):
    r = cliente.post("/auth/login",
                     data={"username": "noexiste@utpl.edu.ec", "password": "x"})
    assert r.status_code == 401


def test_el_mensaje_de_login_no_revela_cual_fallo(cliente):
    """Decir 'ese correo no existe' regala la lista de correos válidos."""
    r = cliente.post("/auth/login",
                     data={"username": "noexiste@utpl.edu.ec", "password": "x"})
    detalle = r.json()["detail"].lower()
    assert "correo o contraseña" in detalle
    assert "no existe" not in detalle


def test_las_rutas_de_api_exigen_token(cliente):
    for ruta in ["/guias", "/auth/yo", "/api/trabajos/1"]:
        assert cliente.get(ruta).status_code == 401, ruta


def test_las_vistas_redirigen_al_login(cliente):
    """Una vista no devuelve 401: redirige."""
    for ruta in ["/panel", "/guias-vista", "/guias-vista/1/editor"]:
        r = cliente.get(ruta, follow_redirects=False)
        assert r.status_code == 303, ruta
        assert r.headers["location"].endswith("/entrar")


def test_la_cookie_de_sesion_es_httponly(cliente, crear_usuario):
    """Este proyecto publica HTML generado por IA en Canvas: si se cuela un
    script, no debe poder leer la sesión."""
    crear_usuario("cookie@utpl.edu.ec")
    r = cliente.post("/entrar",
                     data={"correo": "cookie@utpl.edu.ec",
                           "contrasena": "clave-de-prueba"},
                     follow_redirects=False)
    assert r.status_code == 303
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_openapi_declara_las_rutas_esperadas(cliente):
    rutas = cliente.get("/openapi.json").json()["paths"]
    for ruta in ["/auth/login", "/guias", "/api/versiones/{version_id}/editar",
                 "/api/guias/{guia_id}/generar", "/api/trabajos/{trabajo_id}"]:
        assert ruta in rutas, ruta
```

### 3.1 Permisos de las vistas

`tests/integracion/test_permisos_vistas.py`:

```python
"""Quién puede hacer qué. Cada caso aquí es una puerta que no debe abrirse."""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from libs.py.auth.dependencias import NOMBRE_COOKIE
from libs.py.auth.seguridad import crear_token

pytestmark = pytest.mark.bd


def cliente_de(usuario):
    c = TestClient(app)
    c.cookies.set(NOMBRE_COOKIE,
                  crear_token(usuario.id, sorted(usuario.codigos_de_rol())))
    return c


def test_el_docente_no_puede_publicar(crear_usuario, crear_guia):
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    guia = crear_guia(ana, estado="aprobada")
    r = cliente_de(ana).get(f"/guias-vista/{guia.id}/publicar",
                            follow_redirects=False)
    assert r.status_code == 404


def test_el_operador_si_puede_publicar(crear_usuario, crear_guia):
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    op = crear_usuario("op@utpl.edu.ec", roles=("operador",))
    guia = crear_guia(ana, estado="aprobada")
    assert cliente_de(op).get(f"/guias-vista/{guia.id}/publicar").status_code == 200


def test_no_se_publica_una_guia_sin_aprobar(crear_usuario, crear_guia):
    """Publicar un borrador se salta la revisión, que es justo lo que el ciclo
    de vida existe para impedir."""
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    op = crear_usuario("op@utpl.edu.ec", roles=("operador", "admin"))
    guia = crear_guia(ana, estado="borrador")
    r = cliente_de(op).post(f"/guias-vista/{guia.id}/publicar",
                            data={"canvas_curso_id": "99999"})
    assert r.status_code == 409


def test_una_guia_ajena_devuelve_404_no_403(crear_usuario, crear_guia):
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    luis = crear_usuario("luis@utpl.edu.ec", roles=("docente",))
    guia = crear_guia(ana)
    r = cliente_de(luis).get(f"/guias-vista/{guia.id}/editor")
    assert r.status_code == 404


def test_no_se_edita_una_version_congelada(crear_usuario, crear_guia, curso_minimo):
    """Congelada = en revisión. Solo un revisor descongela; si pudiera el
    docente, la congelación no serviría de nada."""
    import hashlib
    import json

    from libs.py.db.modelos_contenido import VersionGuia
    from libs.py.db.session import SesionLocal

    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    guia = crear_guia(ana)
    s = SesionLocal()
    s.add(VersionGuia(
        guia_id=guia.id, numero=1, origen="agente_ia", contenido=curso_minimo,
        version_esquema="1.0.0",
        sha256=hashlib.sha256(json.dumps(curso_minimo, sort_keys=True).encode()).hexdigest(),
        congelada=True, es_actual=True, creada_por=ana.id))
    s.commit()
    s.close()

    r = cliente_de(ana).post(
        f"/ui/bloque/{guia.id}/p1/bpar001a", data={"texto": "Nuevo"})
    assert r.status_code == 409
```

### 3.2 El formulario de requerimientos

`tests/integracion/test_requerimientos.py`:

```python
"""Las 12 variables de la UTPL. Renombrar una hace que el prompt reciba
undefined y el fallo aparece lejos de su causa."""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from libs.py.auth.dependencias import NOMBRE_COOKIE
from libs.py.auth.seguridad import crear_token

pytestmark = pytest.mark.bd

CAMPOS = ["level", "modality", "faculty", "program", "subjectCode",
          "academicPeriod", "subjectName", "weeks", "credits",
          "learningOutcome", "contents", "methodology", "bibliography"]


def cliente_de(usuario):
    c = TestClient(app)
    c.cookies.set(NOMBRE_COOKIE, crear_token(usuario.id, sorted(usuario.codigos_de_rol())))
    return c


def test_el_formulario_pide_los_trece_campos(crear_usuario, crear_guia):
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    guia = crear_guia(ana)
    html = cliente_de(ana).get(f"/guias-vista/{guia.id}/generar").text
    for campo in CAMPOS:
        assert f'name="{campo}"' in html, f"falta el campo {campo}"


def test_la_duracion_solo_ofrece_8_o_16(crear_usuario, crear_guia):
    """Su formulario original admitía 1-20 y el servidor rechazaba el resto."""
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    guia = crear_guia(ana)
    html = cliente_de(ana).get(f"/guias-vista/{guia.id}/generar").text
    assert 'value="8"' in html and 'value="16"' in html
    assert 'value="12"' not in html


def test_la_cascada_devuelve_opciones(crear_usuario):
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    c = cliente_de(ana)
    assert "<option" in c.get("/ui/modalidades", params={"level": "grado"}).text
    assert "<option" in c.get(
        "/ui/facultades", params={"level": "grado", "modality": "en-linea"}).text


def test_una_duracion_invalida_se_rechaza(crear_usuario, crear_guia):
    ana = crear_usuario("ana@utpl.edu.ec", roles=("docente",))
    guia = crear_guia(ana)
    datos = {c: "x" for c in CAMPOS}
    datos.update({"weeks": "12", "credits": "3"})
    r = cliente_de(ana).post(f"/guias-vista/{guia.id}/requerimientos", data=datos)
    assert r.status_code == 422
```

---

## Nivel 4 — Flujo completo con modelo simulado

Sin gastar tokens. Usa `AGENTE_SIMULADO=1` y la cola síncrona.

`tests/extremo/test_generacion.py`:

```python
"""De los requerimientos a un curso.json válido, sin llamar al modelo."""
import json

import jsonschema
import pytest

from libs.py.agente.cliente import RespuestaModelo
from libs.py.agente.generador import ErrorDeGeneracion, generar_guia
from libs.py.agente.unidades import plan_desde_unidades

pytestmark = pytest.mark.lento


def modelo_simulado(instrucciones, contenido):
    """Devuelve una página válida, con autoevaluación si la semana cierra unidad."""
    semana = 1
    for linea in contenido.splitlines():
        if linea.lower().startswith("semana:"):
            semana = int("".join(c for c in linea if c.isdigit()) or 1)
            break

    pagina = {"titulo": f"Semana {semana}", "bloques": [
        {"tipo": "encabezado", "nivel": 2, "texto": "Contenidos"},
        {"tipo": "parrafo", "texto": "Texto <strong>simulado</strong>."},
        {"tipo": "focalizador", "focalizador": "recuerde",
         "bloques": [{"tipo": "parrafo", "texto": "Repase."}]},
        {"tipo": "lista", "ordenada": False,
         "items": [{"texto": "Uno"}, {"texto": "Dos"}]},
    ]}
    if "cierra unidad" in contenido.lower():
        pagina["bloques"].append({"tipo": "autoevaluacion", "preguntas": [
            {"id": f"q{i}", "numero": i, "enunciado": f"Pregunta {i} simulada",
             "opciones": [{"letra": "a", "texto": "A"}, {"letra": "b", "texto": "B"}],
             "correcta": "a", "retroalimentacion": "Porque sí."}
            for i in range(1, 11)]})

    return RespuestaModelo(texto=json.dumps(pagina, ensure_ascii=False),
                           tokens_entrada=1200, tokens_salida=900)


@pytest.fixture
def datos_curso():
    unidades = [
        {"id": "u1", "numero": 1, "titulo": "Primera",
         "resultado_aprendizaje_id": "ra1", "semana_inicio": 1, "semana_fin": 4},
        {"id": "u2", "numero": 2, "titulo": "Segunda",
         "resultado_aprendizaje_id": "ra1", "semana_inicio": 5, "semana_fin": 8},
    ]
    return {
        "codigo_banner": "TEST101", "asignatura": "Prueba",
        "periodo": "2026-1", "total_semanas": 8,
        "unidades": unidades,
        "resultados_aprendizaje": [
            {"id": "ra1", "numero": 1, "texto": "Aplica los fundamentos en casos reales."}],
        "plan": plan_desde_unidades(unidades),
    }


def test_la_guia_generada_valida_contra_el_esquema(esquema, datos_curso):
    curso, _ = generar_guia(datos_curso, plan=datos_curso["plan"],
                            bibliografia=["Autor, A. (2020). Título. Editorial."],
                            llamador=modelo_simulado,
                            validar=lambda c: type("R", (), {
                                "semaforo": "verde",
                                "como_dict": lambda self: {"semaforo": "verde",
                                                           "alertas": []}})())
    errores = list(jsonschema.Draft202012Validator(esquema).iter_errors(curso))
    assert errores == [], [e.message for e in errores[:3]]


def test_se_generan_las_ocho_paginas(datos_curso):
    curso, _ = generar_guia(datos_curso, plan=datos_curso["plan"],
                            llamador=modelo_simulado,
                            validar=lambda c: type("R", (), {
                                "semaforo": "verde",
                                "como_dict": lambda self: {"alertas": []}})())
    assert len(curso["estructura"]["paginas"]) == 8


def test_las_paginas_llevan_su_unidad_id(datos_curso):
    curso, _ = generar_guia(datos_curso, plan=datos_curso["plan"],
                            llamador=modelo_simulado,
                            validar=lambda c: type("R", (), {
                                "semaforo": "verde",
                                "como_dict": lambda self: {"alertas": []}})())
    for pagina in curso["estructura"]["paginas"]:
        assert pagina.get("unidad_id"), f"semana {pagina['semana']} sin unidad_id"


def test_la_telemetria_suma_los_tokens(datos_curso):
    _, telemetria = generar_guia(datos_curso, plan=datos_curso["plan"],
                                 llamador=modelo_simulado,
                                 validar=lambda c: type("R", (), {
                                     "semaforo": "verde",
                                     "como_dict": lambda self: {"alertas": []}})())
    assert telemetria["tokens_entrada"] == 1200 * 8
    assert telemetria["intentos"] >= 8


def test_avisar_reporta_cada_semana(datos_curso):
    avisos = []
    generar_guia(datos_curso, plan=datos_curso["plan"], llamador=modelo_simulado,
                 avisar=lambda hechas, total: avisos.append((hechas, total)),
                 validar=lambda c: type("R", (), {
                     "semaforo": "verde",
                     "como_dict": lambda self: {"alertas": []}})())
    assert avisos == [(n, 8) for n in range(1, 9)]


def test_una_respuesta_truncada_lo_dice(datos_curso):
    """El mensaje distingue 'el modelo escribe mal JSON' de 'se agotó
    max_tokens': son causas distintas y arreglos distintos."""
    def truncado(instrucciones, contenido):
        return RespuestaModelo(texto='{"titulo": "x", "bloques": [{"tipo": "parr',
                               tokens_entrada=100, tokens_salida=16000)

    with pytest.raises(ErrorDeGeneracion, match="[Tt]runcada|MAX_TOKENS"):
        generar_guia(datos_curso, plan=datos_curso["plan"], llamador=truncado,
                     validar=lambda c: None)


def test_una_respuesta_invalida_se_reintenta(datos_curso):
    intentos = {"n": 0}

    def inestable(instrucciones, contenido):
        intentos["n"] += 1
        if intentos["n"] == 1:
            return RespuestaModelo(texto="no es json", tokens_entrada=1, tokens_salida=1)
        return modelo_simulado(instrucciones, contenido)

    generar_guia({**datos_curso, "total_semanas": 1},
                 plan=[{"semana": 1, "unidad": 1, "unidad_id": "u1"}],
                 llamador=inestable,
                 validar=lambda c: type("R", (), {
                     "semaforo": "verde",
                     "como_dict": lambda self: {"alertas": []}})())
    assert intentos["n"] == 2
```

### 4.1 La cadena de publicación

`tests/extremo/test_publicacion.py`:

```python
"""curso.json -> adaptador -> render. Sin tocar Canvas."""
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "apps" / "pipeline-canvas"))

from libs.py.publicacion.adaptador_canonico import convertir  # noqa: E402


@pytest.fixture
def mapa_falso():
    """Un mapa de plantilla con las claves que usa el render."""
    return {
        clave: {"file_id": 1, "url": f"https://canvas/files/{i}", "carpeta": "x"}
        for i, clave in enumerate([
            "iconos/home", "iconos/hover/home", "iconos/resultado_aprendizaje",
            "iconos/contextualizacion", "iconos/zona_practica",
            "iconos/actividades_recomendadas", "iconos/hover/actividades_recomendadas",
            "iconos/autoevaluacion", "iconos/hover/autoevaluacion",
            "iconos/actividad_evaluada", "iconos/hover/actividad_evaluada",
        ])
    }


def test_el_html_usa_el_vocabulario_ed(curso_minimo, mapa_falso):
    """El tema global estiliza ed-*; cc-* es el tema anterior."""
    import render_utpl

    canonico = convertir(curso_minimo)
    html = render_utpl.html_semana_utpl(canonico, 1, mapa_falso,
                                        "https://canvas", "1")
    assert 'class="ed-container"' in html
    assert "cc-" not in html


def test_el_html_lleva_las_secciones_de_la_plantilla(curso_minimo, mapa_falso):
    import render_utpl

    html = render_utpl.html_semana_utpl(convertir(curso_minimo), 1, mapa_falso,
                                        "https://canvas", "1")
    for marca in ["week_course", "container-homepage-bnt",
                  "container-learning-outcome", "final_content",
                  "preliminary-tabs", "ed-footer"]:
        assert marca in html, f"falta la sección {marca}"


def test_la_cabecera_va_vacia(curso_minimo, mapa_falso):
    """El tema pone ahí la imagen de banner; un título encima se solapa."""
    import render_utpl

    html = render_utpl.html_semana_utpl(convertir(curso_minimo), 1, mapa_falso,
                                        "https://canvas", "1")
    assert '<header class="ed-header"></header>' in html


def test_la_contextualizacion_solo_en_la_semana_que_abre_la_unidad(
        curso_minimo, mapa_falso):
    import copy

    import render_utpl

    curso = copy.deepcopy(curso_minimo)
    curso["estructura"]["unidades"][0]["contextualizacion"] = "Contexto. " * 20
    canonico = convertir(curso)
    s1 = render_utpl.html_semana_utpl(canonico, 1, mapa_falso, "https://canvas", "1")
    s2 = render_utpl.html_semana_utpl(canonico, 2, mapa_falso, "https://canvas", "1")
    assert "Contextualiz" in s1
    assert "Contextualiz" not in s2


def test_la_navegacion_apunta_a_las_semanas_del_curso(curso_minimo, mapa_falso):
    import render_utpl

    html = render_utpl.html_semana_utpl(convertir(curso_minimo), 3, mapa_falso,
                                        "https://canvas", "90020")
    assert "/courses/90020/pages/semana-1" in html
    assert 'class="active" title="Semana 3"' in html
```

### 4.2 El circuito de migración

`tests/extremo/test_migracion.py`:

```python
"""HTML de un curso viejo -> curso.json -> HTML con la plantilla nueva."""
import jsonschema

from libs.py.agente import ensamblado
from libs.py.publicacion.html_a_bloques import curso_desde_extraido

HTML_SEMANA = """
<div class="ed-container">
  <section class="content">
    <div class="subtitle-section"><h3><strong>Unidad 1.</strong> Fundamentos</h3></div>
    <div data-origen="introduccion-fuente" data-unidad="1">
      <p>Introducción de la unidad.</p>
    </div>
    <div class="ctab">
      <div class="ctab__panel">
        <h4><strong>1.1. Primer tema</strong></h4>
        <p>Contenido del primer tema.</p>
        <div class="focuser important">
          <div class="content-focuser"><p>Aviso importante.</p></div>
        </div>
        <table class="table-general">
          <thead><tr><th>A</th></tr></thead><tbody><tr><td>1</td></tr></tbody>
        </table>
      </div>
    </div>
  </section>
</div>
"""


def extraido_falso(semanas=3):
    return {
        "curso_id": 1, "nombre": "Curso de prueba",
        "modulos": [{"id": 1, "nombre": "Contenido", "items": [
            {"id": n, "titulo": f"Semana {n}", "tipo_canvas": "Page",
             "clasificacion": "otro", "html": HTML_SEMANA}
            for n in range(1, semanas + 1)]}],
        "paginas_sueltas": [],
    }


def test_el_curso_migrado_valida(esquema):
    curso = curso_desde_extraido(extraido_falso())
    for pagina in curso["estructura"]["paginas"]:
        ensamblado.poner_ids_y_origen(pagina["bloques"], origen="docente")
    curso["info_general"]["codigo_banner"] = "SIN-CODIGO"
    errores = list(jsonschema.Draft202012Validator(esquema).iter_errors(curso))
    assert errores == [], [e.message for e in errores[:3]]


def test_se_reconocen_los_tipos_de_bloque():
    curso = curso_desde_extraido(extraido_falso(1))
    tipos = {b["tipo"] for b in curso["estructura"]["paginas"][0]["bloques"]}
    assert {"encabezado", "parrafo", "focalizador", "tabla"} <= tipos


def test_el_titulo_de_unidad_sale_del_html():
    """El valor por defecto hacía que el render escribiera 'Unidad 1. Unidad 1'."""
    curso = curso_desde_extraido(extraido_falso(1))
    assert curso["estructura"]["unidades"][0]["titulo"] == "Fundamentos"


def test_los_modulos_repetidos_no_duplican_semanas():
    extraido = extraido_falso(2)
    extraido["modulos"].append(dict(extraido["modulos"][0]))
    curso = curso_desde_extraido(extraido)
    semanas = [p["semana"] for p in curso["estructura"]["paginas"]]
    assert semanas == sorted(set(semanas))


def test_el_contenido_migrado_es_de_origen_docente():
    """No lo escribió el agente: contarlo como suyo falsearía la métrica."""
    curso = curso_desde_extraido(extraido_falso(1))
    for pagina in curso["estructura"]["paginas"]:
        ensamblado.poner_ids_y_origen(pagina["bloques"], origen="docente")
        for bloque in pagina["bloques"]:
            assert bloque["origen"] == "docente"
```

---

## Nivel 5 — Contra Canvas real

Marcadas con `@pytest.mark.canvas`. **No se ejecutan en CI** y modifican un
curso de verdad.

`tests/extremo/test_canvas.py`:

```python
"""Contra Canvas real. Requiere CANVAS_TEST_CURSO: un curso VACÍO.

    CANVAS_TEST_CURSO=90099 pytest -m canvas

Canvas no reutiliza los identificadores de páginas borradas: si el curso ya
tuvo una 'Semana 1', las nuevas salen con sufijo y la navegación se rompe.
"""
import os

import pytest
import requests

from libs.py.config.settings import settings

pytestmark = pytest.mark.canvas

CURSO = os.getenv("CANVAS_TEST_CURSO")


@pytest.fixture(autouse=True)
def exige_curso():
    if not CURSO:
        pytest.skip("define CANVAS_TEST_CURSO con un curso vacío")


def api(ruta):
    return requests.get(
        f"{settings.canvas_url.rstrip('/')}/api/v1{ruta}",
        headers={"Authorization": f"Bearer {settings.canvas_token}"}, timeout=30)


def test_el_token_es_valido():
    assert api("/users/self").status_code == 200


def test_el_curso_de_prueba_existe():
    assert api(f"/courses/{CURSO}").status_code == 200


def test_el_curso_de_prueba_esta_vacio():
    paginas = api(f"/courses/{CURSO}/pages").json()
    assert paginas == [], "el curso debe estar vacío: los slugs no se reutilizan"


@pytest.mark.lento
def test_publicacion_completa(curso_minimo):
    from libs.py.publicacion.canvas import publicar

    avisos = []
    resultado = publicar(curso_minimo, int(CURSO), settings.canvas_url,
                         avisar=lambda pct, msg: avisos.append(pct))

    assert resultado["semanas"] == list(range(1, 9))
    assert avisos[-1] == 100

    paginas = {p["url"] for p in api(f"/courses/{CURSO}/pages").json()}
    for n in range(1, 9):
        assert f"semana-{n}" in paginas, f"falta semana-{n} (¿slug con sufijo?)"


@pytest.mark.lento
def test_la_pagina_de_inicio_es_la_portada():
    curso = api(f"/courses/{CURSO}").json()
    assert curso.get("default_view") == "wiki"
```

---

## 9. Lista de comprobación manual

Lo que no se automatiza. Media hora, antes de cada demostración.

### Acceso

- [ ] `/entrar` con credenciales incorrectas → mensaje ambiguo, sin decir cuál falló
- [ ] Con credenciales correctas → aterriza en `/panel`
- [ ] «Cerrar sesión» → vuelve a `/entrar` y no se puede volver atrás
- [ ] Abrir `/panel` en ventana de incógnito → redirige al login

### Panel

- [ ] Muestra el nombre y los roles del usuario
- [ ] Las cajas de conteo cuadran con la tabla
- [ ] Una guía en `borrador` sin versión ofrece **Generar**, no **Editar**
- [ ] Una guía `aprobada` ofrece **Publicar**, no **Editar**
- [ ] Un docente no ve el botón de **Publicar**

### Crear y generar

- [ ] «Nueva guía» → el formulario de las 12 variables
- [ ] Elegir nivel rellena modalidad; modalidad rellena facultad; facultad rellena carrera
- [ ] La duración solo ofrece 8 y 16
- [ ] Enviar sin un campo obligatorio → el navegador lo marca
- [ ] La pantalla de confirmación muestra los nombres legibles, no los identificadores con guiones
- [ ] Con acentos: «Psicología», no `Psicolog\u00eda`
- [ ] «Generar» → pantalla de progreso, el porcentaje sube
- [ ] Pulsar «Generar» dos veces → lleva al trabajo en curso, no lanza dos

### Editor

- [ ] Las semanas se listan y se puede navegar entre ellas
- [ ] Los doce tipos de bloque se ven con su formato
- [ ] Un párrafo se edita, se guarda, y **al recargar sigue el cambio**
- [ ] «Cancelar» descarta sin guardar
- [ ] Meter `<div>` en el editor → error 422 con mensaje claro
- [ ] El semáforo de la cabecera coincide con el de la base

### Publicación

- [ ] Un curso de Canvas **vacío** cada vez
- [ ] El progreso pasa por 5% → 20% → 30% → y sube semana a semana
- [ ] Al terminar, el curso abre en la página de **Inicio**, no en módulos
- [ ] Las ocho semanas tienen contenido y los slugs son `semana-1`… sin sufijo
- [ ] Los focalizadores se ven con su icono y su color
- [ ] Las pestañas de subtema funcionan y son los temas, no los apartados del prompt
- [ ] La contextualización aparece solo en la primera semana de la unidad
- [ ] La navegación entre semanas lleva a las páginas correctas
- [ ] No hay `**` ni `<strong>` visibles como texto

### Migración

- [ ] «Importar de Canvas» con el id de un curso publicado
- [ ] Aterriza en el editor con las semanas del curso viejo
- [ ] Los focalizadores conservan su tipo
- [ ] Las tablas conservan encabezados y filas
- [ ] Desde el editor se puede **Regenerar** o **Aprobar y publicar**
- [ ] El curso de origen **no se ha modificado**

---

## 10. Cómo se ejecuta todo

```bash
# rápido, mientras se programa: solo unitarias, menos de 2 segundos
pytest tests/unitarias -q

# con base de datos, antes de subir
pytest -m "not canvas" -q

# todo, incluido Canvas real, contra un curso vacío
CANVAS_TEST_CURSO=90099 pytest -q

# una sola prueba mientras se depura
pytest tests/unitarias/test_normalizar.py::test_contenido_se_traduce_a_bloques -x -vv

# cobertura, para ver qué falta
pytest -m "not canvas" --cov=libs --cov-report=term-missing
```

### En CI

`.github/workflows/pruebas.yml`, si ya hay CI:

```yaml
- run: pytest -m "not canvas and not lento" --cov=libs
```

Se excluye Canvas porque modifica cursos reales, y `lento` para que el ciclo
siga siendo rápido. Las lentas se lanzan a mano antes de cada entrega.

---

## 11. Los diez fallos que ya ocurrieron

Cada uno tiene su prueba arriba. Si alguno vuelve, la prueba lo caza.

| # | Fallo | Por qué costó encontrarlo | Prueba |
|---|---|---|---|
| 1 | `plan_desde_unidades` no ponía `unidad_id` | `.get()` con valor por defecto devolvía vacío, sin error | `test_el_plan_lleva_unidad_id` |
| 2 | El `learningOutcome` no llegaba a `resultados_aprendizaje` | El docente lo escribía y se perdía en silencio | `test_el_resultado_de_aprendizaje_va_en_ras_globales_curados` |
| 3 | `MAX_TOKENS` en 8000 cortaba el JSON | El mensaje decía «JSON mal formado» y mandaba a depurar el prompt | `test_una_respuesta_truncada_lo_dice` |
| 4 | Nadie llamaba a `load_dotenv` | La API funcionaba y el worker no, con la misma configuración | `test_el_token_es_valido` |
| 5 | `env_file=".env"` relativo | Fallaba según desde dónde arrancara el proceso | fixture de `settings` |
| 6 | Variable de entorno **exportada y vacía** ganaba sobre el `.env` | No se ve al mirar el entorno; el síntoma era un 401 | comprobación en `ejecutar.py` |
| 7 | El modelo escribía `contenido` en vez de `bloques` | El documento se rechazaba entero, 400 errores de golpe | `test_contenido_se_traduce_a_bloques` |
| 8 | `md_inline` escapaba el HTML antes de traducir | `<strong>` llegaba a Canvas como texto literal | `test_html_se_convierte_a_markdown` |
| 9 | La jerarquía se dedujo del nivel HTML y no de la numeración | 17 pestañas en una semana | `test_la_jerarquia_sale_de_la_numeracion` (×2) |
| 10 | La misma regla escrita en dos archivos | Se arregló en uno y el otro siguió mal | pruebas en los dos módulos |

### Deuda pendiente, para no olvidarla

- [ ] La regla de jerarquía está en `html_a_bloques.py` **y** en `adaptador_canonico.py`. Extraer a una función común.
- [ ] Los iconos de focalizador están duplicados en dos carpetas.
- [ ] `_texto_plano` y `_a_markdown` hacen trabajo solapado.
- [ ] No hay prueba de `render_inicio_ed.py`: se comprueba a mano.
