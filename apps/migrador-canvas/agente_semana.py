#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agente_semana.py — Agente A3 del migrador: INTRODUCCIÓN Y CIERRE DE SEMANA.

"Agente IA de Consolidación y Optimización Semanal (Introducciones y Cierres)"
del Rediseño 3 — Aprobado y Listo para Producción. El SYSTEM_PROMPT de abajo
es el prompt oficial entregado por el equipo, VERBATIM: no modificarlo sin
acta de reunión.

Por cada semana del plan:
  · Escenario 1 (Fusión y Consolidación): hay textos introductorios previos
    del docente → un único párrafo consolidado, directo y corto.
  · Escenario 2 (Generación desde Cero): no hay textos → introducción
    generada desde el índice de temas, sin listar los subtemas.
  · El CIERRE siempre lo genera el agente (el docente nunca lo proporciona),
    más corto que la introducción y sin repetir sus conceptos.

La salida del modelo sigue la ESTRUCTURA DE SALIDA OBLIGATORIA del prompt
(texto con encabezados), que aquí se parsea; no se usa tool_use porque el
prompt aprobado define su propio formato de respuesta.

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

# ═══ PROMPT OFICIAL (VERBATIM — Informe Técnico, Rediseño 3) ═══
SYSTEM_PROMPT = """Asume el rol de un Diseñador Instruccional Experto y Auditor Pedagógico para educación superior de pregrado. Tu tarea es analizar y procesar los componentes textuales de una semana académica modularizada dentro de una estructura de código o JSON para generar exclusivamente dos elementos requeridos por la nueva interfaz del metacurso en Canvas LMS: un único párrafo introductorio optimizado y un párrafo de cierre conclusivo.

CONTEXTO DEL PROCESO DIDÁCTICO:
Las asignaturas se están transformando de un modelo de 16 semanas a un modelo modular de 8 semanas, lo que implica la fusión de contenidos y temas. El diseño final en la plataforma Canvas LMS exige que cada semana inicie con el título de la unidad, seguido inmediatamente por un único texto introductorio corto, luego los temas desglosados en pestañas interactivas (tabs) y finalice la semana con un párrafo de cierre.

INSTRUCCIONES DE DIAGNÓSTICO Y PROCESAMIENTO (ÁRBOL DE DECISIÓN):

Analiza los metadatos, el índice de temas y los textos introductorios disponibles para la semana en evaluación. Actúa bajo uno de los siguientes dos escenarios para estructurar la Salida Principal:

[ESCENARIO 1: EXISTEN TEXTOS INTRODUCTORIOS PREVIOS (Fusión y Consolidación)]
- Este escenario se activa si la semana actual es el resultado de la unión de dos o más semanas antiguas y el documento base de entrada provee los párrafos de bienvenida o introducciones que el docente utilizaba originalmente de forma dispersa.
- Acción Instruccional: Toma todos los textos introductorios originales provistos. Redacta un único párrafo consolidado, sumamente directo y corto, que unifique la esencia del autor sin expandir el contenido ni agregar enfoques externos. El docente es el experto.

[ESCENARIO 2: NO EXISTEN TEXTOS INTRODUCTORIOS (Generación desde Cero)]
- Este escenario se activa si la semana en evaluación no cuenta con ningún párrafo de bienvenida, introducción o texto de presentación previo.
- Acción Instruccional: El agente debe leer el índice de temas asignado a esa semana y, con base en su naturaleza temática general, generar desde cero un párrafo introductorio fluido, cordial y sintético.

REGLAS DE REDACCIÓN Y ESTILO PARA LA IA (ESTRICTAS PARA AMBOS ESCENARIOS):

1. Restricción de Extensión, Enfoque y Concisión (Evitar Objeciones del Experto):
   - La Introducción debe constar de un único párrafo corto, directo y conciso. Su función es presentar de manera cordial el campo de estudio general, alineándose estrictamente al enfoque del autor sin profundizar en contenidos, teorías ni conceptos avanzados.
   - El Cierre debe ser un único párrafo corto, obligatoriamente más conciso que la introducción. Su función es retroalimentar y concluir la semana de forma precisa.

2. Prohibición Absoluta de Listados Temáticos en la Introducción:
   - Queda terminantemente PROHIBIDO que el párrafo introductorio liste o mencione uno a uno los subtemas que se van a revisar (ej. "se revisará el tema 1.1, luego el 1.2..."). Dado que los temas ya aparecen debajo en formato de pestañas (tabs), la introducción debe ser una redacción fluida sobre el objeto de estudio general, nunca un índice textual.

3. Prohibición Absoluta de Términos de Transición Temporal, Fusión o Ubicación Cronológica:
   - Queda terminantemente PROHIBIDO mencionar que las semanas se unificaron, fusionaron o combinaron. El curso debe leerse como un producto totalmente nuevo y orgánico.
   - Queda estrictamente PROHIBIDO usar la palabra "bloque" en cualquier contexto (ej. "bloque unificado", "en este bloque", "bloque de contenido").
   - Queda estrictamente PROHIBIDO hacer alusión a la temporalidad u orden cronológico de la asignatura (evitar frases como "etapas iniciales", "etapas finales", "mitad del ciclo", "semana unificada", "en esta primera etapa" o similares) para garantizar que la lógica funcione idénticamente en cualquier semana del ciclo sin inducir a errores temporales. Se debe hablar de manera natural utilizando únicamente los términos institucionales: "semana" y "unidad".

4. Variabilidad en el Inicio de la Redacción (Evitar Plantillas):
   - Queda prohibido que todas las semanas inicien con la palabra "Bienvenido" o "Estimado estudiante". Si el texto original del docente lo incluye (Escenario 1) se puede respetar de forma esporádica, pero el agente debe variar sistemáticamente la apertura de la redacción entre semanas (ej. iniciar directo con la acción, con el objeto de estudio o con frases de contextualización profesional).

5. No Redundancia en el Cierre:
   - El párrafo de cierre SIEMPRE será generado desde cero por el agente (el docente nunca lo proporciona). Debe redactarse cuidando rigurosamente no repetir los conceptos, verbos o frases exactas utilizadas en el párrafo introductorio. Debe enfocarse en la trascendencia general de los temas vistos y conectar con la práctica real.

6. Restricción Formal (Sin tuteo) y Signos de Puntuación Prohibidos:
   - Emplea estrictamente la tercera persona formal (ej. "comprenda", "aprenderá", "le permitirá"). Queda prohibido tutear al estudiante.
   - Queda TERMINANTEMENTE PROHIBIDO el uso de guiones largos (—) o guiones cortos (-) para introducir incisos, frases aclaratorias o ideas secundarias. Su uso evidencia generación artificial y degrada el diseño instruccional. En su lugar, utilice estrictamente comas o paréntesis.

ESTRUCTURA DE SALIDA OBLIGATORIA (RESPUESTA LIMPIA PARA API - SIN AUDITORÍA):

### SALIDA PRINCIPAL
**Nueva Introducción de la Semana:**
[Inserte aquí el único párrafo generado o consolidado por la IA]

**Nuevo Cierre de la Semana:**
[Inserte aquí el párrafo corto de cierre generado por la IA]"""

