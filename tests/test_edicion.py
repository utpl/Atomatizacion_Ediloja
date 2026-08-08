"""Pruebas de las operaciones de edición.

Sin base de datos, sin HTTP. Solo dicts. Todo lo difícil de la edición está
aquí: localizar bloques anidados, respetar el anidamiento de un nivel, mover
sin descuadrar índices, renumerar figuras.

    pytest tests/test_edicion.py -v
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.py.edicion.esquemas import (
    ActualizarBloque,
    ActualizarPagina,
    EliminarBloque,
    EliminarPagina,
    InsertarBloque,
    InsertarPagina,
    MoverBloque,
    MoverPagina,
    PeticionEdicion,
)
from libs.py.edicion.operaciones import ErrorDeEdicion, aplicar, localizar_bloque


def curso_base() -> dict:
    """Un curso con la forma REAL del esquema: estructura.paginas, hijos en
    `bloques`, focalizador en el campo `focalizador`."""
    return {
        "version_esquema": "1.0.0",
        "info_general": {"codigo_banner": "CONT1140", "asignatura": "Contabilidad",
                         "periodo": "2026-1", "total_semanas": 2},
        "estructura": {
            "unidades": [{"id": "u1", "numero": 1, "titulo": "Fundamentos"}],
            "paginas": [
                {
                    "id": "p1", "semana": 1, "titulo": "Semana 1", "unidad_id": "u1",
                    "bloques": [
                        {"id": "b111111", "tipo": "encabezado", "nivel": 2,
                         "texto": "Intro", "origen": "agente"},
                        {"id": "b222222", "tipo": "parrafo",
                         "texto": "Uno", "origen": "agente"},
                        {"id": "b333333", "tipo": "caja", "origen": "agente",
                         "bloques": [
                             {"id": "b444444", "tipo": "parrafo",
                              "texto": "Dentro", "origen": "agente"}]},
                        {"id": "b555555", "tipo": "imagen", "recurso_ref": "r1",
                         "alt": "Un esquema", "origen": "agente"},
                    ],
                },
                {
                    "id": "p2", "semana": 2, "titulo": "Semana 2", "unidad_id": "u1",
                    "bloques": [
                        {"id": "b666666", "tipo": "parrafo",
                         "texto": "Dos", "origen": "agente"},
                        {"id": "b777777", "tipo": "imagen", "recurso_ref": "r2",
                         "alt": "Otro esquema", "origen": "agente"},
                    ],
                },
            ],
        },
        "recursos": [
            {"ref": "r1", "tipo": "imagen", "archivo": "r1.png", "mime": "image/png"},
            {"ref": "r2", "tipo": "imagen", "archivo": "r2.png", "mime": "image/png"},
        ],
    }


def paginas(curso):
    return curso["estructura"]["paginas"]


# ---------------------------------------------------------------------------
# Localización
# ---------------------------------------------------------------------------


def test_localiza_un_bloque_de_primer_nivel():
    pagina, lista, i = localizar_bloque(curso_base(), "b222222")
    assert pagina["id"] == "p1"
    assert lista[i]["texto"] == "Uno"


def test_localiza_un_bloque_dentro_de_una_caja():
    pagina, lista, i = localizar_bloque(curso_base(), "b444444")
    assert pagina["id"] == "p1"
    assert lista[i]["texto"] == "Dentro"
    assert len(lista) == 1  # es la lista de hijos de la caja, no la de la página


def test_bloque_inexistente_da_error():
    with pytest.raises(ErrorDeEdicion, match="No existe el bloque"):
        localizar_bloque(curso_base(), "bnoexiste")


# ---------------------------------------------------------------------------
# Actualizar
# ---------------------------------------------------------------------------


def test_actualizar_cambia_solo_los_campos_pedidos():
    nuevo, _ = aplicar(
        curso_base(), [ActualizarBloque(bloque_id="b222222", campos={"texto": "Cambiado"})]
    )
    bloque = paginas(nuevo)[0]["bloques"][1]
    assert bloque["texto"] == "Cambiado"
    assert bloque["tipo"] == "parrafo"  # lo no tocado se conserva


def test_actualizar_un_bloque_de_la_ia_lo_marca_como_mixto():
    nuevo, _ = aplicar(
        curso_base(), [ActualizarBloque(bloque_id="b222222", campos={"texto": "X"})]
    )
    assert paginas(nuevo)[0]["bloques"][1]["origen"] == "mixto"


def test_actualizar_funciona_dentro_de_una_caja():
    nuevo, _ = aplicar(
        curso_base(), [ActualizarBloque(bloque_id="b444444", campos={"texto": "Editado"})]
    )
    assert paginas(nuevo)[0]["bloques"][2]["bloques"][0]["texto"] == "Editado"


def test_no_se_puede_cambiar_el_id():
    with pytest.raises(ErrorDeEdicion, match="id de un bloque no se puede cambiar"):
        aplicar(curso_base(), [ActualizarBloque(bloque_id="b222222", campos={"id": "b99"})])


def test_actualizar_rechaza_html_fuera_de_la_lista_blanca():
    with pytest.raises(ErrorDeEdicion, match="div"):
        aplicar(
            curso_base(),
            [ActualizarBloque(bloque_id="b222222", campos={"texto": "<div>no</div>"})],
        )


def test_actualizar_acepta_html_de_la_lista_blanca():
    nuevo, _ = aplicar(
        curso_base(),
        [ActualizarBloque(bloque_id="b222222", campos={"texto": "<strong>si</strong>"})],
    )
    assert "strong" in paginas(nuevo)[0]["bloques"][1]["texto"]


def test_actualizar_rechaza_tipo_inventado():
    with pytest.raises(ErrorDeEdicion, match="smartart"):
        aplicar(
            curso_base(), [ActualizarBloque(bloque_id="b222222", campos={"tipo": "smartart"})]
        )


def test_actualizar_rechaza_focalizador_fuera_del_enum():
    with pytest.raises(ErrorDeEdicion, match="valor no permitido"):
        aplicar(
            curso_base(),
            [
                ActualizarBloque(
                    bloque_id="b222222", campos={"tipo": "focalizador", "focalizador": "inventada"}
                )
            ],
        )


# ---------------------------------------------------------------------------
# Eliminar
# ---------------------------------------------------------------------------


def test_eliminar_quita_el_bloque():
    nuevo, _ = aplicar(curso_base(), [EliminarBloque(bloque_id="b222222")])
    ids = [b["id"] for b in paginas(nuevo)[0]["bloques"]]
    assert ids == ["b111111", "b333333", "b555555"]


def test_eliminar_dentro_de_una_caja_deja_la_caja():
    nuevo, _ = aplicar(curso_base(), [EliminarBloque(bloque_id="b444444")])
    caja = paginas(nuevo)[0]["bloques"][2]
    assert caja["id"] == "b333333"
    assert caja["bloques"] == []


def test_eliminar_una_caja_se_lleva_los_hijos():
    nuevo, _ = aplicar(curso_base(), [EliminarBloque(bloque_id="b333333")])
    ids = [b["id"] for b in paginas(nuevo)[0]["bloques"]]
    assert "b333333" not in ids
    with pytest.raises(ErrorDeEdicion):
        localizar_bloque(nuevo, "b444444")


def test_eliminar_guarda_el_antes_para_poder_deshacer():
    _, registros = aplicar(curso_base(), [EliminarBloque(bloque_id="b222222")])
    assert registros[0]["antes"]["texto"] == "Uno"
    assert registros[0]["despues"] is None


# ---------------------------------------------------------------------------
# Insertar
# ---------------------------------------------------------------------------


def test_insertar_en_la_posicion_pedida():
    nuevo, _ = aplicar(
        curso_base(),
        [InsertarBloque(pagina_id="p1", indice=1,
                        bloque={"tipo": "parrafo", "texto": "Nuevo"})],
    )
    assert paginas(nuevo)[0]["bloques"][1]["texto"] == "Nuevo"


def test_el_bloque_insertado_recibe_id_y_origen_docente():
    nuevo, registros = aplicar(
        curso_base(),
        [InsertarBloque(pagina_id="p1", indice=0,
                        bloque={"tipo": "parrafo", "texto": "Nuevo"})],
    )
    bloque = paginas(nuevo)[0]["bloques"][0]
    assert bloque["id"].startswith("b")
    assert bloque["origen"] == "docente"
    assert registros[0]["bloque_id"] == bloque["id"]


def test_insertar_dentro_de_una_caja():
    nuevo, _ = aplicar(
        curso_base(),
        [InsertarBloque(pagina_id="p1", indice=1, dentro_de="b333333",
                        bloque={"tipo": "parrafo", "texto": "Segundo hijo"})],
    )
    caja = paginas(nuevo)[0]["bloques"][2]
    assert [h["texto"] for h in caja["bloques"]] == ["Dentro", "Segundo hijo"]


def test_no_se_puede_insertar_dentro_de_algo_que_no_es_contenedor():
    with pytest.raises(ErrorDeEdicion, match="no puede contener"):
        aplicar(
            curso_base(),
            [InsertarBloque(pagina_id="p1", indice=0, dentro_de="b222222",
                            bloque={"tipo": "parrafo", "texto": "X"})],
        )


def test_no_se_puede_insertar_una_caja_dentro_de_una_caja():
    with pytest.raises(ErrorDeEdicion, match="más de un nivel"):
        aplicar(
            curso_base(),
            [
                InsertarBloque(
                    pagina_id="p1", indice=0, dentro_de="b333333",
                    bloque={"tipo": "caja",
                            "bloques": [{"tipo": "parrafo", "texto": "hondo"}]},
                )
            ],
        )


def test_un_indice_pasado_de_largo_inserta_al_final():
    nuevo, _ = aplicar(
        curso_base(),
        [InsertarBloque(pagina_id="p1", indice=999,
                        bloque={"tipo": "parrafo", "texto": "Ultimo"})],
    )
    assert paginas(nuevo)[0]["bloques"][-1]["texto"] == "Ultimo"


def test_insertar_en_pagina_inexistente_da_error():
    with pytest.raises(ErrorDeEdicion, match="No existe la página"):
        aplicar(
            curso_base(),
            [InsertarBloque(pagina_id="pNO", indice=0,
                            bloque={"tipo": "parrafo", "texto": "X"})],
        )


# ---------------------------------------------------------------------------
# Mover
# ---------------------------------------------------------------------------


def test_mover_dentro_de_la_misma_pagina():
    nuevo, _ = aplicar(
        curso_base(), [MoverBloque(bloque_id="b111111", pagina_id="p1", indice=2)]
    )
    assert [b["id"] for b in paginas(nuevo)[0]["bloques"]] == ["b222222", "b333333", "b111111", "b555555"]


def test_mover_a_otra_pagina():
    nuevo, _ = aplicar(
        curso_base(), [MoverBloque(bloque_id="b222222", pagina_id="p2", indice=0)]
    )
    assert [b["id"] for b in paginas(nuevo)[0]["bloques"]] == ["b111111", "b333333", "b555555"]
    assert [b["id"] for b in paginas(nuevo)[1]["bloques"]] == ["b222222", "b666666", "b777777"]


def test_mover_de_dentro_de_una_caja_a_la_pagina():
    nuevo, _ = aplicar(
        curso_base(), [MoverBloque(bloque_id="b444444", pagina_id="p1", indice=0)]
    )
    assert paginas(nuevo)[0]["bloques"][0]["id"] == "b444444"
    assert paginas(nuevo)[0]["bloques"][3]["bloques"] == []


def test_mover_de_la_pagina_a_dentro_de_una_caja():
    nuevo, _ = aplicar(
        curso_base(),
        [MoverBloque(bloque_id="b222222", pagina_id="p1", indice=0, dentro_de="b333333")],
    )
    caja = next(b for b in paginas(nuevo)[0]["bloques"] if b["id"] == "b333333")
    assert [h["id"] for h in caja["bloques"]] == ["b222222", "b444444"]


def test_no_se_puede_meter_una_caja_con_hijos_dentro_de_otra():
    curso = curso_base()
    paginas(curso)[0]["bloques"].append(
        {"id": "b888888", "tipo": "caja", "bloques": [{"id": "b999999", "tipo": "parrafo",
                                                    "texto": "x"}]}
    )
    with pytest.raises(ErrorDeEdicion, match="excedería el anidamiento"):
        aplicar(curso, [MoverBloque(bloque_id="b888888", pagina_id="p1", indice=0,
                                    dentro_de="b333333")])


def test_mover_hacia_adelante_no_descuadra_el_indice():
    """El caso clásico: al quitar el bloque, todo lo de detrás se desplaza."""
    nuevo, _ = aplicar(
        curso_base(), [MoverBloque(bloque_id="b111111", pagina_id="p1", indice=3)]
    )
    assert [b["id"] for b in paginas(nuevo)[0]["bloques"]] == ["b222222", "b333333", "b555555", "b111111"]


# ---------------------------------------------------------------------------
# Operaciones estructurales
# ---------------------------------------------------------------------------


def test_insertar_pagina():
    nuevo, registros = aplicar(
        curso_base(), [InsertarPagina(indice=1, titulo="Tema nuevo del docente", semana=99)]
    )
    assert len(paginas(nuevo)) == 3
    assert paginas(nuevo)[1]["titulo"] == "Tema nuevo del docente"
    
    assert registros[0]["pagina_id"] == paginas(nuevo)[1]["id"]


def test_eliminar_pagina():
    nuevo, _ = aplicar(curso_base(), [EliminarPagina(pagina_id="p1")])
    assert [p["id"] for p in paginas(nuevo)] == ["p2"]


def test_mover_pagina():
    nuevo, _ = aplicar(curso_base(), [MoverPagina(pagina_id="p2", indice=0)])
    assert [p["id"] for p in paginas(nuevo)] == ["p2", "p1"]


def test_actualizar_pagina_cambia_el_titulo():
    nuevo, _ = aplicar(
        curso_base(), [ActualizarPagina(pagina_id="p1", campos={"titulo": "Otro"})]
    )
    assert paginas(nuevo)[0]["titulo"] == "Otro"


def test_actualizar_pagina_no_deja_reemplazar_los_bloques():
    with pytest.raises(ErrorDeEdicion, match="Los bloques no se cambian"):
        aplicar(curso_base(), [ActualizarPagina(pagina_id="p1", campos={"bloques": []})])


# ---------------------------------------------------------------------------
# Lote y transacción
# ---------------------------------------------------------------------------


def test_un_lote_aplica_las_operaciones_en_orden():
    nuevo, registros = aplicar(
        curso_base(),
        [
            EliminarBloque(bloque_id="b222222"),
            InsertarBloque(pagina_id="p1", indice=1,
                           bloque={"tipo": "parrafo", "texto": "Reemplazo"}),
        ],
    )
    assert len(registros) == 2
    assert paginas(nuevo)[0]["bloques"][1]["texto"] == "Reemplazo"


def test_si_falla_una_operacion_no_se_aplica_ninguna():
    original = curso_base()
    with pytest.raises(ErrorDeEdicion, match="Operación 2"):
        aplicar(
            original,
            [
                EliminarBloque(bloque_id="b222222"),
                EliminarBloque(bloque_id="bnoexiste"),
            ],
        )
    # El curso original sigue intacto: la primera operación no se coló.
    assert [b["id"] for b in paginas(original)[0]["bloques"]] == \
        ["b111111", "b222222", "b333333", "b555555"]


def test_el_error_dice_que_operacion_del_lote_fallo():
    with pytest.raises(ErrorDeEdicion, match=r"Operación 3 \(eliminar_bloque\)"):
        aplicar(
            curso_base(),
            [
                ActualizarBloque(bloque_id="b111111", campos={"texto": "a"}),
                ActualizarBloque(bloque_id="b222222", campos={"texto": "b"}),
                EliminarBloque(bloque_id="bnoexiste"),
            ],
        )


# ---------------------------------------------------------------------------
# Recálculos automáticos
# ---------------------------------------------------------------------------


def test_las_figuras_se_renumeran_tras_editar():
    nuevo, _ = aplicar(
        curso_base(),
        [InsertarBloque(pagina_id="p1", indice=0,
                        bloque={"tipo": "diagrama", "alt": "Nuevo diagrama"})],
    )
    numeros = [
        b.get("numero_figura")
        for p in paginas(nuevo)
        for b in p["bloques"]
        if b["tipo"] in ("imagen", "diagrama")
    ]
    assert numeros == [1, 2, 3]


def test_las_estadisticas_se_recalculan():
    nuevo, _ = aplicar(curso_base(), [EliminarBloque(bloque_id="b222222")])
    est = nuevo["estadisticas"]
    # Las cinco cifras que declara el esquema
    assert est["total_paginas"] == 2
    assert est["total_unidades"] == 1
    assert est["total_recursos"] == 2
    assert est["por_origen"] == {"agente": 6}


def test_las_estadisticas_reflejan_lo_que_edito_el_docente():
    nuevo, _ = aplicar(
        curso_base(),
        [
            ActualizarBloque(bloque_id="b111111", campos={"texto": "Editado"}),
            InsertarBloque(pagina_id="p1", indice=0,
                           bloque={"tipo": "parrafo", "texto": "Mío"}),
        ],
    )
    assert nuevo["estadisticas"]["por_origen"] == {
        "agente": 6,   # los que no tocó
        "mixto": 1,    # b1: lo generó la IA y lo editó el docente
        "docente": 1,  # el que insertó de cero
    }


# ---------------------------------------------------------------------------
# El contrato Pydantic
# ---------------------------------------------------------------------------


def test_la_peticion_distingue_las_operaciones_por_su_nombre():
    peticion = PeticionEdicion.model_validate(
        {
            "operaciones": [
                {"operacion": "eliminar_bloque", "bloque_id": "b222222"},
                {"operacion": "mover_pagina", "pagina_id": "p2", "indice": 0},
            ]
        }
    )
    assert isinstance(peticion.operaciones[0], EliminarBloque)
    assert isinstance(peticion.operaciones[1], MoverPagina)


def test_una_operacion_inventada_se_rechaza_en_el_contrato():
    with pytest.raises(ValidationError):
        PeticionEdicion.model_validate(
            {"operaciones": [{"operacion": "formatear_disco"}]}
        )


def test_un_lote_vacio_se_rechaza():
    with pytest.raises(ValidationError):
        PeticionEdicion.model_validate({"operaciones": []})


def test_un_indice_negativo_se_rechaza():
    with pytest.raises(ValidationError):
        PeticionEdicion.model_validate(
            {"operaciones": [{"operacion": "mover_pagina", "pagina_id": "p1",
                              "indice": -1}]}
        )
