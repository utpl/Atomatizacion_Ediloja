#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agente_autoevaluacion.py — Agente A4 del migrador: AUTOEVALUACIONES INTERACTIVAS.

Genera la autoevaluación de una semana como HTML interactivo propio, sin
depender de herramientas externas (Genially u otras). Esto resuelve dos
problemas del flujo anterior:

  · El contenido dejaba de estar bajo control de la institución: vivía en el
    servidor de un tercero y solo se enlazaba con un <iframe>.
  · No se podía cambiar una sola pregunta sin rehacer el recurso completo a
    mano en la herramienta de origen.

REGLA DE ORO (acordada con el equipo):
  · Si el revisor NO toca nada, se conserva el recurso original tal cual.
    Este agente no se ejecuta y el <iframe> se traslada sin cambios.
  · Solo cuando el revisor edita o solicita regenerar, el agente produce una
    autoevaluación nueva que SUSTITUYE al recurso anterior en la pestaña
    Autoevaluación de esa semana.

El HTML generado es autónomo: preguntas de opción múltiple con validación y
retroalimentación, sin dependencias externas ni JavaScript de terceros. Usa
las clases de la plantilla oficial para heredar el estilo del tema de Canvas.

Requiere: pip install anthropic  +  variable ANTHROPIC_API_KEY.
"""
import os
import re
import json
import time

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

MODELO_DEFAULT = os.environ.get('AGENTE_MODELO', 'claude-sonnet-4-5')
PRECIO_IN_POR_M = 3.0
PRECIO_OUT_POR_M = 15.0
MAX_REINTENTOS = 2

N_PREGUNTAS_DEFECTO = 5

SYSTEM_PROMPT = """Eres un Diseñador Instruccional Experto en evaluación formativa \
para educación superior de pregrado, modalidad en línea.

Tu tarea es redactar las preguntas de una AUTOEVALUACIÓN de repaso a partir del \
contenido académico de una semana de estudio. La autoevaluación es formativa: su \
propósito es que el estudiante compruebe su comprensión y reciba retroalimentación, \
no calificarlo.

REGLAS DE CONTENIDO:
1. Las preguntas se basan EXCLUSIVAMENTE en el contenido proporcionado. No \
introduzcas temas, teorías ni datos que no aparezcan en el material.
2. Evalúa comprensión y aplicación, no memorización literal. Evita preguntas que \
se respondan reconociendo una frase textual.
3. Cubre los distintos temas del material de forma equilibrada; no concentres \
todas las preguntas en un solo apartado.
4. Cada pregunta tiene cuatro opciones y una sola respuesta correcta.
5. Los distractores deben ser verosímiles y del mismo orden de magnitud que la \
respuesta correcta. Nada de opciones absurdas o de relleno.
6. La retroalimentación explica POR QUÉ la respuesta correcta lo es, en una o dos \
frases. No se limita a repetir la opción.

REGLAS DE REDACCIÓN:
- Trato de usted, nunca tuteo.
- Español neutro, claro y profesional.
- Sin guiones largos como recurso de puntuación.
- No uses "bloque", "módulo semanal" ni alusiones al proceso de migración.
- El enunciado debe entenderse sin haber leído las opciones.

FORMATO DE SALIDA OBLIGATORIO:
Responde ÚNICAMENTE con un objeto JSON válido, sin texto antes ni después, sin \
markdown y sin bloques de código. Estructura exacta:

{"preguntas":[{"enunciado":"...","opciones":["...","...","...","..."],\
"correcta":0,"retroalimentacion":"..."}]}