RE_SALIDA = re.compile(
    r'\*\*Nueva Introducci[oó]n de la Semana:\*\*\s*(.*?)\s*'
    r'\*\*Nuevo Cierre de la Semana:\*\*\s*(.*)', re.S)


RE_CODIGO_TEMA = re.compile(r'^\s*(\d+(?:\.\d+)*)')


def _rango_temas(indice_temas):
    """'(1.1 al 2.2)' segun los temas consolidados en la semana.

    A diferencia del homonimo de generar_curso.py (que recibe dicts con
    clave 'codigo'), aqui el indice llega como lista de cadenas
    "1.1 Titulo del tema", asi que el codigo se extrae del inicio de cada
    linea. Las entradas sin codigo numerico se ignoran.
    """
    cods = []
    for t in indice_temas or []:
        m = RE_CODIGO_TEMA.match(str(t))
        if m:
            cods.append(m.group(1))
    if not cods:
        return ''
    if len(cods) == 1:
        return f'({cods[0]})'
    return f'({cods[0]} al {cods[-1]})'


def construir_bloque_entrada(indice_temas, fuentes, unidad=None):
    """Estructura de entrada tal como la define el prompt oficial."""
    b = ["INFORMACIÓN DE ENTRADA PARA ANALIZAR:"]
    if unidad:
        b.append(f"- Unidad que se introduce: {unidad}")
    rango = _rango_temas(indice_temas)
    if rango:
        b.append(f"- Alcance de la semana: temas {rango} (incluye sus subtemas)")
    b.append("- Índice de temas de la semana (con subtemas):")
    for t in indice_temas:
        b.append(f"    · {t}")
    if fuentes:
        b.append(f"- Textos introductorios disponibles ({len(fuentes)}):")
        for i, f in enumerate(fuentes, 1):
            b.append(f"    [Texto {i}] {f.strip()}")
    else:
        b.append("- Textos introductorios disponibles (si existen): NINGUNO "
                 "(no existe párrafo de bienvenida ni presentación previa: ESCENARIO 2)")
    return "\n".join(b)


