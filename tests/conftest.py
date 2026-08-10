"""Fixtures compartidas por todas las pruebas.

Los curso.json de prueba se construyen aquí y no se leen de
datos_ejemplo/fixtures: un fixture en disco cambia cuando alguien regenera, y
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
    """Una página con los doce tipos. El caso que más rompe."""
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
