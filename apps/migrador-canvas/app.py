#!/usr/bin/env python3
"""
app.py — Backend local para la migración de metacursos Canvas (16 → N semanas).

Corre en la máquina del revisor. El revisor abre http://localhost:5000,
pega el link del curso viejo y sube el Word de distribución. Todo lo demás
(extraer Canvas, cotejar, migrar assets, generar el curso nuevo) pasa aquí.

Ejecutar:
    python3 -m venv venv && source venv/bin/activate
    pip install flask requests python-docx openpyxl
    export CANVAS_TOKEN="tu_token"          # o ponlo en .env
    export CANVAS_BASE="https://utpl.instructure.com"
    python3 app.py
"""
import os, re, io, json, tempfile
import re
from flask import Flask, request, jsonify, send_from_directory

import extraer_canvas as ec
import parsear_distribucion as pd
import parsear_ajustes as pa
import canvas_assets as ca
import generar_curso as gc

# .env sencillo (sin dependencias)
if os.path.exists('.env'):
    for line in open('.env'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

BASE = os.environ.get('CANVAS_BASE', 'https://utpl.instructure.com')
TOKEN = os.environ.get('CANVAS_TOKEN')
CUENTA = os.environ.get('CANVAS_ACCOUNT_ID', '1')
# Instancia DESTINO (p. ej. utpl.test.instructure.com). Si no se define,
# se usa la misma del origen. Permite extraer de producción y subir a test.
BASE_DESTINO = os.environ.get('CANVAS_BASE_DESTINO', BASE).rstrip('/')
TOKEN_DESTINO = os.environ.get('CANVAS_TOKEN_DESTINO', TOKEN)

app = Flask(__name__, static_folder='.', static_url_path='')

# caché en memoria del último curso extraído (evita re-extraer al generar)
CACHE = {}
PROGRESO = {}   # estado en vivo de la subida a Canvas (barra del tablero)


def _course_id(url_o_id):
    m = re.search(r'/courses/(\d+)', str(url_o_id))
    if m: return int(m.group(1))
    if str(url_o_id).strip().isdigit(): return int(url_o_id)
    return None


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/procesar', methods=['POST'])
def procesar():
    """Recibe: link del curso + archivo de ajustes. Devuelve canvas_slim +
    distribución para que la interfaz arme el tablero.

    Nuevo flujo: el archivo es la TABLA EXCEL DE AJUSTES (.xlsx) elaborada
    por el revisor; trae el link del curso viejo, la reubicación de temas
    por semana y los temas eliminados. El .docx del docente se sigue
    aceptando como flujo legado.
    """
    if not TOKEN:
        return jsonify(error='Falta CANVAS_TOKEN en el servidor'), 500
    if 'word' not in request.files:
        return jsonify(error='Falta el archivo de ajustes (.xlsx) o el Word'), 400
    f = request.files['word']
    nombre = (f.filename or '').lower()
    es_excel = nombre.endswith('.xlsx') or nombre.endswith('.xlsm')

    # 1) parsear el archivo de entrada
    sufijo = '.xlsx' if es_excel else '.docx'
    tmp = tempfile.NamedTemporaryFile(suffix=sufijo, delete=False)
    f.save(tmp.name); tmp.close()
    ajustes = None
    try:
        if es_excel:
            ajustes = pa.parse(tmp.name)
        else:
            dist = pd.parse(tmp.name)
    except Exception as e:
        tipo = 'Excel de ajustes' if es_excel else 'Word'
        return jsonify(error=f'{tipo} inválido: {e}'), 400
    finally:
        os.unlink(tmp.name)

    # 2) resolver el curso: link pegado o URL dentro del Excel
    url = request.form.get('curso_url', '')
    cid = _course_id(url) or (_course_id(ajustes['meta']['curso_url']) if ajustes else None)
    if not cid:
        return jsonify(error='No se pudo leer el ID del curso (pega el link o inclúyelo en el Excel)'), 400

    # 3) extraer Canvas
    try:
        canvas = ec.extraer_curso(BASE, TOKEN, cid, log=lambda *a: None)
    except Exception as e:
        return jsonify(error=f'Error extrayendo Canvas: {e}'), 502
    CACHE[cid] = canvas

    # 4) si la entrada fue el Excel, completar títulos y textos de RA
    #    desde el propio curso (el Excel solo trae números y códigos)
    if ajustes is not None:
        dist = pa.enriquecer_con_canvas(ajustes, canvas)

    # 5) recortar Canvas a páginas Semana (aligera el payload) + inventario de assets
    slim = {'curso_id': canvas['curso_id'], 'nombre': canvas['nombre'], 'modulos': []}
    for m in canvas['modulos']:
        items = []
        for it in m['items']:
            if re.match(r'^Semana\s+\d+(\s*y\s*\d+)?$', (it.get('titulo') or '').strip()) and it.get('html'):
                inv = ca.inventariar(it['html'])
                items.append({'id': it['id'], 'titulo': it['titulo'], 'slug': it.get('slug', ''),
                              'html': it['html'], 'assets': inv['resumen']})
        if items:
            slim['modulos'].append({'id': m['id'], 'nombre': m['nombre'], 'items': items})

    # informativo para el tablero: paginas fuera de modulos que se trajeron
    # (p. ej. "Autoevaluaciones"), para que el revisor sepa que existen
    sueltas = [{'titulo': p.get('titulo'), 'slug': p.get('slug'),
                'clasificacion': p.get('clasificacion')}
               for p in (canvas.get('paginas_sueltas') or [])]
    return jsonify(canvas=slim, distribucion=dist, curso_id=cid,
                   inicio=gc._fuentes_inicio(canvas), paginas_sueltas=sueltas)


@app.route('/api/generar', methods=['POST'])
def generar():
    """Recibe el plan revisado. Copia assets, aplica plantilla y crea el curso nuevo.
    Por defecto crea las páginas SIN publicar (dry-run seguro)."""
    if not TOKEN:
        return jsonify(error='Falta CANVAS_TOKEN'), 500
    data = request.get_json(force=True)
    plan = data.get('plan')
    cid = data.get('curso_id') or plan.get('curso_id')
    publicar = bool(data.get('publicar', True))   # todo publicado, nada en borrador
    curso_destino = data.get('curso_destino')  # None → crea uno nuevo
    # el tablero puede mandar el link completo del curso destino: de ahí se
    # deriva la instancia (producción/test) sin depender del .env
    base_dest = (data.get('base_destino') or BASE_DESTINO).rstrip('/')
    token_dest = TOKEN_DESTINO or TOKEN
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el Word'), 400

    logs = []
    import time as _t
    total_pag = len(plan.get('semanas') or {}) + 3   # inicio + preliminares + finales (estimado)
    PROGRESO.clear()
    PROGRESO.update(estado='subiendo', pct=3, etapa='Preparando la subida…',
                    inicio=_t.time(), paginas=0, total_paginas=total_pag)

    def _log(*a):
        msg = ' '.join(str(x) for x in a)
        logs.append(msg)
        # traducir los hitos del log a % de avance para la barra del tablero
        if 'Curso destino creado' in msg or 'Instancias separadas' in msg:
            PROGRESO.update(pct=8, etapa='Curso destino listo')
        elif 'Copiando' in msg and 'archivos' in msg:
            PROGRESO.update(pct=12, etapa='Copiando archivos e imágenes del curso viejo al nuevo…')
        elif re.search(r'· (\d+)/(\d+) archivos', msg):
            _m = re.search(r'· (\d+)/(\d+) archivos', msg)
            _i, _t = int(_m.group(1)), int(_m.group(2))
            PROGRESO.update(pct=12 + int(28 * _i / max(1, _t)),
                            etapa=f'Copiando archivos e imágenes… {_i}/{_t}')
        elif 'archivos copiados' in msg:
            PROGRESO.update(pct=40, etapa='Archivos copiados')
        elif 'recursos de la plantilla' in msg:
            PROGRESO.update(pct=45, etapa='Subiendo recursos de la plantilla oficial…')
        elif 'recursos de plantilla subidos' in msg:
            PROGRESO.update(pct=50, etapa='Recursos de plantilla listos')
        elif msg.strip().startswith('✓'):
            PROGRESO['paginas'] += 1
            frac = min(1.0, PROGRESO['paginas'] / max(1, PROGRESO['total_paginas']))
            PROGRESO.update(pct=min(95, int(50 + 45 * frac)),
                            etapa=f"Creando páginas… {msg.strip().lstrip('✓ ').split(':')[0]}")
        PROGRESO['ultimo'] = msg

    try:
        res = gc.generar(BASE, TOKEN, plan, canvas, CUENTA,
                         curso_destino=curso_destino, publicar=publicar,
                         base_destino=base_dest, token_destino=token_dest,
                         log=_log)
    except Exception as e:
        PROGRESO.update(estado='error', etapa=str(e), pct=PROGRESO.get('pct', 0))
        return jsonify(error=str(e), logs=logs), 502
    res['logs'] = logs
    res['url_curso'] = f"{base_dest}/courses/{res['curso_destino']}"
    PROGRESO.update(estado='listo', pct=100, etapa='Curso subido a Canvas',
                    url=res['url_curso'])
    return jsonify(res)


@app.route('/api/generar/progreso')
def generar_progreso():
    """Estado en vivo de la subida (para la barra de progreso del tablero)."""
    import time as _t
    p = dict(PROGRESO)
    if p.get('inicio'):
        p['segundos'] = int(_t.time() - p['inicio'])
    return jsonify(p or {'estado': 'inactivo'})


@app.route('/api/preview', methods=['POST'])
def preview():
    """Previsualizador: construye las páginas del curso NUEVO (plantilla
    Rediseño 3 + renumeración) SIN tocar Canvas. Las imágenes siguen
    apuntando al curso viejo, así se ven tal cual en el navegador del
    revisor (que ya tiene sesión en Canvas)."""
    data = request.get_json(force=True)
    plan = data.get('plan')
    cid = data.get('curso_id') or plan.get('curso_id')
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el archivo'), 400
    try:
        paginas, reporte = gc.construir_paginas(plan, canvas)
        for pg in paginas:
            pg['body'] = gc.ca.tokens_a_local(pg['body'])
    except Exception as e:
        return jsonify(error=str(e)), 500
    # recursos locales referenciados pero ausentes (p. ej. la carpeta
    # Metacurso sin copiar a plantilla_recursos/): el empaquetado debe
    # incluir TODAS las carpetas; aquí se avisa en vez de fallar en silencio
    import os as _os, re as _re, urllib.parse as _up
    base_rec = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'plantilla_recursos')
    faltantes = set()
    for pg in paginas:
        for ruta in _re.findall(r'(?:src|href)="/plantilla_recursos/([^"?]+)', pg['body']):
            rel = _up.unquote(ruta)
            if not _os.path.exists(_os.path.join(base_rec, rel)):
                faltantes.add(rel)
    return jsonify(paginas=paginas, renumeracion=reporte,
                   recursos_faltantes=sorted(faltantes),
                   validacion=gc.validar_consistencia(plan))