def llamar_agente(client, modelo, bloque_entrada, max_reintentos=MAX_REINTENTOS):
    for intento in range(max_reintentos + 1):
        try:
            resp = client.messages.create(
                model=modelo,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": bloque_entrada}],
            )
            tin = resp.usage.input_tokens
            tout = resp.usage.output_tokens
            costo = tin / 1_000_000 * PRECIO_IN_POR_M + tout / 1_000_000 * PRECIO_OUT_POR_M
            texto = ''.join(b.text for b in resp.content if b.type == 'text')
            m = RE_SALIDA.search(texto)
            if not m:
                raise ValueError("La respuesta no siguió la ESTRUCTURA DE SALIDA OBLIGATORIA")
            intro = m.group(1).strip().strip('[]').strip()
            cierre = m.group(2).strip().strip('[]').strip()
            cierre = re.sub(r'^#+.*$', '', cierre, flags=re.M).strip()
            return intro, cierre, tin, tout, costo
        except Exception:
            if intento < max_reintentos:
                time.sleep(2 ** intento)
                continue
            raise


def validar(intro, cierre):
    """Controles duros derivados de las reglas del prompt oficial."""
    avisos = []
    for nombre, texto in (('introducción', intro), ('cierre', cierre)):
        if not texto:
            avisos.append(f"{nombre} vacío")
            continue
        if '—' in texto:
            avisos.append(f"{nombre}: contiene guión largo prohibido")
        t = texto.lower()
        if re.search(r'\bbloques?\b', t):
            avisos.append(f"{nombre}: palabra prohibida 'bloque'")
        if re.search(r'unificad|fusionad|combinad', t):
            avisos.append(f"{nombre}: alude a la fusión de semanas")
        if re.search(r'etapas?\s+(inicial|final)|mitad\s+del\s+ciclo|primera\s+etapa', t):
            avisos.append(f"{nombre}: alusión cronológica prohibida")
        if re.search(r'\b(tú|tienes|puedes|aprenderás|comprendas|conocerás)\b', t):
            avisos.append(f"{nombre}: tutea al estudiante")
        if re.search(r'\btemas?\s+\d+\.\d+', t):
            avisos.append(f"{nombre}: lista subtemas por código")
    if intro and cierre and len(cierre) >= len(intro):
        avisos.append("el cierre debe ser más conciso que la introducción")
    return avisos


def _texto_plano(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html or '')).strip()


def estado_plan(plan, canvas, gc):
    """Qué datos usaría el agente en cada semana, SIN llamar al modelo:
    semanas antiguas de origen, frases de inicio de cada una, índice de temas
    y si corresponde aplicar IA (solo cuando se unen semanas).
    Es lo que el revisor ve y confirma antes de generar."""
    ras = {r for d in (plan.get('semanas') or {}).values()
           for r in (d.get('resultados_aprendizaje') or [])}
    frases_sem = _frases_inicio_semana(canvas, gc, ras)
    estado = {}
    for sem, d in (plan.get('semanas') or {}).items():
        indice, origen = [], []
        for t in (d.get('temas') or []):
            if t.get('accion') == 'del':
                continue
            cod = (t.get('codigo') or '')
            indice.append(f"{cod} {t.get('titulo') or ''}".strip())
            ns = gc._num_semana(t.get('semana_canvas'))
            if ns and ns not in origen:
                origen.append(ns)
        if not indice:
            continue
        origen.sort()
        estado[sem] = {
            'aplica_ia': len(origen) > 1,
            'semanas_origen': origen,
            'fuentes': [{'semana': n, 'texto': frases_sem.get(n) or ''} for n in origen],
            'indice': indice,
        }
    return estado