El campo "correcta" es el índice (0 a 3) de la opción correcta dentro del arreglo \
"opciones"."""


# ---------------------------------------------------------------------------
# Construcción de la entrada
# ---------------------------------------------------------------------------
RE_TAGS = re.compile(r'<[^>]+>')


def _texto_plano(html, limite=14000):
    """HTML → texto legible para el modelo (sin etiquetas ni recursos)."""
    if not html:
        return ''
    t = re.sub(r'<(script|style|iframe)[^>]*>.*?</\1>', ' ', html,
               flags=re.S | re.I)
    t = RE_TAGS.sub(' ', t)
    t = (t.replace('&nbsp;', ' ').replace('&aacute;', 'á').replace('&eacute;', 'é')
          .replace('&iacute;', 'í').replace('&oacute;', 'ó').replace('&uacute;', 'ú')
          .replace('&ntilde;', 'ñ').replace('&amp;', '&').replace('&quot;', '"')
          .replace('&ldquo;', '"').replace('&rdquo;', '"'))
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:limite]


RE_OPCION = re.compile(r'^\s*([a-e])[\.\)]\s*(.+)$', re.I)


def extraer_banco_por_autoevaluacion(html):
    """Compatibilidad: delega en banco_preguntas.extraer_banco().

    El procesamiento real vive ahora en banco_preguntas.py, con una fuente
    unica de verdad (el solucionario se DERIVA del banco). Esta funcion se
    conserva porque el resto del sistema espera el formato de diccionarios.
    """
    try:
        import banco_preguntas as bp
    except ImportError:
        return _extraer_banco_legacy(html)
    bancos = bp.extraer_banco(html)
    out = {}
    for n, b in bancos.items():
        out[n] = [{'enunciado': p.enunciado, 'opciones': p.opciones,
                   'correcta': (p.correctas[0] if p.correctas else None),
                   'retroalimentacion': p.retroalimentacion,
                   'id': p.id, 'numero': p.numero, 'tipo': p.tipo,
                   'avisos': p.avisos}
                  for b_ in [b] for p in b_.preguntas]
    return out


def _extraer_banco_legacy(html):
    """Banco COMPLETO de la página "Autoevaluaciones" del curso antiguo.

    Esa página no la ven los estudiantes: es la fuente con la que se generaba
    la guía. Contiene, por cada autoevaluación:
      · <div id="autoevaluacion_N"> con las preguntas y sus opciones
      · <table id="solucionario_N"> con la respuesta correcta (a/b/c) y la
        retroalimentación ya redactada por el docente

    Devuelve {N: [{'enunciado','opciones','correcta','retroalimentacion'}]}
    con la respuesta correcta YA resuelta, de modo que el agente no tenga que
    deducirla: se conserva el criterio del docente.
    """
    if not html:
        return {}
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}
    sopa = BeautifulSoup(html, 'html.parser')

    # 1) soluciones: {N: {n_pregunta: (letra, retroalimentacion)}}
    soluciones = {}
    for tabla in sopa.find_all('table', id=re.compile(r'^solucionario_(\d+)$')):
        n = int(re.search(r'(\d+)$', tabla.get('id')).group(1))
        filas = {}
        for tr in tabla.find_all('tr'):
            celdas = tr.find_all('td')
            if len(celdas) < 3:
                continue
            num = (celdas[0].get_text(' ') or '').strip()
            letra = (celdas[1].get_text(' ') or '').strip().lower()
            retro = re.sub(r'\s+', ' ', celdas[2].get_text(' ')).strip()
            if num.isdigit() and re.match(r'^[a-e]$', letra):
                filas[int(num)] = (letra, retro)
        if filas:
            soluciones[n] = filas

    # 2) preguntas por autoevaluacion
    banco = {}
    for div in sopa.find_all('div', id=re.compile(r'^autoevaluacion_(\d+)$')):
        n = int(re.search(r'(\d+)$', div.get('id')).group(1))
        lista = div.find('ol')
        if not lista:
            continue
        preguntas = []
        for i, li in enumerate(lista.find_all('li', recursive=False), 1):
            anid = li.find(['ol', 'ul'])
            if not anid:
                continue
            enun = ''.join(x if isinstance(x, str) else x.get_text(' ')
                           for x in li.contents
                           if getattr(x, 'name', None) not in ('ol', 'ul'))
            enun = re.sub(r'\s+', ' ', enun).strip()
            ops = [re.sub(r'\s+', ' ', o.get_text(' ')).strip()
                   for o in anid.find_all('li', recursive=False)]
            if not enun or len(ops) < 2:
                continue
            letra, retro = (soluciones.get(n, {}) or {}).get(i, (None, ''))
            correcta = (ord(letra) - 97) if letra else None
            if correcta is not None and not (0 <= correcta < len(ops)):
                correcta = None
            preguntas.append({'enunciado': enun, 'opciones': ops,
                              'correcta': correcta, 'retroalimentacion': retro})
        if preguntas:
            banco[n] = preguntas
    return banco


def extraer_preguntas_pagina(html):
    """Preguntas del banco en texto de la página "Autoevaluaciones" del curso
    antiguo.

    Esa página lista las MISMAS preguntas que estan dentro de los recursos
    interactivos (Genially) de cada semana: es la fuente en texto del mismo
    contenido. Partir de aqui es mejor que deducir preguntas del temario,
    porque son las que el docente ya valido.

    Formato habitual:
        1. Enunciado de la pregunta:
             a. Opcion uno
             b. Opcion dos
             c. Opcion tres
    Devuelve [{'enunciado':…, 'opciones':[…]}] sin marcar la correcta (la
    pagina no la indica).
    """
    if not html:
        return []
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []
    sopa = BeautifulSoup(html, 'html.parser')
    preguntas = []

    # caso 1: listas anidadas <ol><li>enunciado<ol><li>opcion…
    for li in sopa.find_all('li'):
        anid = li.find(['ol', 'ul'])
        if not anid:
            continue
        enun = ''.join(x if isinstance(x, str) else x.get_text(' ')
                       for x in li.contents
                       if getattr(x, 'name', None) not in ('ol', 'ul'))
        enun = re.sub(r'\s+', ' ', enun).strip()
        ops = [re.sub(r'\s+', ' ', o.get_text(' ')).strip()
               for o in anid.find_all('li', recursive=False)]
        ops = [RE_OPCION.sub(r'\2', o).strip() for o in ops if o]
        if enun and len(ops) >= 2:
            preguntas.append({'enunciado': enun, 'opciones': ops})

    if preguntas:
        return preguntas

    # caso 2: texto plano con numeracion y letras
    lineas = [re.sub(r'\s+', ' ', l).strip()
              for l in re.split(r'<br\s*/?>|</p>|</li>', html)]
    lineas = [RE_TAGS.sub('', l).strip() for l in lineas]
    actual = None
    for l in lineas:
        if not l:
            continue
        m = RE_OPCION.match(l)
        if m and actual:
            actual['opciones'].append(m.group(2).strip())
        elif re.match(r'^\s*\d+[\.\)]\s*', l):
            if actual and len(actual['opciones']) >= 2:
                preguntas.append(actual)
            actual = {'enunciado': re.sub(r'^\s*\d+[\.\)]\s*', '', l),
                      'opciones': []}
    if actual and len(actual['opciones']) >= 2:
        preguntas.append(actual)
    return preguntas


def construir_entrada(semana, ra, temas, n_preguntas=N_PREGUNTAS_DEFECTO,
                      banco=None):
    """Mensaje de usuario con el material de la semana."""
    partes = [f'SEMANA: {semana}']
    if ra:
        partes.append('RESULTADO(S) DE APRENDIZAJE:\n' +
                      '\n'.join(f'- {r}' for r in ra if r))
    partes.append(f'NÚMERO DE PREGUNTAS SOLICITADAS: {n_preguntas}')
    if banco:
        partes.append(
            '\nPREGUNTAS ORIGINALES DEL DOCENTE (banco de la página '
            '"Autoevaluaciones" del curso anterior). Son las que ya se usaban '
            'en el recurso interactivo de esta semana. Consérvelas como base: '
            'reutilice su enunciado y sus opciones, corrija solo redacción o '
            'errores evidentes, e indique cuál es la correcta según el '
            'contenido académico. Añada preguntas nuevas SOLO si faltan para '
            'llegar al número solicitado:')
        for i, p in enumerate(banco, 1):
            partes.append(f'{i}. {p["enunciado"]}')
            for j, o in enumerate(p.get('opciones') or []):
                partes.append(f'   {chr(97 + j)}. {o}')
    partes.append('\nCONTENIDO ACADÉMICO DE LA SEMANA:')
    for t in temas:
        cod = t.get('codigo', '')
        tit = t.get('titulo', '')
        cuerpo = _texto_plano(t.get('html', ''), limite=6000)
        if cuerpo:
            partes.append(f'\n[{cod} {tit}]\n{cuerpo}')
    return '\n'.join(partes)


# ---------------------------------------------------------------------------
# Render del HTML interactivo
# ---------------------------------------------------------------------------
def render_autoevaluacion(preguntas, semana=''):
    """Preguntas → HTML autónomo, interactivo y sin dependencias externas.

    La interactividad se resuelve con radios y CSS (:has / :checked): no hace
    falta JavaScript, lo que evita que el sanitizador de Canvas la desactive.
    """
    if not preguntas:
        return ''
    uid = re.sub(r'[^0-9a-zA-Z]+', '', str(semana)) or 'sem'
    bloques = []
    for i, p in enumerate(preguntas, 1):
        nombre = f'q{uid}_{i}'
        opciones = []
        for j, op in enumerate(p.get('opciones') or []):
            correcta = (j == p.get('correcta', 0))
            opciones.append(
                f'<label class="ae-op{" ae-ok" if correcta else ""}">'
                f'<input type="radio" name="{nombre}">'
                f'<span>{_esc(op)}</span></label>')
        bloques.append(
            f'<li class="ae-preg">'
            f'<p class="ae-enun">{_esc(p.get("enunciado", ""))}</p>'
            f'<div class="ae-ops">{"".join(opciones)}</div>'
            f'<p class="ae-fb"><strong>Retroalimentación.</strong> '
            f'{_esc(p.get("retroalimentacion", ""))}</p>'
            f'</li>')

    estilo = (
        '<style>'
        '.ae-wrap{border:1px solid #bbd6e7;border-radius:8px;padding:14px 18px;margin:1em 0}'
        '.ae-preg{margin:0 0 1.2em;padding-bottom:1em;border-bottom:1px solid #e3edf5;list-style:none}'
        '.ae-preg:last-child{border-bottom:0;margin-bottom:0}'
        '.ae-enun{font-weight:600;color:#083e70;margin:0 0 .6em}'
        '.ae-op{display:block;padding:6px 10px;margin:4px 0;border:1px solid #c8ddeb;'
        'border-radius:6px;cursor:pointer;transition:background .2s}'
        '.ae-op:hover{background:#f0f5f9}'
        '.ae-op input{margin-right:8px}'
        '.ae-op:has(input:checked){border-color:#adb5bd;background:#f1f3f5}'
        '.ae-op.ae-ok:has(input:checked){border-color:#087f5b;background:#d8f5a2}'
        '.ae-fb{display:none;margin:.6em 0 0;padding:8px 12px;border-radius:6px;'
        'background:#fcf5e5;border-left:4px solid #eaa621;font-size:.95em;color:#273540}'
        '.ae-preg:has(input:checked) .ae-fb{display:block}'
        '</style>')

    # Nota: si Canvas elimina el <style> al sanitizar, las preguntas y la
    # retroalimentacion siguen siendo legibles (solo se pierde el ocultamiento
    # de la retroalimentacion hasta responder). Por eso el marcado es
    # semantico y no depende del CSS para tener sentido.
    return (f'{estilo}<div class="ae-wrap" data-ia="autoevaluacion-generada">'
            f'<ol style="margin:0;padding:0">{"".join(bloques)}</ol></div>')


def _esc(t):
    return (str(t or '').replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


# ---------------------------------------------------------------------------
# Llamada al modelo
# ---------------------------------------------------------------------------
def _parsear(texto):
    """Respuesta del modelo → lista de preguntas validadas."""
    t = (texto or '').strip()
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', t)
    i, j = t.find('{'), t.rfind('}')
    if i == -1 or j == -1:
        return []
    try:
        data = json.loads(t[i:j + 1])
    except json.JSONDecodeError:
        return []
    out = []
    for p in (data.get('preguntas') or []):
        ops = p.get('opciones') or []
        if not p.get('enunciado') or len(ops) < 2:
            continue
        c = p.get('correcta', 0)
        if not isinstance(c, int) or not (0 <= c < len(ops)):
            c = 0
        out.append({'enunciado': p['enunciado'], 'opciones': ops, 'correcta': c,
                    'retroalimentacion': p.get('retroalimentacion', '')})
    return out


def generar(semana, ra, temas, n_preguntas=N_PREGUNTAS_DEFECTO,
            modelo=MODELO_DEFAULT, log=lambda *a: None, banco=None):
    """Genera la autoevaluación de una semana. Devuelve (html, info).

    Si se pasa `banco` (preguntas de la página "Autoevaluaciones" del curso
    antiguo), el agente parte de ellas en lugar de inventarlas desde el
    temario: son las preguntas que el docente ya validó.
    """
    if Anthropic is None:
        raise RuntimeError('Falta la librería anthropic: pip install anthropic')
    if not os.environ.get('ANTHROPIC_API_KEY'):
        raise RuntimeError('Falta la variable de entorno ANTHROPIC_API_KEY')

    client = Anthropic()
    entrada = construir_entrada(semana, ra, temas, n_preguntas, banco)
    ultimo = None
    for intento in range(1, MAX_REINTENTOS + 2):
        try:
            resp = client.messages.create(
                model=modelo, max_tokens=4000, system=SYSTEM_PROMPT,
                messages=[{'role': 'user', 'content': entrada}])
            texto = ''.join(b.text for b in resp.content if b.type == 'text')
            preguntas = _parsear(texto)
            if preguntas:
                costo = (resp.usage.input_tokens / 1e6 * PRECIO_IN_POR_M +
                         resp.usage.output_tokens / 1e6 * PRECIO_OUT_POR_M)
                return render_autoevaluacion(preguntas, semana), {
                    'preguntas': preguntas,
                    'n': len(preguntas),
                    'tokens_in': resp.usage.input_tokens,
                    'tokens_out': resp.usage.output_tokens,
                    'costo_usd': round(costo, 4)}
            ultimo = 'la respuesta del modelo no contenía preguntas válidas'
        except Exception as e:                     # noqa: BLE001
            ultimo = str(e)
        if intento <= MAX_REINTENTOS:
            log(f'  reintento {intento} ({ultimo})')
            time.sleep(2 * intento)
    raise RuntimeError(f'No se pudo generar la autoevaluación: {ultimo}')


def procesar_plan(plan, canvas, gc, semanas=None, n_preguntas=N_PREGUNTAS_DEFECTO,
                  modelo=MODELO_DEFAULT, log=lambda *a: None):
    """Genera autoevaluaciones para las semanas indicadas (o todas).

    Devuelve (resultados, resumen). Los resultados se guardan en el plan bajo
    'autoevaluaciones_generadas' y sustituyen al recurso original.
    """
    resultados, llamadas, costo = {}, 0, 0.0
    objetivo = semanas or list((plan.get('semanas') or {}).keys())

    # Banco COMPLETO (preguntas + respuesta correcta + retroalimentacion) de la
    # pagina "Autoevaluaciones". Si la semana tiene su autoevaluacion completa
    # ahi, se renderiza DIRECTAMENTE sin llamar al modelo: el contenido ya esta
    # validado por el docente y no hay nada que la IA deba inventar.
    banco_num = {}
    for m in canvas.get('modulos', []):
        for it in m.get('items', []):
            clave = ((it.get('slug') or '') + ' ' + (it.get('titulo') or '')).lower()
            if 'autoevaluacion' in clave or 'autoevaluación' in clave:
                banco_num = extraer_banco_por_autoevaluacion(it.get('html') or '')
                break
        if banco_num:
            break
    if not banco_num:
        for it in (canvas.get('paginas_sueltas') or []):
            clave = ((it.get('slug') or '') + ' ' + (it.get('titulo') or '')).lower()
            if 'autoevaluacion' in clave or 'autoevaluación' in clave:
                banco_num = extraer_banco_por_autoevaluacion(it.get('html') or '')
                break
    if banco_num:
        log(f'  banco del docente: {len(banco_num)} autoevaluación(es) con solucionario')

    # Banco de preguntas del curso antiguo: la pagina "Autoevaluaciones"
    # contiene las MISMAS preguntas que estan dentro de los recursos
    # interactivos de cada semana. Se usan como base para no perder el trabajo
    # del docente ni desalinear ambos elementos.
    banco = []
    for m in canvas.get('modulos', []):
        for it in m.get('items', []):
            clave = ((it.get('slug') or '') + ' ' + (it.get('titulo') or '')).lower()
            if 'autoevaluacion' in clave or 'autoevaluación' in clave:
                banco = extraer_preguntas_pagina(it.get('html') or '')
                break
        if banco:
            break
    if not banco:
        for it in (canvas.get('paginas_sueltas') or []):
            clave = ((it.get('slug') or '') + ' ' + (it.get('titulo') or '')).lower()
            if 'autoevaluacion' in clave or 'autoevaluación' in clave:
                banco = extraer_preguntas_pagina(it.get('html') or '')
                break
    if banco:
        log(f'  banco del curso antiguo: {len(banco)} preguntas disponibles')
    else:
        log('  sin banco de preguntas: se generarán desde el contenido')
    for sem in objetivo:
        d = (plan.get('semanas') or {}).get(sem) or {}
        temas = [t for t in (d.get('temas') or []) if t.get('accion') != 'del']
        if not temas:
            log(f'  {sem}: sin temas, se omite')
            continue
        # el contenido real de cada tema se toma del curso extraído
        enriquecidos = []
        for t in temas:
            html = t.get('html') or ''
            if not html:
                html = gc._html_de_tema(canvas, t.get('codigo')) if hasattr(
                    gc, '_html_de_tema') else ''
            enriquecidos.append({'codigo': t.get('codigo', ''),
                                 'titulo': t.get('titulo', ''), 'html': html})
        # ¿existe la autoevaluación del docente para esta semana?
        _n = gc._num_semana(sem)
        _delDocente = banco_num.get(_n) if _n else None
        if _delDocente and all(p.get('correcta') is not None for p in _delDocente):
            # completa (con respuestas): se usa tal cual, sin llamar al modelo
            resultados[sem] = {
                'html': render_autoevaluacion(_delDocente, sem),
                'preguntas': _delDocente, 'n': len(_delDocente),
                'origen': 'docente'}
            log(f'  ✓ {sem}: {len(_delDocente)} preguntas del docente (sin IA)')
            continue

        html, info = generar(sem, d.get('resultados_aprendizaje') or [],
                             enriquecidos, n_preguntas, modelo, log,
                             banco=_delDocente or banco)
        # el costo se registra en el log del servidor, no en la respuesta:
        # es informacion operativa que no ve el usuario final
        resultados[sem] = {'html': html, 'preguntas': info['preguntas'],
                           'n': info['n'], 'origen': 'ia'}
        llamadas += 1
        costo += info['costo_usd']
        log(f'  ✓ {sem}: {info["n"]} preguntas (uso interno: '
            f'${info["costo_usd"]})')
    # el resumen que viaja al navegador no lleva costos ni llamadas
    log(f'  [interno] {llamadas} llamada(s), ${round(costo, 4)}')
    return resultados, {'semanas': len(resultados)}