@app.route('/api/alertas', methods=['POST'])
def alertas_temporales():
    """Detección de referencias temporales (semana/bimestre) PARA EL TABLERO:
    el revisor las ve y corrige aquí, antes de previsualizar o subir."""
    data = request.get_json(force=True)
    plan = data.get('plan')
    cid = data.get('curso_id') or plan.get('curso_id')
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el archivo'), 400
    try:
        paginas, _ = gc.construir_paginas(plan, canvas)
    except Exception as e:
        return jsonify(error=str(e)), 500
    alertas = []
    for pg in paginas:
        for a in (pg.get('alertas_detalle') or []):
            alertas.append({'semana': pg['semana'], 'ubicacion': a.get('ubicacion', ''),
                            'frase': a['frase'], 'contexto': a.get('contexto', '')})
    return jsonify(alertas=alertas)


@app.route('/api/contextualizaciones/estado', methods=['POST'])
def contextualizaciones_estado():
    """Por semana del plan: RA(s) y contextualización fuente (si la hubiera),
    para la vista de contextualizaciones del tablero donde el agente evalúa
    y da veredicto (SÍ es / NO es) antes de generar."""
    data = request.get_json(force=True)
    plan = data.get('plan')
    cid = data.get('curso_id') or plan.get('curso_id')
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el archivo'), 400
    import re as _re
    _, ctx_por_ra = gc._material_viejo(canvas)
    ras_txt, _, _ = gc._indices_canvas(canvas)
    txt_a_num = {(t or '').strip().lower(): n for n, t in ras_txt.items()}
    def _plano(h):
        return _re.sub(r'\s+', ' ', _re.sub(r'<[^>]+>', ' ', h or '')).strip()
    estado = {}
    for sem, d in (plan.get('semanas') or {}).items():
        ras = d.get('resultados_aprendizaje') or []
        nums = [txt_a_num.get((r or '').strip().lower()) for r in ras]
        estado[sem] = {'ras': ras,
                       'fuentes': [_plano(ctx_por_ra.get(n)) if n and ctx_por_ra.get(n) else None
                                   for n in nums]}
    return jsonify(estado=estado)


