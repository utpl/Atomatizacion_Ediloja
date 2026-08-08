#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agente_contextualizacion.py — Agente A1 del migrador (adaptado del pipeline
viejo curar_contextualizaciones.py, cuyos prompts ya estaban probados).

Árbol de decisión POR SEMANA del curso nuevo:

  · RA ÚNICO con contextualización vieja  → el agente la REVISA:
        Escenario 2: válida → se CONSERVA intacta.
        Escenario 3: es bienvenida/lista de temas → GENERA nueva
                     (+ texto_reubicado para el revisor).
  · RA ÚNICO sin contextualización        → Escenario 1: GENERA desde cero.
  · 2+ RA UNIDOS                          → Escenario 4: GENERA OBLIGATORIAMENTE
        una contextualización CONJUNTO usando las viejas de esos RA como fuente.
  · Mismos RA que una semana anterior     → se REUTILIZA la generada (0 llamadas).

Requiere: pip install anthropic  +  variable ANTHROPIC_API_KEY.
"""
import os
import re
import time

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

MODELO_DEFAULT = os.environ.get('AGENTE_MODELO', 'claude-sonnet-4-5')
PRECIO_IN_POR_M = 3.0
PRECIO_OUT_POR_M = 15.0
MAX_REINTENTOS = 2

SYSTEM_PROMPT = """Asume el rol de un Diseñador Instruccional Experto y Auditor Pedagógico para educación superior de pregrado. Tu tarea es analizar los Resultados de Aprendizaje (RA) de una semana académica y verificar que cuenten con su respectiva "Contextualización".

ÁRBOL DE DECISIÓN:

[ESCENARIO 1: NO EXISTE Contextualización para este RA (el campo está vacío)]
- GENERA desde cero la contextualización para ese RA.
- Lineamiento: Redacta un párrafo amplio, fluido y motivador que inicie obligatoriamente con la frase "Para alcanzar este resultado de aprendizaje...". Debe explicar de manera directa cómo el estudiante logrará dicha competencia.
- Estilo Formal SIN tutear: PROHIBIDO usar "comprendas", "aprenderás", "te dará". Use formalidad estricta: "comprenda", "aprenderá", "le proporcionará".
- Enfoque exclusivo en el RA: PROHIBIDO referir tiempo, "semanas", "bloques", "módulos" o similares.
- Puntuación: PROHIBIDO guiones largos (—) o cortos (-) para incisos. Use comas o paréntesis.

[ESCENARIO 2: SÍ EXISTE Contextualización VÁLIDA para este RA]
- Si el docente redactó un texto que hace referencia al logro o beneficio del RA, consérvalo INTACTO.
- No alteres su redacción ni su extensión.

[ESCENARIO 3: EXISTE Texto del Docente pero es BIENVENIDA / INTRODUCCIÓN TEMÁTICA]
- Si el texto se limita a dar la bienvenida o a listar los temas, NO califica como contextualización.
- Acción:
  1. GENERA una nueva contextualización para el RA (reglas Escenario 1).
  2. Devuelve el texto original del docente en `texto_reubicado`, RESPETANDO todos sus saltos de línea originales. Cada oración, viñeta o bloque debe mantener exactamente los saltos con los que ingresó. Prohibido resumir o usar puntos suspensivos.

[ESCENARIO 4: la semana UNE DOS O MÁS RA (se te indicará explícitamente)]
- La generación es OBLIGATORIA aunque existan contextualizaciones previas: al unirse los RA, ninguna contextualización individual queda acorde.
- GENERA UNA sola contextualización que sea el CONJUNTO de todas las contextualizaciones fuente entregadas, cubriendo todos los RA de la semana sin enumerarlos mecánicamente.
- Inicia obligatoriamente con la frase "Para alcanzar estos resultados de aprendizaje...".
- Aplican las mismas reglas de estilo del Escenario 1 (formalidad sin tutear, sin referencias temporales, sin guiones para incisos).

