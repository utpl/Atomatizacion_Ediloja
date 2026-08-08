"""Pruebas del agente con un modelo SIMULADO.

Ni una sola llamada real a la API. Todo lo que se prueba aquí —reintentos,
ensamblado, numeración, estadísticas, regeneración— es lógica nuestra, y la
lógica nuestra se prueba sin gastar dinero ni depender de la red.

Ejecutar:  pytest tests/test_agente.py -v
"""

from __future__ import annotations

import json

import pytest

from libs.py.agente import ensamblado
from libs.py.agente.cliente import RespuestaModelo
from libs.py.agente.generador import (
    ErrorDeGeneracion,
    _comprobar_pagina,
    _extraer_json,
    generar_guia,
    generar_pagina,
    regenerar_pagina,
)

DATOS_CURSO = {
    "codigo_banner": "CONT1140",
    "asignatura": "Contabilidad General",
    "periodo": "2026-1",
    "total_semanas": 3,
    "unidades": [{"id": "u1", "numero": 1, "titulo": "Fundamentos"}],
}


def paginas(curso):
    """Las páginas viven en estructura.paginas."""
    return curso["estructura"]["paginas"]


def _validar_falso(curso):
    """Sustituye al validador institucional. Aquí no se prueba el validador."""
    return {"semaforo": "verde", "alertas": []}


def _pagina_valida(titulo: str = "Semana de prueba", con_imagen: bool = True) -> dict:
    bloques = [
        {"tipo": "encabezado", "nivel": 2, "texto": titulo},
        {"tipo": "parrafo", "texto": "Texto con <strong>negrita</strong> permitida."},
        {
            "tipo": "focalizador",
            "focalizador": "recuerde",
            "bloques": [{"tipo": "parrafo", "texto": "Un recordatorio."}],
        },
    ]
    if con_imagen:
        bloques.append({"tipo": "imagen", "alt": "Diagrama del ciclo contable"})
    return {"titulo": titulo, "bloques": bloques}


class ModeloSimulado:
    """Devuelve respuestas prefijadas y cuenta cuántas veces lo llaman."""

    def __init__(self, respuestas: list[str]):
        self.respuestas = respuestas
        self.llamadas: list[tuple[str, str]] = []

    def __call__(self, instrucciones: str, contenido: str) -> RespuestaModelo:
        self.llamadas.append((instrucciones, contenido))
        i = min(len(self.llamadas) - 1, len(self.respuestas) - 1)
        return RespuestaModelo(texto=self.respuestas[i], tokens_entrada=100, tokens_salida=250)


# ---------------------------------------------------------------------------
# Extracción del JSON
# ---------------------------------------------------------------------------


def test_extrae_json_pelado():
    assert _extraer_json('{"a": 1}') == {"a": 1}


def test_extrae_json_dentro_de_valla_markdown():
    assert _extraer_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extrae_json_con_frase_de_cortesia_delante():
    texto = 'Claro, aquí tienes la semana:\n{"a": 1}\nEspero que sirva.'
    assert _extraer_json(texto) == {"a": 1}


def test_json_mal_formado_da_error_claro():
    with pytest.raises(ValueError, match="JSON mal formado"):
        _extraer_json('{"a": 1,,}')


def test_sin_json_da_error_claro():
    with pytest.raises(ValueError, match="no contiene ningún objeto JSON"):
        _extraer_json("Lo siento, no puedo ayudarte con eso.")


# ---------------------------------------------------------------------------
# Comprobación de la página
# ---------------------------------------------------------------------------


def test_pagina_valida_no_da_errores():
    assert _comprobar_pagina(_pagina_valida()) == []


def test_rechaza_tipo_de_bloque_inexistente():
    pagina = {"titulo": "X", "bloques": [{"tipo": "smartart"}]}
    errores = _comprobar_pagina(pagina)
    assert any("smartart" in e for e in errores)


def test_rechaza_focalizador_fuera_del_enum():
    pagina = {"titulo": "X", "bloques": [{"tipo": "focalizador", "focalizador": "atencion"}]}
    errores = _comprobar_pagina(pagina)
    assert any("atencion" in e for e in errores)


def test_acepta_los_18_focalizadores():
    from libs.py.agente.prompt import FOCALIZADORES

    assert len(FOCALIZADORES) == 18
    for variante in FOCALIZADORES:
        pagina = {
            "titulo": "X",
            "bloques": [{"tipo": "focalizador", "focalizador": variante}],
        }
        assert _comprobar_pagina(pagina) == [], f"falló {variante}"


def test_rechaza_html_fuera_de_la_lista_blanca():
    pagina = {"titulo": "X", "bloques": [{"tipo": "parrafo", "texto": "<div>no</div>"}]}
    errores = _comprobar_pagina(pagina)
    assert any("div" in e for e in errores)


def test_acepta_html_de_la_lista_blanca():
    pagina = {
        "titulo": "X",
        "bloques": [{"tipo": "parrafo", "texto": "<strong>a</strong> <em>b</em><br>"}],
    }
    assert _comprobar_pagina(pagina) == []