@app.route('/api/banco/estado', methods=['POST'])
def banco_estado():
    """Banco de preguntas de la página "Autoevaluaciones", estructurado.

    Cada pregunta es una unidad independiente con su id, número, enunciado,
    tipo, opciones, respuesta correcta, retroalimentación, recursos y avisos.
    El solucionario NO se devuelve como copia: se deriva del banco.
    """
    import banco_preguntas as bp
    data = request.get_json(force=True)
    cid = data.get('curso_id') or (data.get('plan') or {}).get('curso_id')
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el archivo'), 400

    html = ''
    origen = ''
    candidatos = [it for m in canvas.get('modulos', []) for it in m.get('items', [])]
    candidatos += list(canvas.get('paginas_sueltas') or [])
    for it in candidatos:
        clave = ((it.get('slug') or '') + ' ' + (it.get('titulo') or '')).lower()
        if 'autoevaluacion' in clave or 'autoevaluación' in clave:
            html = it.get('html') or ''
            origen = it.get('titulo') or it.get('slug') or ''
            break
    if not html:
        return jsonify(bancos=[], origen='',
                       error='No se encontró la página de autoevaluaciones')

    bancos = bp.extraer_banco(html)
    return jsonify(origen=origen,
                   bancos=[bancos[n].to_dict() for n in sorted(bancos)])