DEBES devolver tu análisis usando la herramienta `registrar_contextualizacion`."""

TOOL_REGISTRAR = {
    "name": "registrar_contextualizacion",
    "description": "Registra el análisis del RA según el escenario detectado.",
    "input_schema": {
        "type": "object",
        "properties": {
            "escenario": {
                "type": "integer",
                "enum": [1, 2, 3, 4],
                "description": "1: vacía (generar). 2: válida (conservar). 3: bienvenida (generar nueva + reubicar). 4: RAs unificados (generar conjunto, obligatorio)."
            },
            "contextualizacion": {
                "type": "string",
                "description": "Escenarios 1, 3 y 4: la NUEVA contextualización. Escenario 2: el texto INTACTO del docente."
            },
            "texto_reubicado": {
                "type": "string",
                "description": "Solo Escenario 3: texto del docente para reubicar. Otros: cadena vacía."
            },
            "comentario_auditoria": {
                "type": "string",
                "description": "Escenarios 1, 3 y 4: el mensaje PREV para el docente. Otros: cadena vacía."
            }
        },
        "required": ["escenario", "contextualizacion", "texto_reubicado", "comentario_auditoria"]
    }
}


def _texto_plano(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html or '')).strip()


def construir_bloque_entrada(ras, contextos, semana):
    """ras: lista de textos de RA de la semana nueva.
    contextos: lista paralela con la contextualización vieja de cada RA
    (texto plano, o None)."""
    b = []
    if len(ras) > 1:
        b.append(f"NOTA: Esta semana UNE {len(ras)} Resultados de Aprendizaje (ESCENARIO 4).")
        b.append("La generación de UNA contextualización conjunto es OBLIGATORIA.")
        b.append("")
        for i, (ra, ctx) in enumerate(zip(ras, contextos), 1):
            b.append(f"RA {i}: {ra.strip()}")
            if ctx:
                b.append(f"Contextualización fuente del RA {i} (curso anterior):")
                b.append(ctx.strip())
            else:
                b.append(f"El RA {i} no tenía contextualización en el curso anterior.")
            b.append("")
    else:
        b.append("Resultado de Aprendizaje (RA) a analizar:")
        b.append(ras[0].strip())
        b.append("")
        if contextos and contextos[0]:
            b.append("Texto encontrado bajo el marcador 'Contextualización' (curso anterior):")
            b.append(contextos[0].strip())
        else:
            b.append("El bloque 'Contextualización' está VACÍO. El docente no escribió texto.")
    b.append("")
    b.append(f"Etiqueta temporal: {semana}")
    return "\n".join(b)


def llamar_agente(client, modelo, bloque_entrada, max_reintentos=MAX_REINTENTOS):
    for intento in range(max_reintentos + 1):
        try:
            resp = client.messages.create(
                model=modelo,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                tools=[TOOL_REGISTRAR],
                tool_choice={"type": "tool", "name": "registrar_contextualizacion"},
                messages=[{"role": "user",
                           "content": "INFORMACIÓN DE ENTRADA PARA ANALIZAR:\n\n" + bloque_entrada}],
            )
            tin = resp.usage.input_tokens
            tout = resp.usage.output_tokens
            costo = tin / 1_000_000 * PRECIO_IN_POR_M + tout / 1_000_000 * PRECIO_OUT_POR_M
            for block in resp.content:
                if block.type == "tool_use" and block.name == "registrar_contextualizacion":
                    return block.input, tin, tout, costo
            raise ValueError("No se encontró tool_use en la respuesta")
        except Exception as e:
            if intento < max_reintentos:
                time.sleep(2 ** intento)
                continue
            raise


def validar(contextualizacion, escenario):
    """Validación probada del pipeline viejo, extendida al escenario 4."""
    avisos = []
    if escenario not in (1, 3, 4):
        return avisos
    ctx_lower = contextualizacion.lower()
    frase = ("para alcanzar estos resultados de aprendizaje" if escenario == 4
             else "para alcanzar este resultado de aprendizaje")
    if not ctx_lower.startswith(frase):
        avisos.append("NO inicia con la frase obligatoria")
    if "—" in contextualizacion:
        avisos.append("contiene guión largo prohibido")
    for palabra in ("semana", "semanas", "bloque", "bloques", "módulo", "módulos"):
        if re.search(r"\b" + palabra + r"\b", ctx_lower):
            avisos.append(f"palabra prohibida '{palabra}'")
            break
    return avisos


def procesar_plan(plan, canvas, gc, modelo=MODELO_DEFAULT, log=lambda *a: None):
    """Recorre las semanas del plan del MIGRADOR y resuelve la
    contextualización de cada una según el árbol de decisión.
    Devuelve (resultados, resumen). resultados[semana] = {
        'escenario', 'contextualizacion' (HTML <p>), 'conservada',
        'reusada_de', 'texto_reubicado', 'comentario', 'avisos' }"""
    if Anthropic is None:
        raise RuntimeError("Falta la librería 'anthropic' (pip install anthropic)")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Falta la variable de entorno ANTHROPIC_API_KEY")
    client = Anthropic()

    _, ctx_por_ra = gc._material_viejo(canvas)
    ras_txt, _, _ = gc._indices_canvas(canvas)
    txt_a_num = {(t or '').strip().lower(): n for n, t in ras_txt.items()}

    resultados, grupos = {}, {}
    tin_t = tout_t = 0
    costo_t = 0.0
    llamadas = 0

    for sem, d in plan['semanas'].items():
        ras = d.get('resultados_aprendizaje') or []
        if not ras:
            continue
        nums = [txt_a_num.get((r or '').strip().lower()) for r in ras]
        clave = tuple(sorted(n for n in nums if n)) or tuple(sorted(r.strip().lower() for r in ras))

        # mismos RA que una semana anterior → reutilizar (0 llamadas)
        if clave in grupos:
            origen = grupos[clave]
            resultados[sem] = dict(resultados[origen])
            resultados[sem]['reusada_de'] = origen
            log(f"  {sem}: reutiliza la contextualización de {origen} (mismos RA)")
            continue

        contextos = [_texto_plano(ctx_por_ra.get(n)) if n and ctx_por_ra.get(n) else None
                     for n in nums]
        bloque = construir_bloque_entrada(ras, contextos, sem)
        log(f"  {sem}: {'ESCENARIO 4 (RA unidos)' if len(ras) > 1 else 'revisión de RA único'}…")
        salida, tin, tout, costo = llamar_agente(client, modelo, bloque)
        llamadas += 1
        tin_t += tin; tout_t += tout; costo_t += costo

        esc = int(salida.get('escenario') or (4 if len(ras) > 1 else 1))
        if len(ras) > 1:
            esc = 4  # la unión manda: generación obligatoria
        texto = (salida.get('contextualizacion') or '').strip()
        avisos = validar(texto, esc)
        parrafos = ''.join(f'<p>{p.strip()}</p>' for p in texto.split('\n') if p.strip())
        resultados[sem] = {
            'escenario': esc,
            'contextualizacion': parrafos or f'<p>{texto}</p>',
            'conservada': esc == 2,
            'reusada_de': None,
            'texto_reubicado': (salida.get('texto_reubicado') or '').strip(),
            'comentario': (salida.get('comentario_auditoria') or '').strip(),
            'avisos': avisos,
        }
        grupos[clave] = sem

    resumen = {'llamadas': llamadas, 'tokens_in': tin_t, 'tokens_out': tout_t,
               'costo_usd': round(costo_t, 4), 'modelo': modelo}
    return resultados, resumen