def procesar_plan(plan, canvas, gc, modelo=MODELO_DEFAULT, log=lambda *a: None):
    """Genera la INTRODUCCIÓN y el CIERRE de cada semana según las reglas
    aprobadas (Observaciones ADMI_4038):

      · Se UNEN semanas antiguas  → "Aplicar IA por unión de semanas":
        el agente consolida las frases de inicio de esas semanas más el
        índice de temas, y genera también el cierre.
      · NO se unen semanas        → "No aplicar IA porque no se unen semanas":
        la introducción del docente se mantiene TAL CUAL y el cierre usa la
        frase por defecto (no se llama al agente).
      · Las introducciones de UNIDAD ("Se mantiene texto intro Unidad N") no
        las toca el agente: son del docente y se conservan.

    Devuelve (resultados, resumen). resultados[semana] = {
        'introduccion', 'cierre', 'aplica_ia', 'escenario', 'semanas_origen',
        'fuentes': [textos usados], 'indice': [temas usados], 'avisos'}"""
    if Anthropic is None:
        raise RuntimeError("Falta la librería 'anthropic' (pip install anthropic)")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Falta la variable de entorno ANTHROPIC_API_KEY")
    client = Anthropic()

    ras = {r for dd in (plan.get('semanas') or {}).values()
           for r in (dd.get('resultados_aprendizaje') or [])}
    frases_sem = _frases_inicio_semana(canvas, gc, ras)   # frases limpias por semana vieja
    resultados = {}
    tin_t = tout_t = 0
    costo_t = 0.0
    llamadas = 0

    for sem, d in (plan.get('semanas') or {}).items():
        indice, origen = [], []
        for t in (d.get('temas') or []):
            if t.get('accion') == 'del':
                continue
            cod = (t.get('codigo') or '')
            indice.append(f"{cod} {t.get('titulo') or ''}".strip())
            ns = gc._num_semana(t.get('semana_canvas'))
            if ns and ns not in origen:
                origen.append(ns)
        if not indice:
            continue
        origen.sort()

        # ¿se unen semanas antiguas en esta semana nueva?
        une = len(origen) > 1
        fuentes = [frases_sem[n] for n in origen if frases_sem.get(n)]

        if not une:
            # "No aplicar IA porque no se unen semanas": intro del docente tal
            # cual y cierre con la frase por defecto
            log(f"  {sem}: no se unen semanas (S{origen[0] if origen else '?'}) "
                "→ intro del docente tal cual y cierre por defecto")
            resultados[sem] = {
                'aplica_ia': False,
                'introduccion': '', 'cierre': '',
                'escenario': 0,
                'semanas_origen': origen,
                'fuentes': fuentes,
                'indice': indice,
                'avisos': [],
            }
            continue

        log(f"  {sem}: une S{', S'.join(str(n) for n in origen)} → "
            f"{len(indice)} temas, {len(fuentes)} frase(s) de inicio…")
        intro, cierre, tin, tout, costo = llamar_agente(
            client, modelo, construir_bloque_entrada(indice, fuentes))
        llamadas += 1
        tin_t += tin; tout_t += tout; costo_t += costo
        avisos = validar(intro, cierre)
        resultados[sem] = {
            'aplica_ia': True,
            'introduccion': f'<p>{intro}</p>' if intro else '',
            'cierre': f'<p>{cierre}</p>' if cierre else '',
            'escenario': 1 if fuentes else 2,
            'semanas_origen': origen,
            'fuentes': fuentes,
            'indice': indice,
            'avisos': avisos,
        }

    # el consumo (llamadas, tokens, costo) se registra para uso interno pero no
    # se envia al navegador: es informacion operativa, no del usuario final
    log(f'  [interno] {llamadas} llamada(s), {tin_t}+{tout_t} tokens, '
        f'${round(costo_t, 4)}')
    resumen = {'semanas': llamadas, 'modelo': modelo}
    return resultados, resumen


def _frases_inicio_semana(canvas, gc, ras_curso=()):
    """Introduccion de SEMANA de cada semana antigua: el texto que va ENCIMA
    del encabezado "Unidad N." (lo que va debajo es la introduccion de UNIDAD
    y no se toca). Reutiliza la extraccion del generador para que lo que ve el
    agente sea exactamente lo mismo que se coloca cuando no se unen semanas."""
    return {n: _texto_plano(h)
            for n, h in gc._intros_semana_viejas(canvas, ras_curso).items()}