@app.route('/api/banco/guardar', methods=['POST'])
def banco_guardar():
    """Recibe el banco editado y devuelve el HTML regenerado.

    El solucionario se reconstruye a partir de las preguntas, de modo que
    agregar, eliminar o modificar una sola de ellas mantiene ambos en
    correspondencia uno a uno sin sincronización manual.
    """
    import banco_preguntas as bp
    data = request.get_json(force=True)
    entrada = data.get('bancos') or []
    try:
        bancos = [bp.Banco.from_dict(b) for b in entrada]
    except Exception as e:
        return jsonify(error=f'Banco inválido: {e}'), 400

    partes, avisos = [], []
    for b in bancos:
        b.validar()
        partes.append(bp.render_banco_html(b))
        avisos.extend(b.avisos)
    return jsonify(html='<div class="fce">' + ''.join(partes) + '</div>',
                   avisos=avisos,
                   interactivas={b.numero: bp.render_interactiva(b) for b in bancos})


@app.route('/api/banco/convertir', methods=['POST'])
def banco_convertir():
    """Convierte TODAS las autoevaluaciones del banco al formato interactivo
    propio, SIN llamar a ningún modelo.

    Las preguntas, las respuestas correctas y la retroalimentación ya están en
    la página "Autoevaluaciones" del curso antiguo (bloques autoevaluacion_N +
    tablas solucionario_N): aquí solo se maquetan con la plantilla. Coste 0.

    Sirve para dejar TODAS las semanas en el mismo formato y evitar que unas
    queden con el recurso externo y otras con el propio.
    """
    import banco_preguntas as bp
    data = request.get_json(force=True)
    cid = data.get('curso_id') or (data.get('plan') or {}).get('curso_id')
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el archivo'), 400

    # el banco puede venir editado desde el tablero; si no, se lee del curso
    if data.get('bancos'):
        bancos = {b['numero']: bp.Banco.from_dict(b) for b in data['bancos']}
    else:
        html = ''
        cand = [it for m in canvas.get('modulos', []) for it in m.get('items', [])]
        cand += list(canvas.get('paginas_sueltas') or [])
        for it in cand:
            clave = ((it.get('slug') or '') + ' ' + (it.get('titulo') or '')).lower()
            if 'autoevaluacion' in clave or 'autoevaluación' in clave:
                html = it.get('html') or ''
                break
        if not html:
            return jsonify(error='No se encontró la página de autoevaluaciones'), 404
        bancos = bp.extraer_banco(html)

    # correspondencia autoevaluacion_N → semana del plan
    plan = data.get('plan') or {}
    semanas = list((plan.get('semanas') or {}).keys())
    mapa = data.get('mapa') or {}          # {n_autoeval: nombre_semana}

    salidas, avisos = {}, []
    for n, b in sorted(bancos.items()):
        sem = mapa.get(str(n)) or mapa.get(n)
        if not sem:
            sem = semanas[n - 1] if 0 < n <= len(semanas) else None
        incompletas = [p.numero for p in b.preguntas if not p.completa]
        if incompletas:
            avisos.append({'autoevaluacion': n, 'semana': sem,
                           'aviso': f'preguntas incompletas: {incompletas}'})
        if not sem:
            avisos.append({'autoevaluacion': n, 'semana': None,
                           'aviso': 'sin semana asignada, no se aplicará'})
            continue
        salidas[sem] = {'html': bp.render_interactiva(b),
                        'n': len(b.preguntas), 'origen': 'docente',
                        'autoevaluacion': n}

    # el resumen NO incluye costos ni número de llamadas: esa información es
    # operativa y no debe mostrarse a los usuarios finales
    return jsonify(resultados=salidas, avisos=avisos,
                   resumen={'autoevaluaciones': len(salidas),
                            'preguntas': sum(v['n'] for v in salidas.values())})