def test_rechaza_anidamiento_de_dos_niveles():
    pagina = {
        "titulo": "X",
        "bloques": [
            {
                "tipo": "caja",
                "bloques": [
                    {"tipo": "caja", "bloques": [{"tipo": "parrafo", "texto": "hondo"}]}
                ],
            }
        ],
    }
    errores = _comprobar_pagina(pagina)
    assert any("más de un nivel" in e for e in errores)


def test_rechaza_bloques_dentro_de_un_tipo_que_no_es_contenedor():
    pagina = {
        "titulo": "X",
        "bloques": [{"tipo": "parrafo", "bloques": [{"tipo": "parrafo", "texto": "a"}]}],
    }
    errores = _comprobar_pagina(pagina)
    assert any("no puede contener" in e for e in errores)


# ---------------------------------------------------------------------------
# Reintentos
# ---------------------------------------------------------------------------


def test_una_pagina_valida_a_la_primera_no_reintenta():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    pagina, tel = generar_pagina(datos_curso=DATOS_CURSO, semana=1, llamador=modelo)
    assert tel["intentos"] == 1
    assert len(modelo.llamadas) == 1
    assert pagina["semana"] == 1


def test_reintenta_y_acierta_al_segundo_intento():
    modelo = ModeloSimulado(
        [
            '{"titulo": "Mala", "bloques": [{"tipo": "smartart"}]}',
            json.dumps(_pagina_valida()),
        ]
    )
    pagina, tel = generar_pagina(datos_curso=DATOS_CURSO, semana=1, llamador=modelo)
    assert tel["intentos"] == 2
    assert pagina["titulo"] == "Semana de prueba"


def test_el_error_concreto_se_le_devuelve_al_modelo_en_el_reintento():
    modelo = ModeloSimulado(
        [
            '{"titulo": "Mala", "bloques": [{"tipo": "smartart"}]}',
            json.dumps(_pagina_valida()),
        ]
    )
    generar_pagina(datos_curso=DATOS_CURSO, semana=1, llamador=modelo)
    segundo_contenido = modelo.llamadas[1][1]
    assert "Corrección necesaria" in segundo_contenido
    assert "smartart" in segundo_contenido


def test_agotar_los_intentos_lanza_error_de_generacion():
    modelo = ModeloSimulado(['{"titulo": "Mala", "bloques": [{"tipo": "smartart"}]}'])
    with pytest.raises(ErrorDeGeneracion, match="tras 3 intentos"):
        generar_pagina(datos_curso=DATOS_CURSO, semana=1, llamador=modelo)
    assert len(modelo.llamadas) == 3


# ---------------------------------------------------------------------------
# Ensamblado: la contabilidad la lleva nuestro código
# ---------------------------------------------------------------------------


def test_todos_los_bloques_reciben_id_y_origen():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    pagina, _ = generar_pagina(datos_curso=DATOS_CURSO, semana=1, llamador=modelo)
    for bloque in pagina["bloques"]:
        assert bloque["id"].startswith("b")
        assert bloque["origen"] == "agente"
    anidado = next(b for b in pagina["bloques"] if b["tipo"] == "focalizador")
    assert anidado["bloques"][0]["id"].startswith("b")
    assert anidado["bloques"][0]["origen"] == "agente"


def test_los_ids_no_se_repiten():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    curso, _tel = generar_guia(DATOS_CURSO, llamador=modelo, validar=_validar_falso)
    ids = [
        b["id"]
        for pagina in paginas(curso)
        for b in ensamblado.bloques_de_pagina(pagina)
    ]
    assert len(ids) == len(set(ids))


def test_las_figuras_se_numeran_correlativas_en_todo_el_curso():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    curso, _tel = generar_guia(DATOS_CURSO, llamador=modelo, validar=_validar_falso)
    numeros = [
        b["numero_figura"]
        for pagina in paginas(curso)
        for b in ensamblado.bloques_de_pagina(pagina)
        if b["tipo"] == "imagen"
    ]
    assert numeros == [1, 2, 3]


def test_estadisticas_cuentan_bloques_anidados():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    curso, _tel = generar_guia(DATOS_CURSO, llamador=modelo, validar=_validar_falso)
    est = curso["estadisticas"]
    # Las cinco cifras que declara el esquema
    assert est["total_paginas"] == 3
    assert est["total_unidades"] == 1
    assert est["total_recursos"] == 3  # una figura por página, dada de alta sola
    # Y el desglose extra, que es el que mide cuánto edita el docente
    assert est["por_tipo"]["parrafo"] == 6  # 1 suelto + 1 anidado, por 3 páginas
    assert est["por_origen"] == {"agente": 15}


# ---------------------------------------------------------------------------
# Guía completa
# ---------------------------------------------------------------------------


def test_genera_una_pagina_por_semana():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    curso, _tel = generar_guia(DATOS_CURSO, llamador=modelo, validar=_validar_falso)
    assert len(paginas(curso)) == 3
    assert [p["semana"] for p in paginas(curso)] == [1, 2, 3]
    assert curso["version_esquema"] == "1.0.0"