@app.route('/api/agente/autoevaluacion', methods=['POST'])
def agente_autoevaluacion():
    """Agente A4: genera la autoevaluación de una o varias semanas como HTML
    interactivo propio, que SUSTITUYE al recurso externo original.

    Solo se invoca cuando el revisor lo pide: si no toca nada, el recurso
    original se traslada tal cual.
    """
    import agente_autoevaluacion as a4
    data = request.get_json(force=True)
    plan = data.get('plan')
    cid = data.get('curso_id') or plan.get('curso_id')
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el archivo'), 400
    try:
        resultados, resumen = a4.procesar_plan(
            plan, canvas, gc,
            semanas=data.get('semanas'),
            n_preguntas=int(data.get('n_preguntas') or a4.N_PREGUNTAS_DEFECTO),
            modelo=data.get('modelo') or a4.MODELO_DEFAULT)
    except Exception as e:
        return jsonify(error=str(e)), 500
    return jsonify(resultados=resultados, resumen=resumen)


@app.route('/api/evaluaciones/estado', methods=['POST'])
def evaluaciones_estado():
    """Evaluaciones del curso ANTIGUO (página "Evaluaciones" o similar) para
    que el revisor las traiga, edite o elimine antes de generar el curso nuevo.

    Se busca tanto en las páginas de módulos como en las sueltas, porque la
    página de evaluaciones no siempre está dentro de un módulo.
    """
    import re as _re
    data = request.get_json(force=True)
    cid = data.get('curso_id') or (data.get('plan') or {}).get('curso_id')
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el archivo'), 400

    # incluye AUTOevaluaciones: en el curso antiguo la pagina se llama
    # "Autoevaluaciones" y contiene las mismas preguntas que estan dentro de
    # los recursos interactivos (Genially) de cada semana.
    CLAVES = ('autoevaluacion', 'autoevaluación', 'autoevaluaciones',
              'evaluacion', 'evaluación', 'evaluaciones', 'evaluate',
              'zona-de-evaluacion', 'zona de evaluac')
    encontradas = []
    vistos = set()

    def _mirar(it):
        slug = (it.get('slug') or '')
        tit = (it.get('titulo') or '')
        clave = (slug + ' ' + tit).lower()
        html = it.get('html') or ''
        if not html or not any(k in clave for k in CLAVES):
            return
        if _re.match(r'^semana\s+\d+', tit.strip(), _re.I):
            return                      # las semanas ya se tratan aparte
        if slug in vistos:
            return
        vistos.add(slug)
        encontradas.append({'titulo': tit or slug, 'slug': slug, 'html': html})

    for m in canvas.get('modulos', []):
        for it in m.get('items', []):
            _mirar(it)
    for it in (canvas.get('paginas_sueltas') or []):
        _mirar(it)

    # diagnostico: si no se hallo nada, devolver el inventario de paginas para
    # ver QUE trajo realmente el extractor (puede que la pagina no este en
    # ningun modulo y por tanto no se haya extraido del curso antiguo)
    if not encontradas:
        inventario = []
        for m in canvas.get('modulos', []):
            for it in m.get('items', []):
                inventario.append({'titulo': it.get('titulo') or '',
                                   'slug': it.get('slug') or '',
                                   'con_html': bool(it.get('html'))})
        for it in (canvas.get('paginas_sueltas') or []):
            inventario.append({'titulo': it.get('titulo') or '',
                               'slug': it.get('slug') or '',
                               'con_html': bool(it.get('html')), 'suelta': True})
        return jsonify(evaluaciones=[], inventario=inventario)

    def _recursos(html):
        out = []
        for m in _re.finditer(r'<iframe[^>]*src="([^"]+)"[^>]*>', html or ''):
            t = _re.search(r'title="([^"]*)"', m.group(0))
            out.append({'src': m.group(1), 'titulo': t.group(1) if t else ''})
        return out

    for e in encontradas:
        e['recursos'] = _recursos(e['html'])

    return jsonify(evaluaciones=encontradas)


@app.route('/api/practica/estado', methods=['POST'])
def practica_estado():
    """Zona de práctica por semana del PLAN: actividades recomendadas,
    autoevaluaciones y actividad evaluada que se traen del curso viejo,
    para que el revisor pueda editarlas antes de generar.

    Las autoevaluaciones suelen ser iframes externos (Genially): se puede
    quitarlas, sustituirlas o cambiar el texto que las acompaña, pero las
    preguntas se editan en la herramienta de origen, no aquí.
    """
    data = request.get_json(force=True)
    plan = data.get('plan')
    cid = data.get('curso_id') or plan.get('curso_id')
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el archivo'), 400
    try:
        material, _ = gc._material_viejo(canvas)
    except Exception as e:
        return jsonify(error=str(e)), 500

    import re as _re
    def _iframes(html):
        return [{'src': m.group(1),
                 'titulo': (_re.search(r'title="([^"]*)"', m.group(0)) or [None, ''])[1]
                           if _re.search(r'title="([^"]*)"', m.group(0)) else ''}
                for m in _re.finditer(r'<iframe[^>]*src="([^"]+)"[^>]*>', html or '')]

    estado = {}
    for sem, d in (plan.get('semanas') or {}).items():
        # semanas del curso VIEJO que alimentan esta semana nueva
        origen = sorted({gc._num_semana(t.get('semana_canvas'))
                         for t in (d.get('temas') or [])
                         if t.get('semana_canvas') and gc._num_semana(t.get('semana_canvas'))})
        bloques = []
        for n in origen:
            info = material.get(n) or {}
            bloques.append({
                'semana_origen': f'Semana {n}',
                'actividades': info.get('actividades') or '',
                'evaluadas': info.get('evaluadas') or '',
                'autoevaluaciones': [{'html': a, 'iframes': _iframes(a)}
                                     for a in (info.get('autoevals') or [])],
            })
        estado[sem] = {'origen': [f'Semana {n}' for n in origen], 'bloques': bloques}
    return jsonify(estado=estado)