def test_la_telemetria_suma_las_tres_llamadas():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    _curso, _tel = generar_guia(DATOS_CURSO, llamador=modelo, validar=_validar_falso)
    assert _tel["tokens_entrada"] == 300
    assert _tel["tokens_salida"] == 750


def test_la_semana_previa_llega_como_contexto_de_la_siguiente():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    generar_guia(DATOS_CURSO, llamador=modelo, validar=_validar_falso)
    primera = modelo.llamadas[0][1]
    segunda = modelo.llamadas[1][1]
    assert "esta es la primera" in primera
    assert "Semana de prueba" in segunda


def test_el_plan_marca_que_semana_cierra_unidad():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    plan = [
        {"semana": 1, "unidad_id": "u1"},
        {"semana": 2, "unidad_id": "u1", "cierra_unidad": True},
    ]
    generar_guia(DATOS_CURSO, plan=plan, llamador=modelo, validar=_validar_falso)
    assert "cierra unidad" not in modelo.llamadas[0][1]
    assert "cierra unidad" in modelo.llamadas[1][1]


def test_la_bibliografia_se_pasa_al_modelo():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    generar_guia(
        DATOS_CURSO,
        bibliografia=["Horngren, C. (2012). Contabilidad de costos."],
        llamador=modelo,
        validar=_validar_falso,
    )
    assert "Horngren" in modelo.llamadas[0][1]


def test_se_llama_al_validador_institucional_una_vez():
    llamadas = []

    def validador_espia(curso):
        llamadas.append(curso)
        return {"semaforo": "amarillo", "alertas": ["algo"]}

    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    curso, _tel = generar_guia(DATOS_CURSO, llamador=modelo, validar=validador_espia)
    assert len(llamadas) == 1
    assert curso["validaciones"]["semaforo"] == "amarillo"


# ---------------------------------------------------------------------------
# Regeneración de una sola semana
# ---------------------------------------------------------------------------


def test_regenerar_solo_cambia_la_semana_pedida():
    modelo = ModeloSimulado([json.dumps(_pagina_valida("Original"))])
    curso, _tel = generar_guia(DATOS_CURSO, llamador=modelo, validar=_validar_falso)
    ids_semana_1 = [b["id"] for b in paginas(curso)[0]["bloques"]]
    ids_semana_3 = [b["id"] for b in paginas(curso)[2]["bloques"]]

    modelo_nuevo = ModeloSimulado([json.dumps(_pagina_valida("Rehecha"))])
    regenerar_pagina(
        curso, 2, datos_curso=DATOS_CURSO, llamador=modelo_nuevo, validar=_validar_falso
    )

    assert paginas(curso)[1]["titulo"] == "Rehecha"
    assert [b["id"] for b in paginas(curso)[0]["bloques"]] == ids_semana_1
    assert [b["id"] for b in paginas(curso)[2]["bloques"]] == ids_semana_3


def test_regenerar_renumera_las_figuras_posteriores():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    curso, _tel = generar_guia(DATOS_CURSO, llamador=modelo, validar=_validar_falso)

    # La semana nueva trae dos imágenes en vez de una.
    pagina_con_dos = _pagina_valida("Con dos figuras")
    pagina_con_dos["bloques"].append({"tipo": "diagrama", "alt": "Otro esquema"})
    modelo_nuevo = ModeloSimulado([json.dumps(pagina_con_dos)])
    regenerar_pagina(
        curso, 1, datos_curso=DATOS_CURSO, llamador=modelo_nuevo, validar=_validar_falso
    )

    numeros = [
        b["numero_figura"]
        for pagina in paginas(curso)
        for b in ensamblado.bloques_de_pagina(pagina)
        if b["tipo"] in ("imagen", "diagrama")
    ]
    assert numeros == [1, 2, 3, 4]


def test_regenerar_una_semana_inexistente_da_error():
    modelo = ModeloSimulado([json.dumps(_pagina_valida())])
    curso, _tel = generar_guia(DATOS_CURSO, llamador=modelo, validar=_validar_falso)
    with pytest.raises(ValueError, match="ninguna semana 9"):
        regenerar_pagina(curso, 9, llamador=modelo, validar=_validar_falso)


# ---------------------------------------------------------------------------
# Ensamblado a pelo
# ---------------------------------------------------------------------------


def test_poner_ids_respeta_los_que_ya_existen():
    bloques = [{"tipo": "parrafo", "id": "bYAEXISTIA", "origen": "docente"}]
    ensamblado.poner_ids_y_origen(bloques, origen="agente")
    assert bloques[0]["id"] == "bYAEXISTIA"
    assert bloques[0]["origen"] == "docente"


def test_origen_invalido_da_error():
    with pytest.raises(ValueError, match="origen no válido"):
        ensamblado.poner_ids_y_origen([{"tipo": "parrafo"}], origen="inventado")