@app.route('/api/semana/estado', methods=['POST'])
def semana_estado():
    """Por semana: qué datos usaría el Agente A3 (frases de inicio de las
    semanas antiguas e índice de temas) y si aplica IA o no, SIN llamar al
    modelo. Es la vista previa que el revisor confirma antes de generar."""
    import agente_semana as a3
    data = request.get_json(force=True)
    plan = data.get('plan')
    cid = data.get('curso_id') or plan.get('curso_id')
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el archivo'), 400
    try:
        estado = a3.estado_plan(plan, canvas, gc)
    except Exception as e:
        return jsonify(error=str(e)), 500
    return jsonify(estado=estado)


@app.route('/api/agente/semana', methods=['POST'])
def agente_semana():
    """Agente A3 (Consolidación y Optimización Semanal): genera por semana la
    introducción (consolidada o desde el índice) y el cierre conclusivo."""
    import agente_semana as a3
    data = request.get_json(force=True)
    plan = data.get('plan')
    cid = data.get('curso_id') or plan.get('curso_id')
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el archivo'), 400
    try:
        resultados, resumen = a3.procesar_plan(plan, canvas, gc,
                                               modelo=data.get('modelo') or a3.MODELO_DEFAULT)
    except Exception as e:
        return jsonify(error=str(e)), 500
    return jsonify(resultados=resultados, resumen=resumen)


@app.route('/api/agente/contextualizaciones', methods=['POST'])
def agente_contextualizaciones():
    """Agente A1: revisa/genera las contextualizaciones del plan.
    RA unico con texto valido → conserva; invalido/vacio → genera;
    2+ RA unidos → genera obligatoriamente el conjunto; mismos RA → reutiliza."""
    import agente_contextualizacion as a1
    data = request.get_json(force=True)
    plan = data.get('plan')
    cid = data.get('curso_id') or plan.get('curso_id')
    canvas = CACHE.get(cid)
    if not canvas:
        return jsonify(error='Curso no está en caché; vuelve a procesar el archivo'), 400
    try:
        resultados, resumen = a1.procesar_plan(plan, canvas, gc,
                                               modelo=data.get('modelo') or a1.MODELO_DEFAULT)
    except Exception as e:
        return jsonify(error=str(e)), 500
    return jsonify(resultados=resultados, resumen=resumen)


if __name__ == '__main__':
    print(f"🌐 Migrador de metacursos · {BASE}")
    print(f"   Token: {'✓ cargado' if TOKEN else '✗ FALTA (export CANVAS_TOKEN)'}")
    print("   Abre http://localhost:5000")
    app.run(host='127.0.0.1', port=5000, debug=True)
