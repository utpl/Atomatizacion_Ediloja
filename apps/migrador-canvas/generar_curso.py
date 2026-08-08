#!/usr/bin/env python3
"""
generar_curso.py — Construye el curso nuevo a partir del plan de migración revisado.

Toma el plan (decisiones del revisor) + el curso viejo extraído, y por cada semana nueva:
  1. reúne el HTML de los temas que se MANTIENEN
  2. migra sus assets (imágenes/focalizadores) del curso viejo al nuevo
  3. vierte todo en la NUEVA PLANTILLA (plantilla.render_semana)
  4. crea la página en el curso destino vía Canvas API

Los temas MODIFICAR / NUEVO y los bloques de contextualización/actividad/autoevaluación
se marcan como huecos <!-- IA:... --> para que el agente los complete después.

⚠ La plantilla nueva vive en plantilla.py. Mientras no exista el molde definitivo,
render_semana reusa la estructura del curso viejo (fallback) para que el pipeline corra.
"""
import os
import time
import re, requests
import canvas_assets as ca
import renumerar
from parsear_ajustes import _indices_canvas

try:
    import plantilla  # molde nuevo, si existe
except ImportError:
    plantilla = None


# ---------------------------------------------------------------------------
# Fallback de plantilla: reflow simple mientras llega el molde nuevo
# ---------------------------------------------------------------------------
def _render_fallback(semana, temas_html, ra, huecos):
    partes = [f'<div class="cu-semana" data-semana="{semana}">']
    partes.append('<div class="cu-ra"><h2>Resultado de aprendizaje</h2>'
                  + ''.join(f'<p>{r}</p>' for r in ra) + '</div>')
    if 'contextualizacion' in huecos:
        partes.append('<!-- IA:contextualizacion --><div class="cu-contexto" '
                      'data-ia="contextualizacion" data-ia-pendiente="1"></div>')
    for t in temas_html:
        partes.append(f'<section class="cu-tema" data-codigo="{t["codigo"]}">{t["html"]}</section>')
    if 'actividad' in huecos:
        partes.append('<!-- IA:actividad --><div class="cu-actividad" '
                      'data-ia="actividad" data-ia-pendiente="1"></div>')
    if 'autoevaluacion' in huecos:
        partes.append('<!-- IA:autoevaluacion --><div class="cu-autoeval" '
                      'data-ia="autoevaluacion" data-ia-pendiente="1"></div>')
    partes.append('</div>')
    return '\n'.join(partes)


def render_semana(semana, temas_html, ra, huecos, **kw):
    if plantilla and hasattr(plantilla, 'render_semana'):
        try:
            return plantilla.render_semana(semana, temas_html, ra, huecos, **kw)
        except TypeError:  # molde antiguo sin kwargs
            return plantilla.render_semana(semana, temas_html, ra, huecos)
    return _render_fallback(semana, temas_html, ra, huecos)


# ---------------------------------------------------------------------------
# Índice de HTML por código de tema desde el curso viejo
# ---------------------------------------------------------------------------
RE_HEAD = re.compile(r'<(h[2-6])[^>]*>(.*?)</\1>', re.S | re.I)
RE_MARCA_ACT = re.compile(r'Actividad(?:es)? de aprendizaje (recomendada|evaluada)s?', re.I)


def _inicio_zona_actividades(html):
    """Posiciones donde empieza cada bloque de actividades (recomendadas o
    evaluadas) en una página vieja: el corte se hace en el contenedor del
    subtítulo para que el tema NO arrastre las actividades (van aparte, en
    las pestañas de la Zona de práctica)."""
    posiciones = []
    for m in RE_MARCA_ACT.finditer(html):
        pos = html.rfind('<div class="subtitulo-semana', max(0, m.start() - 400), m.start())
        if pos == -1:
            pos = html.rfind('<h3', max(0, m.start() - 250), m.start())
        posiciones.append(pos if pos != -1 else m.start())
    return sorted(posiciones)
RE_CODE = re.compile(r'^\s*(?:<[^>]+>)*\s*(\d+\.\d+(?:\.\d+)?)\.?\s')

def _balancear(frag):
    """Repara fragmentos HTML cortados a mitad de contenedores: cierra lo
    abierto y descarta cierres huérfanos (evita que un </div> extra rompa
    el panel de la plantilla)."""
    try:
        from bs4 import BeautifulSoup
        return str(BeautifulSoup(frag, 'html.parser'))
    except Exception:
        return frag


def _secciones_por_codigo(canvas):
    """{codigo_top: html} recorriendo las páginas Semana del curso viejo.

    Reglas:
    · Solo cortan sección los encabezados de TEMA (X.Y). Los subtemas
      (X.Y.Z) quedan DENTRO de su padre.
    · Un mismo tema puede continuar en varias semanas viejas (p. ej. 2.5 en
      semanas 5, 6 y 7): las apariciones se CONCATENAN en orden de semana,
      quitando el encabezado repetido de las continuaciones.
    · Cada fragmento se balancea para no arrastrar cierres huérfanos.
    """
    ocurrencias = {}   # codigo → [(num_semana_vieja, fragmento), …]
    for m in canvas['modulos']:
        for it in m['items']:
            t = (it.get('titulo') or '').strip()
            mw = re.match(r'^Semana\s+(\d+)(\s*y\s*\d+)?$', t)
            if not mw:
                continue
            nsem = int(mw.group(1))
            html = it.get('html', '')
            zonas_act = _inicio_zona_actividades(html)
            heads = []
            for h in RE_HEAD.finditer(html):
                txt = re.sub('<[^>]+>', '', h.group(2)).replace('\xa0', ' ').strip()
                mm = re.match(r'^(\d+\.\d+(?:\.\d+)?)\.?(\s+|$)', txt)
                if mm:
                    heads.append((h, mm.group(1)))
            for i, (h, cod) in enumerate(heads):
                if cod.count('.') > 1:
                    continue  # subtema: va dentro del padre
                fin = len(html)
                for j in range(i + 1, len(heads)):
                    if heads[j][1].count('.') == 1:  # próximo TEMA top
                        fin = heads[j][0].start(); break
                # el tema termina donde empieza la zona de actividades: éstas
                # no van dentro del contenido sino en la Zona de práctica
                for z in zonas_act:
                    if h.start() < z < fin:
                        fin = z; break
                frag = _balancear(html[h.start():fin])
                ocurrencias.setdefault(cod, []).append((nsem, frag))

    idx = {}
    for cod, occ in ocurrencias.items():
        occ.sort(key=lambda x: x[0])
        partes = []
        for k, (_, frag) in enumerate(occ):
            if k:
                # continuación: quitar el encabezado repetido del tema
                frag = RE_HEAD.sub('', frag, count=1)
            partes.append(frag)
        idx[cod] = '\n'.join(partes)
    return idx



# ---------------------------------------------------------------------------
# Construcción de páginas (reutilizable por /api/generar y /api/preview)
# ---------------------------------------------------------------------------
RE_RA_PAG = re.compile(r'Resultado de aprendizaje\s+(\d+)\s*:?\s*</strong>', re.I)

def _div_balanceado(html, i):
    """Contenido interno del <div> que abre en la posición i (anidamiento seguro)."""
    j = html.index('>', i) + 1
    nivel, k, c = 1, j, -1
    while nivel and k < len(html):
        a = html.find('<div', k)
        c = html.find('</div>', k)
        if c == -1:
            break
        if a != -1 and a < c:
            nivel += 1; k = a + 4
        else:
            nivel -= 1; k = c + 6
    return html[j:c].strip()


RE_HEAD_UNIDAD = re.compile(r'<(h[1-4])[^>]*>\s*(?:<strong>)?\s*Unidad\s+(\d+)\.', re.I)



FORO_ASESORIA = 'Foro de asesoría permanente'

FORO_ASESORIA_CUERPO = (
    '<p>Estimado estudiante, este espacio esta destinado a resolver las inquietudes '
    'que surjan durante el estudio de la asignatura. Plantee aqui sus consultas sobre '
    'los contenidos, las actividades o los recursos, y su docente le respondera en el '
    'menor tiempo posible.</p>'
    '<p>Antes de escribir, revise si su pregunta ya fue formulada por un companero: '
    'las respuestas anteriores pueden resolver su duda de inmediato.</p>')


def _url_foro_asesoria(base, token, curso_id, log=None):
    """Devuelve la URL del Foro de asesoria del curso DESTINO. Si no existe,
    lo CREA primero (publicado) y luego devuelve su URL, para que el boton de
    la pagina de inicio quede enlazado."""
    if not curso_id:
        return None
    h = {'Authorization': f'Bearer {token}'}
    url_foros = f'{base.rstrip("/")}/api/v1/courses/{curso_id}/discussion_topics'
    try:
        r = _peticion('GET', url_foros, headers=h, params={'per_page': 100},
                      reintentos=2, timeout=60)
        for t in r.json():
            if re.search(r'foro\s+de\s+asesor', (t.get('title') or ''), re.I):
                if log:
                    log(f"  ✓ Foro de asesoria ya existente: {t.get('title')}")
                return f'{base.rstrip("/")}/courses/{curso_id}/discussion_topics/{t["id"]}'
    except Exception as e:
        if log:
            log(f"    ⚠ No se pudo consultar los foros: {e}")
    # no existe: crearlo
    try:
        r = _peticion('POST', url_foros, headers=h,
                      data={'title': FORO_ASESORIA,
                            'message': FORO_ASESORIA_CUERPO,
                            'discussion_type': 'threaded',
                            'published': 'true',
                            'pinned': 'true'},
                      reintentos=2, timeout=60)
        tid = r.json().get('id')
        if log:
            log(f"  ✓ Foro creado y publicado: {FORO_ASESORIA}")
        return f'{base.rstrip("/")}/courses/{curso_id}/discussion_topics/{tid}'
    except Exception as e:
        if log:
            log(f"    ⚠ No se pudo crear el Foro de asesoria: {e}")
    return None


def _nombre_asignatura(canvas, plan):
    """Solo el nombre de la ASIGNATURA en la página de inicio: se retiran las
    palabras del curso contenedor ("Metacurso", "Curso", "Plantilla") y los
    sufijos de código o paralelo que traía el título del curso viejo."""
    nombre = (plan.get('curso') or canvas.get('nombre') or 'Asignatura').strip()
    nombre = re.sub(r'^\s*(meta\s*curso|metacurso|curso|plantilla|copia\s+de)\s*[-:–]?\s*',
                    '', nombre, flags=re.I)
    nombre = re.sub(r'\s*[-–|]\s*(meta\s*curso|metacurso)\b.*$', '', nombre, flags=re.I)
    nombre = re.sub(r'\s*\((?:[^)]*\b(?:paralelo|nrc|c[oó]digo)\b[^)]*)\)\s*$', '',
                    nombre, flags=re.I)
    return nombre.strip(' -–:|') or 'Asignatura'



def _intros_semana_viejas(canvas, ras_curso=()):
    """Introduccion de SEMANA de cada semana ANTIGUA: el texto que va ENCIMA
    del encabezado "Unidad N." (posicion = definicion).

    Debajo del titulo esta la introduccion de UNIDAD, que no se toca.
    Se descartan los Resultados de aprendizaje y las frases genericas de
    plantilla, que aparecen igual en todas las semanas."""
    ras_norm = {re.sub(r'\s+', ' ', (r or '')).strip().lower() for r in ras_curso}
    out = {}
    for m in canvas['modulos']:
        for it in m['items']:
            n = _num_semana(it.get('titulo'))
            if not n:
                continue
            html = it.get('html') or ''
            corte = RE_HEAD_UNIDAD.search(html)
            cab = html[:corte.start()] if corte else html
            cab = _quitar_ruido_intro(_limpiar(cab, conservar_clases=True))
            partes = []
            for mp in re.finditer(r'<(p|div|h[1-6]|li)\b[^>]*>(.*?)</\1>', cab, re.S | re.I):
                tag, bloque = mp.group(1).lower(), mp.group(0)
                txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', mp.group(2))).strip()
                if tag.startswith('h'):
                    continue
                if not txt or len(txt) < 40:
                    continue
                if RE_GENERICAS_INTRO.search(txt):
                    continue
                if txt.lower() in ras_norm:
                    continue
                partes.append(bloque)
            frag = ''.join(partes).strip()
            if frag and len(re.sub(r'<[^>]+>', '', frag).strip()) > 60:
                out[n] = frag
    return out


RE_GENERICAS_INTRO = re.compile(
    r'(contenidos,?\s*recursos\s*y\s*actividades|actividades\s+de\s+aprendizaje\s+recomendadas|'
    r'resultados?\s+de\s+aprendizaje|recuerde\s+revisar\s+de\s+manera\s+paralela|'
    r'competencias?\s*:)', re.I)


def _intros_unidad(canvas, sin_imagenes=True):
    """Descripciones que el curso viejo traia por semana ANTES del primer
    tema (entre el encabezado "Unidad N." y el primer X.Y). Se recogen en
    orden de semana, por unidad: son las fuentes con las que el agente IA
    genera UNA introduccion por unidad en la semana nueva."""
    out = {}
    for m in canvas['modulos']:
        for it in m['items']:
            t = (it.get('titulo') or '').strip()
            if not re.match(r'^Semana\s+\d+', t):
                continue
            html = it.get('html') or ''
            for mu in RE_HEAD_UNIDAD.finditer(html):
                n = int(mu.group(2))
                # La introduccion de UNIDAD es SOLO lo que va DEBAJO del
                # encabezado "Unidad N.". Lo que va ENCIMA es la frase de
                # inicio de la semana (la usa el Agente A3 para la
                # introduccion semanal) y NO debe mezclarse aqui.
                antes = ''
                # ── texto DESPUÉS del encabezado, hasta el primer tema ──
                ini = html.find('</h', mu.end())
                ini = html.index('>', ini) + 1
                fin = len(html)
                mh = RE_HEAD.search(html, ini)
                while mh:
                    txt = re.sub('<[^>]+>', '', mh.group(2)).replace('\xa0', ' ').strip()
                    if re.match(r'^\d+\.\d+', txt) or re.match(r'^Unidad\s+\d+\.', txt, re.I):
                        fin = mh.start(); break
                    mh = RE_HEAD.search(html, mh.end())
                despues = _quitar_ruido_intro(_limpiar(html[ini:fin], sin_imagenes=sin_imagenes,
                                                      conservar_clases=True))
                frag = ((antes or '') + (despues or '')).strip()
                if frag and len(re.sub('<[^>]+>', '', frag).strip()) > 40:
                    out.setdefault(n, []).append(frag)
    return out



RE_TAB_SEMANA = re.compile(
    r'<(a|button|li|span|strong|em|h[1-6])\b[^>]*>\s*Semana\s+\d+(?:\s*y\s*\d+)?\s*</\1>', re.I)

def _quitar_ruido_intro(frag):
    """Limpia de las fuentes de introducción el ruido de la página vieja:
    · los botones/pestañas de navegación "Semana 1", "Semana 3 Semana 4"…
      (el agente podría suponer de ahí una ubicación temporal y generar mal);
    · el recordatorio genérico "Recuerde revisar de manera paralela los
      contenidos con las actividades…", que es plantilla, no descripción."""
    if not frag:
        return frag
    prev = None
    while prev != frag:            # pestañas anidadas (<li><a>Semana 1</a></li>)
        prev = frag
        frag = RE_TAB_SEMANA.sub('', frag)
    frag = re.sub(r'<p[^>]*>(?:(?!</p>).)*?Recuerde\s+revisar\s+de\s+manera\s+paralela'
                  r'(?:(?!</p>).)*?</p>', '', frag, flags=re.S | re.I)
    # elementos que quedaron vacíos tras quitar las pestañas
    frag = re.sub(r'<(p|li|ul|ol|div)\b[^>]*>\s*</\1>', '', frag)
    return frag


RE_CONT_RECURSOS = re.compile(r'<div class="(?:contenedor-recursos|container-resources)"[^>]*>', re.I)

def _extraer_autoevaluaciones(html):
    """Separa del bloque de actividades las AUTOEVALUACIONES embebidas
    (contenedor-recursos cuyo iframe tiene title ~ 'Autoeval'). Devuelve
    (html_sin_autoevals, [bloques]) donde cada bloque incluye el parrafo
    descriptivo inmediatamente anterior si existe, y el iframe INTACTO."""
    if not html:
        return html, []
    autoevals, cortes = [], []
    for m in RE_CONT_RECURSOS.finditer(html):
        j = m.end(); nivel, k, c = 1, m.end(), -1
        while nivel:
            a = html.find('<div', k); c = html.find('</div>', k)
            if c == -1: break
            if a != -1 and a < c: nivel += 1; k = a + 4
            else: nivel -= 1; k = c + 6
        if c == -1: continue
        bloque_html = html[m.start():k]
        tit = re.search(r'<iframe[^>]*title="([^"]*)"', bloque_html, re.I)
        if not (tit and re.search(r'autoeval', tit.group(1), re.I)):
            continue
        ini = m.start()
        # parrafo descriptivo inmediatamente anterior → descripcion
        prev = re.search(r'(<p\b[^>]*>(?:(?!</p>).)*</p>)\s*$', html[:m.start()], re.S)
        if prev and not re.search(r'<(img|iframe)', prev.group(1), re.I):
            ini = prev.start(1)
            bloque_html = prev.group(1) + bloque_html
        autoevals.append(bloque_html)
        cortes.append((ini, k))
    for ini, fin in reversed(cortes):
        html = html[:ini] + html[fin:]
    return html, autoevals


def _rango_temas(temas_html):
    """'(1.1 al 2.2)' segun los temas consolidados en la semana."""
    cods = [t['codigo'] for t in temas_html]
    if not cods:
        return ''
    if len(cods) == 1:
        return f'({cods[0]})'
    return f'({cods[0]} al {cods[-1]})'


RE_OL = re.compile(r'<ol\b([^>]*)>', re.I)

RE_TRANSICION = re.compile(
    r'<p>\s*Estimado estudiante[^<]*?'
    r'(?:actividad(?:es)? (?:de aprendizaje )?recomendada|desarroll)[^<]*?</p>',
    re.I | re.S)

def _quitar_transicion_actividades(html):
    """Elimina la linea puente 'Estimado estudiante, una vez culminada la
    semana X, lo invito a realizar las siguientes actividades recomendadas'
    que precede al bloque de actividades. El rango de temas ya se muestra en
    el titulo de la pestaña; ademas esa frase arrastraba una lista <ol> con
    'start' que causaba el salto de numeracion (8 -> 12)."""
    return RE_TRANSICION.sub('', html)


def _rotulo_rango_actividades(codigos):
    """Texto del subtitulo de un bloque de actividades, sin el <h4>.

    Formato acordado: 'Actividades del tema 1.1. al tema 1.5.' (con punto
    final en cada codigo). Con un solo tema: 'Actividades del tema 2.5.'.
    Devuelve '' si no hay codigos.
    """
    if not codigos:
        return ''
    cods = sorted(set(codigos), key=lambda c: [int(x) for x in c.split('.')])
    if len(cods) == 1:
        return f'Actividades del tema {cods[0]}.'
    return f'Actividades del tema {cods[0]}. al tema {cods[-1]}.'


def _desenvolver_divs(html):
    """Quita los <div> contenedores que solo aportan margenes.

    El curso viejo trae la metodologia (y otros bloques del inicio) dentro de
    un <div class="contenido-informacion">; _limpiar le quita la clase y deja
    un <div> suelto que, ya dentro de #learning_methodology, solo genera
    margenes indeseados.

    Se usa BeautifulSoup (que ya es dependencia via _balancear) en vez de
    regex: los intentos anteriores con expresiones regulares fallaban ante
    saltos de linea, atributos residuales o contenido fuera del div.
    Cualquier <div> SIN atributos utiles se reemplaza por su contenido,
    en cualquier nivel de anidamiento.
    """
    if not html or '<div' not in html:
        return html
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return html
    sopa = BeautifulSoup(html, 'html.parser')
    # varias pasadas: al desenvolver uno puede quedar otro al descubierto
    for _ in range(6):
        objetivo = None
        for d in sopa.find_all('div'):
            attrs = {k: v for k, v in (d.attrs or {}).items()
                     if k in ('class', 'id') and v}
            if not attrs:                 # <div> sin class ni id: sobra
                objetivo = d
                break
        if objetivo is None:
            break
        objetivo.unwrap()
    return str(sopa).strip()


def _titulo_bloque_actividades(codigos):
    """<h4> que encabeza cada bloque de actividades con su rango de temas."""
    rotulo = _rotulo_rango_actividades(codigos)
    if not rotulo:
        return ''
    # Sin fondo: se usa la clase oficial .subtitle-section del CSS de la
    # plantilla (texto #0a427d + barra azul a la izquierda, fondo blanco).
    # El <h4> conserva ed-act-range para poder localizarlo/retirarlo despues.
    return (f'<div class="subtitle-section ed-act-range">'
            f'<h4><em>{rotulo}</em></h4></div>')


RE_H4_RANGO = re.compile(
    r'<div class="subtitle-section ed-act-range">.*?</div>'
    r'|<h4 class="ed-act-range".*?</h4>', re.S | re.I)

RE_TAG_LISTA = re.compile(r'<(/?)(ol|ul|li)\b([^>]*)>', re.I)

def _renumerar_actividades(bloques):
    """Numeración CONSECUTIVA y sin saltos de las actividades a través de
    todos los bloques fusionados: cada <ol> de primer nivel recibe el start
    que continúa al anterior, contando SOLO los <li> de primer nivel.
    (El conteo anterior incluía los <li> de listas anidadas —p. ej. los
    "Ejemplo 1/2/3" dentro de un ítem— y producía saltos como 8→12.)
    Con una sola fuente el primer <ol> arranca en 1, igual que antes."""
    out, contador = [], 0
    for b in bloques:
        res, idx, pila = [], 0, []
        for m in RE_TAG_LISTA.finditer(b):
            res.append(b[idx:m.start()])
            cierra, tag = m.group(1) == '/', m.group(2).lower()
            tok = m.group(0)
            if tag in ('ol', 'ul'):
                if cierra:
                    if pila:
                        pila.pop()
                    res.append(tok)
                else:
                    if tag == 'ol' and not pila:
                        attrs = re.sub(r'\s+start="[^"]*"', '', m.group(3))
                        if contador:
                            attrs += f' start="{contador + 1}"'
                        res.append('<ol' + attrs + '>')
                    else:
                        res.append(tok)
                    pila.append(tag)
            else:  # <li> / </li>
                if not cierra and len(pila) == 1 and pila[0] == 'ol':
                    contador += 1
                res.append(tok)
            idx = m.end()
        res.append(b[idx:])
        out.append(''.join(res))
    return out


def _paginas_adicionales(canvas):
    """Paginas del PROPIO curso enlazadas desde una semana vieja que no son
    semanas ni paginas generales: pertenecen al contenido de esa semana y
    deben agregarse al final de la semana nueva que la reciba.
    Devuelve {num_semana_vieja: [{'titulo','slug','html'}]}."""
    generales = ('datos-generales', 'informacion-general', 'perfil-del-profesor',
                 'horario-de-tutorias', 'anexos', 'autoevaluaciones', 'creditos',
                 'referencias-bibliograficas', 'inicio', 'encuentros', 'fuentes-y-recursos')
    por_slug = {}
    for m in canvas['modulos']:
        for it in m['items']:
            slug = (it.get('slug') or '').lower()
            if slug:
                por_slug[slug] = it
    out = {}
    for m in canvas['modulos']:
        for it in m['items']:
            t = (it.get('titulo') or '').strip()
            mw = re.match(r'^Semana\s+(\d+)', t)
            if not mw:
                continue
            nsem = int(mw.group(1))
            html = it.get('html') or ''
            links = set(re.findall(r'/pages/([a-z0-9-]+)', html))
            for slug in sorted(links):
                if slug.startswith('semana') or slug.startswith('g') and len(slug) == 33:
                    continue
                if any(g in slug for g in generales):
                    continue
                pagina = por_slug.get(slug)
                if not pagina or not pagina.get('html'):
                    continue
                out.setdefault(nsem, [])
                if slug not in [x['slug'] for x in out[nsem]]:
                    out[nsem].append({'titulo': pagina.get('titulo') or slug,
                                      'slug': slug, 'html': pagina['html']})
    return out


def validar_consistencia(plan):
    """Validacion previa a publicar: semanas y bimestres.
    Bimestre por convencion UTPL: semanas 1-8 → bimestre 1; 9-16 → bimestre 2.
    Devuelve [{tipo, semana, bimestre, recomendacion}]."""
    alertas = []
    def _bim(n):
        return 1 if n <= 8 else 2
    nums = []
    for sem in plan['semanas'].keys():
        m = re.search(r'\d+', sem)
        if not m:
            alertas.append({'tipo': 'Nombre de semana invalido', 'semana': sem,
                            'bimestre': '-', 'recomendacion': 'Usar el formato "Semana N".'})
            continue
        nums.append(int(m.group()))
    dup = sorted({n for n in nums if nums.count(n) > 1})
    for n in dup:
        alertas.append({'tipo': 'Semana duplicada', 'semana': f'Semana {n}',
                        'bimestre': _bim(n),
                        'recomendacion': 'Unificar o renombrar: cada semana debe aparecer una sola vez.'})
    if nums:
        esperadas = list(range(1, max(nums) + 1))
        omitidas = [n for n in esperadas if n not in nums]
        for n in omitidas:
            alertas.append({'tipo': 'Semana omitida', 'semana': f'Semana {n}',
                            'bimestre': _bim(n),
                            'recomendacion': 'Agregar la semana faltante o renumerar las siguientes.'})
        if nums != sorted(nums):
            alertas.append({'tipo': 'Orden de semanas incorrecto', 'semana': '-', 'bimestre': '-',
                            'recomendacion': 'Reordenar el plan: las semanas deben ir de la 1 en adelante.'})
    # correspondencia de bimestres: aplica solo si el curso NUEVO abarca dos
    # bimestres (más de 8 semanas); si todo el curso nuevo es de un bimestre,
    # la consolidación desde el bimestre 2 viejo es intencional por diseño
    curso_bibimestral = bool(nums) and max(nums) > 8
    for sem, d in plan['semanas'].items():
        m = re.search(r'\d+', sem)
        if not m:
            continue
        bim_destino = _bim(int(m.group()))
        origenes = set()
        for t in d.get('temas', []):
            mo = re.search(r'\d+', str(t.get('semana_canvas') or ''))
            if mo:
                origenes.add(_bim(int(mo.group())))
        for bo in (sorted(origenes - {bim_destino}) if curso_bibimestral else []):
            alertas.append({'tipo': 'Cruce de bimestre', 'semana': sem, 'bimestre': bim_destino,
                            'recomendacion': f'La semana recibe contenido del bimestre {bo} del curso '
                                             f'viejo; verificar que la reubicacion sea intencional.'})
        if not d.get('temas'):
            alertas.append({'tipo': 'Semana sin temas', 'semana': sem, 'bimestre': bim_destino,
                            'recomendacion': 'Asignar temas o eliminar la semana del plan.'})

    # ---- Unidades tocadas: temas eliminados, agregados o modificados --------
    # Si en una unidad se elimina o agrega un tema (p. ej. se elimina el 4.4 de
    # la Unidad 4), las actividades recomendadas y la autoevaluacion de ESA
    # unidad pueden quedar con ejercicios o preguntas de temas que ya no estan,
    # o sin cubrir los nuevos. El QA debe revisarlas una por una.
    cambios = {}   # unidad -> {'del': [...], 'add': [...], 'mod': [...], 'semanas': set()}
    for sem, d in plan['semanas'].items():
        for t in (d.get('temas') or []):
            cod = str(t.get('codigo') or '')
            mu = re.match(r'^(\d+)\.', cod)
            if not mu:
                continue
            uni = int(mu.group(1))
            if t.get('accion') == 'del':
                clave = 'del'
            elif t.get('origen') == 'nuevo':
                clave = 'add'
            elif t.get('accion') == 'mod':
                clave = 'mod'
            else:
                continue
            reg = cambios.setdefault(uni, {'del': [], 'add': [], 'mod': [], 'semanas': set()})
            if cod not in reg[clave]:
                reg[clave].append(cod)
            reg['semanas'].add(sem)

    # El Excel de ajustes NO marca los temas eliminados dentro de la semana:
    # los deja en una lista aparte del plan (plan['eliminados']), porque la
    # eliminacion se representa por AUSENCIA del tema en la reubicacion.
    # Sin leer esa lista, eliminar el 4.4 no generaba ninguna alerta.
    # el tablero manda 'eliminar'; parsear_ajustes usa 'eliminados'
    for elim in ((plan.get('eliminar') or []) + (plan.get('eliminados') or [])):
        cod = str((elim or {}).get('codigo') or '') if isinstance(elim, dict) else str(elim or '')
        mu = re.match(r'^(\d+)\.', cod)
        if not mu:
            continue
        uni = int(mu.group(1))
        reg = cambios.setdefault(uni, {'del': [], 'add': [], 'mod': [], 'semanas': set()})
        if cod not in reg['del']:
            reg['del'].append(cod)
        # semana NUEVA donde quedo esa unidad (la del curso viejo ya no existe)
        for sem2, d2 in (plan.get('semanas') or {}).items():
            for t2 in (d2.get('temas') or []):
                m2 = re.match(r'^(\d+)\.', str(t2.get('codigo') or ''))
                if m2 and int(m2.group(1)) == uni:
                    reg['semanas'].add(sem2)
                    break

    for uni in sorted(cambios):
        reg = cambios[uni]
        detalle = []
        if reg['del']:
            detalle.append('eliminado(s) ' + ', '.join(sorted(reg['del'])))
        if reg['add']:
            detalle.append('agregado(s) ' + ', '.join(sorted(reg['add'])))
        if reg['mod']:
            detalle.append('modificado(s) ' + ', '.join(sorted(reg['mod'])))
        sems = sorted(reg['semanas'], key=lambda x: (_num_semana(x) or 0))
        sem_txt = ', '.join(sems) if sems else '-'
        bim_txt = (_bim(_num_semana(sems[0])) if sems and _num_semana(sems[0]) else '-')
        alertas.append({
            'tipo': f'Revisar actividades y autoevaluación · Unidad {uni}',
            'semana': sem_txt, 'bimestre': bim_txt, 'unidad': uni,
            'recomendacion': (
                f'La Unidad {uni} cambió: {"; ".join(detalle)}. '
                f'Revisar las ACTIVIDADES RECOMENDADAS y la AUTOEVALUACIÓN de esta unidad: '
                f'pueden conservar ejercicios o preguntas de temas que ya no existen, '
                f'o no cubrir los temas nuevos.')})
    return alertas


def _semanas_de_codigo(canvas):
    """{codigo_top: [nums de semanas viejas donde aparece]} — incluye las
    CONTINUACIONES de un tema en semanas posteriores, para que sus
    actividades y autoevaluaciones tambien migren a la semana nueva."""
    out = {}
    for m in canvas['modulos']:
        for it in m['items']:
            t = (it.get('titulo') or '').strip()
            mw = re.match(r'^Semana\s+(\d+)', t)
            if not mw:
                continue
            nsem = int(mw.group(1))
            for h in RE_HEAD.finditer(it.get('html') or ''):
                txt = re.sub('<[^>]+>', '', h.group(2)).replace('\xa0', ' ').strip()
                mm = re.match(r'^(\d+\.\d+)(?:\.\d+)?\.?(\s+|$)', txt)
                if mm:
                    out.setdefault(mm.group(1), [])
                    if nsem not in out[mm.group(1)]:
                        out[mm.group(1)].append(nsem)
    return out


def _material_viejo(canvas):
    """Por semana vieja: nº de RA, contextualización y actividades recomendadas.
    Índice de contextualización POR RA (primera aparición): si varias semanas
    comparten RA, la contextualización es la misma y no se regenera."""
    por_semana, ctx_por_ra = {}, {}
    for m in canvas['modulos']:
        for it in m['items']:
            t = (it.get('titulo') or '').strip()
            mm = re.match(r'^Semana\s+(\d+)', t)
            if not mm:
                continue
            html = it.get('html') or ''
            info = {'ra': None, 'contexto': None, 'actividades': None, 'evaluadas': None, 'autoevals': []}
            r = RE_RA_PAG.search(html)
            if r:
                info['ra'] = int(r.group(1))
            i = html.find('class="contextualizacion-semana"')
            if i != -1:
                info['contexto'] = _div_balanceado(html, html.rfind('<div', 0, i))
            i = html.find('class="actividad-recomendada"')
            if i != -1:
                acts = _div_balanceado(html, html.rfind('<div', 0, i))
                acts = _quitar_transicion_actividades(acts)
                acts, autos = _extraer_autoevaluaciones(acts)
                acts = _quitar_invitaciones_autoeval(acts)
                info['actividades'] = acts
                info['autoevals'] = autos
            me = re.search(r'Actividad(?:es)? de aprendizaje evaluadas?', html, re.I)
            if me:
                j = html.find('<div class="contenedor-flex', me.end())
                if j != -1:
                    info['evaluadas'] = _div_balanceado(html, j)
            por_semana[int(mm.group(1))] = info
            if info['ra'] and info['contexto']:
                ctx_por_ra.setdefault(info['ra'], info['contexto'])
    return por_semana, ctx_por_ra


def _num_semana(v):
    if v is None:
        return None
    m = re.search(r'\d+', str(v))
    return int(m.group()) if m else None


# Acepta el focalizador viejo (class="focalizador") y tambien el ya renombrado
# a "focuser" SIN tipo: _normalizar_tablas -> _migrar_clases renombra
# focalizador->focuser antes de esta conversion, y si aqui solo se buscara la
# clase vieja el focalizador quedaba sin tipo y con la imagen del curso viejo.
# Un focuser que YA tiene tipo (focuser video/reading/reflection/important)
# no se vuelve a tocar.
RE_FOCALIZADOR = re.compile(
    r'<div[^>]*\bclass="(?:focalizador|focuser)"[^>]*>', re.I)


def _tipo_focalizador(texto_html, icono_viejo=''):
    """Coteja el focalizador viejo con su equivalente de la plantilla nueva.
    1º por el TEXTO (es lo más fiable: "le invito a leer…", "observe el
    video…", "reflexione…"); 2º por el nombre/alt del ícono viejo; si nada
    coincide → important (y el llamador deja marca para el revisor)."""
    t = re.sub(r'<[^>]+>', ' ', texto_html or '').lower()
    ic = (icono_viejo or '').lower()
    _tipo_focalizador.seguro = True

    # 1) COTEJO POR EL ICONO VIEJO (prioritario): el nombre del archivo del
    #    focalizador antiguo es la fuente mas fiable, porque el diseñador ya
    #    eligio el tipo. El texto solo decide cuando el icono no dice nada.
    # nomenclatura oficial de la plantilla (Plantilla/Focalizadores/):
    # f_importante.png · f_lectura.png · f_reflexione.png · f_video.png
    if re.search(r'f_video', ic):
        return 'video', 'f_video.png'
    if re.search(r'f_lectura', ic):
        return 'reading', 'f_lectura.png'
    if re.search(r'f_reflexione', ic):
        return 'reflection', 'f_reflexione.png'
    if re.search(r'f_importante', ic):
        return 'important', 'f_importante.png'
    if re.search(r'(video|play|reproduc|multimedia|tv|youtube)', ic):
        return 'video', 'f_video.png'
    if re.search(r'(lectura|leer|lea|libro|book|documento|doc|pdf|texto)', ic):
        return 'reading', 'f_lectura.png'
    if re.search(r'(reflex|reflexione|idea|foco|bombill|pensar|piensa|cerebro|medita)', ic):
        return 'reflection', 'f_reflexione.png'
    if re.search(r'(important|importante|exclama|atenci|alerta|admiraci|aviso|nota|'
                 r'mano|dedo|senal|señal|puntero|recuerde|clave)', ic):
        return 'important', 'f_importante.png'

    # 2) COTEJO POR EL TEXTO
    if re.search(r'\b(video|v[ií]deo|videoconferencia|observe\s+el|mire\s+el)\b', t) \
            and re.search(r'v[ií]deo', t):
        return 'video', 'f_video.png'
    if re.search(r'(invito\s+a\s+leer|le[ae]r?\s+el\s+(documento|art[ií]culo|cap[ií]tulo)|'
                 r'lectura|revise\s+el\s+(documento|texto)|documento\s+denominado)', t):
        return 'reading', 'f_lectura.png'
    if re.search(r'(reflexion|medite|piense|preg[uú]ntese|an[aá]lice\s+y\s+responda)', t):
        return 'reflection', 'f_reflexione.png'
    # motivacionales / avisos de arranque: son 'importante' de forma SEGURA,
    # no un fallback (p. ej. "¡es hora de empezar este proceso!", "recuerde que…")
    if re.search(r'(es\s+hora\s+de|manos\s+a\s+la\s+obra|comencemos|empecemos|'
                 r'recuerde\s+que|tenga\s+presente|no\s+olvide|es\s+importante|'
                 r'tome\s+en\s+cuenta|le\s+deseo|[¡!])', t):
        return 'important', 'f_importante.png'

    _tipo_focalizador.seguro = False   # no se pudo cotejar: que confirme el revisor
    return 'important', 'f_importante.png'


def _convertir_focalizadores(html):
    """Focalizadores del curso viejo (div.focalizador con su imagen antigua)
    → formato oficial de la plantilla nueva:
        <div class="focuser {tipo}"><p><img f_{tipo}.png></p>
          <div class="content-focuser">texto</div></div>
    El tipo se COTEJA con el focalizador viejo: primero por el texto
    (invitación a leer / ver video / reflexionar) y si no, por el nombre o
    alt de su ícono; si nada coincide queda 'important' con marca data-ia
    para que el revisor confirme."""
    out, pos = [], 0
    for m in RE_FOCALIZADOR.finditer(html):
        if m.start() < pos:
            continue
        # extraer el div balanceado
        j = m.end()
        nivel, k, c = 1, j, -1
        while nivel:
            a = html.find('<div', k)
            c = html.find('</div>', k)
            if c == -1:
                break
            if a != -1 and a < c:
                nivel += 1; k = a + 4
            else:
                nivel -= 1; k = c + 6
        if c == -1:
            break
        inner = html[j:c]
        # ícono viejo (src/alt) ANTES de quitarlo: sirve para cotejar el tipo
        icono_viejo = ' '.join(re.findall(r'<img[^>]*(?:src|alt)="([^"]*)"', inner, re.I))
        # quitar la imagen vieja del focalizador y quedarnos con el texto
        inner = re.sub(r'<p[^>]*>\s*<img[^>]*>\s*</p>', '', inner, count=1)
        inner = re.sub(r'<img[^>]*>', '', inner)
        # desenvolver el div contenedor del texto si existe
        mm = re.match(r'\s*<div[^>]*>(.*)</div>\s*$', inner, re.S)
        if mm:
            inner = mm.group(1)
        tipo, icono = _tipo_focalizador(inner, icono_viejo)
        marca = ('' if tipo != 'important' or _tipo_focalizador.seguro else
                 ' data-ia="focalizador-tipo" data-ia-nota="confirmar tipo: '
                 'video / reflection / reading / important"')
        nuevo = (f'<div class="focuser {tipo}"{marca}>'
                 '<p style="text-align: center;"><img role="presentation" '
                 f'src="@@PLANTILLA@@/Plantilla/Focalizadores/{icono}" '
                 'alt="" width="80" height="80" loading="lazy"></p>'
                 f'<div class="content-focuser">{inner.strip()}</div></div>')
        out.append(html[pos:m.start()])
        out.append(nuevo)
        pos = k
    out.append(html[pos:])
    return ''.join(out)


RE_TABLE_TAG = re.compile(r'<table\b([^>]*)>', re.I)


# La plantilla oficial renombró sus clases: el contenido del curso viejo aún
# trae las antiguas y por eso no tomaba el formato nuevo.
CLASES_RENOMBRADAS = {
    'contenedor-figura': 'container-figure',
    'contenedor-imagen': 'container-figure',
    'tabla-general': 'table-general',
    'tabla-diseno': 'table-design',
    'tabla-diseño': 'table-design',
    'contenedor-recursos': 'container-resources',
    'focalizador': 'focuser',
}

def _migrar_clases(html):
    """Sustituye las clases viejas por su equivalente de la plantilla nueva
    (p. ej. contenedor-figura → container-figure, tabla-general → table-general)."""
    if not html:
        return html
    def _sub(m):
        valores = [CLASES_RENOMBRADAS.get(c, c) for c in m.group(2).split()]
        # sin duplicados y conservando el orden
        vistos, out = set(), []
        for c in valores:
            if c not in vistos:
                vistos.add(c); out.append(c)
        return f'{m.group(1)}="{" ".join(out)}"'
    return re.sub(r'\b(class)="([^"]*)"', _sub, html)


def _normalizar_tablas(html, clase='table-general'):
    """Las tablas del curso viejo no traen las clases de la plantilla nueva
    (table-general / table-design) y por eso no toman su formato. Además se
    migran las clases renombradas por la plantilla oficial."""
    html = _migrar_clases(html)
    def _sub(m):
        attrs = m.group(1)
        if 'table-general' in attrs or 'table-design' in attrs:
            return m.group(0)
        if 'class="' in attrs:
            attrs = re.sub(r'class="[^"]*"', 'class="' + clase + '"', attrs)
        else:
            attrs = ' class="' + clase + '"' + attrs
        return '<table' + attrs + '>'
    html = RE_TABLE_TAG.sub(_sub, html)
    html = _normalizar_captions(html)
    return _limpiar_p_en_celdas(html)


DATOS_DOCENTE = ('tercer nivel', 'cuarto nivel', 'departamento')


def _datos_docente_a_lista(html):
    """Los datos del docente (titulo de tercer y cuarto nivel, departamento)
    van en un <ul> con viñetas.

    En algunos cursos vienen como <p> sueltos y quedaban sin viñeta. Los <p>
    consecutivos que corresponden a esos datos se agrupan en una sola lista;
    si ya estan en un <ul>, no se toca nada.
    """
    if not html:
        return html
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return html
    sopa = BeautifulSoup(html, 'html.parser')

    def _es_dato(tag):
        if tag.name != 'p':
            return False
        txt = tag.get_text(' ', strip=True).lower()
        return any(k in txt for k in DATOS_DOCENTE)

    # agrupar corridas de <p> que son datos del docente
    for p in list(sopa.find_all('p')):
        if p.parent is None or not _es_dato(p):
            continue
        grupo, sig = [p], p.find_next_sibling()
        while sig is not None and _es_dato(sig):
            grupo.append(sig)
            sig = sig.find_next_sibling()
        ul = sopa.new_tag('ul')
        for tag in grupo:
            li = sopa.new_tag('li')
            for hijo in list(tag.contents):
                li.append(hijo.extract())
            ul.append(li)
        grupo[0].insert_before(ul)
        for tag in grupo:
            tag.decompose()
    return str(sopa)


def _centrar_horas(html):
    """Centra SOLO la columna de horas de la tabla de carga horaria.

    La primera columna (el componente) se deja alineada a la izquierda; se
    centran las demas, que son las que contienen el numero de horas.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return html
    sopa = BeautifulSoup(html, 'html.parser')
    tabla = sopa.find('table')
    if tabla is None:
        return html
    for fila in tabla.find_all('tr'):
        celdas = fila.find_all(['td', 'th'])
        for i, c in enumerate(celdas):
            if i == 0:
                continue          # el nombre del componente no se centra
            estilo = (c.get('style') or '').rstrip(';')
            if 'text-align' in estilo:
                continue          # ya trae alineacion propia: se respeta
            c['style'] = (estilo + ';' if estilo else '') + 'text-align: center;'
    return str(sopa)


RE_CAPTION = re.compile(r'(<caption\b[^>]*>)(.*?)(</caption>)', re.S | re.I)


def _normalizar_captions(html):
    """El titulo del caption va SIEMPRE en cursiva.

    Las tablas numeradas ya traen '<strong>Tabla N</strong><br><em>titulo</em>'.
    Las que solo tienen titulo (p. ej. la de Carga horaria / Numero de horas)
    venian en texto plano y se veian distintas: aqui se les pone <em> al
    titulo para que todas las tablas usen el mismo formato.
    """
    def _cap(m):
        apertura, dentro, cierre = m.group(1), m.group(2), m.group(3)
        # ¿ya tiene cursiva en la parte del titulo? entonces no se toca
        if re.search(r'<(em|i)\b', dentro, re.I):
            return m.group(0)
        mnum = re.search(r'(<strong\b[^>]*>\s*Tabla\s*\d+\s*</strong>\s*(?:<br\s*/?>)?)',
                         dentro, re.I)
        if mnum:
            cabecera = mnum.group(1)
            titulo = dentro[mnum.end():].strip()
            if not titulo:
                return m.group(0)
            return f'{apertura}{cabecera}<em>{titulo}</em>{cierre}'
        titulo = dentro.strip()
        if not titulo:
            return m.group(0)
        return f'{apertura}<em>{titulo}</em>{cierre}'
    return RE_CAPTION.sub(_cap, html)


RE_CELDA = re.compile(r'<(t[hd])\b([^>]*)>(.*?)</\1>', re.S | re.I)
RE_P_SUELTO = re.compile(r'<p\b[^>]*>(.*?)</p>', re.S | re.I)

def _limpiar_p_en_celdas(html):
    """Dentro de las celdas de una tabla: si hay UN solo <p>, se le quita la
    etiqueta y el contenido queda directamente en la celda (así toma el
    formato de la plantilla); si hay VARIOS <p>, se conservan todos."""
    def _celda(m):
        tag, attrs, dentro = m.group(1), m.group(2), m.group(3)
        ps = RE_P_SUELTO.findall(dentro)
        if len(ps) == 1:
            solo = RE_P_SUELTO.sub('', dentro).strip()
            if not solo:      # el <p> es todo el contenido de la celda
                return f'<{tag}{attrs}>{ps[0].strip()}</{tag}>'
        return m.group(0)
    return RE_CELDA.sub(_celda, html)



def _aplicar_reemplazos(html, reemplazos):
    """Sustituciones textuales definidas por el revisor en el tablero
    (p. ej. corregir/eliminar una frase con referencia temporal). Se aplican
    ANTES de marcar referencias, sobre el texto tal cual del contenido."""
    for r in reemplazos or []:
        buscar = (r.get('buscar') or '').strip()
        if buscar and buscar in html:
            html = html.replace(buscar, (r.get('reemplazar') or '').strip())
    return html



RE_P_BOTON_MAS = re.compile(r'<p[^>]*>(?:(?!</p>).)*?/pages/(?:(?!</p>).)*?</p>', re.S | re.I)

def _items_por_slug(canvas):
    out = {}
    for m in canvas['modulos']:
        for it in m['items']:
            slug = (it.get('slug') or '').lower()
            if slug:
                out[slug] = it
    # páginas sueltas (fuera de módulos) enlazadas por "Continuar", que
    # extraer_canvas descarga aparte
    for slug, pg in (canvas.get('paginas_enlazadas') or {}).items():
        out.setdefault(slug.lower(), pg)
    return out


def _embeber_boton_mas(html, por_slug, consumidos):
    """El botón 'Continuar' (a.boton-mas) enlazaba una página del propio curso
    con la continuación del tema. En el curso nuevo esa página NO va aparte:
    su contenido se EMBEBE en el punto exacto del botón y el botón se elimina,
    de modo que el tema (p. ej. 2.4) siga de corrido."""
    def _sub(m):
        bloque = m.group(0)
        # botón/enlace de continuación: clase boton-mas O texto "Continuar"
        if 'boton-mas' not in bloque and not re.search(r'continuar', bloque, re.I):
            return bloque
        ms = re.search(r'href="[^"]*/pages/([^"/?#]+)', bloque, re.I)
        if not ms:
            return bloque
        slug = ms.group(1).lower()
        pag = por_slug.get(slug)
        cuerpo = (pag or {}).get('html')
        if not cuerpo:
            return bloque
        consumidos.add(slug)
        cuerpo = re.sub(r'<link[^>]*>|<script[^>]*>.*?</script>', '', cuerpo, flags=re.S | re.I)
        # el "Regresar" volvía a la página original: embebido ya no existe esa
        # navegación, se elimina (con el <hr> separador si lo acompaña)
        cuerpo = re.sub(r'(?:<hr[^>]*>\s*)?<p[^>]*>(?:(?!</p>).)*?<a(?:(?!</p>).)*?regresar(?:(?!</p>).)*?</p>',
                        '', cuerpo, flags=re.S | re.I)
        return (f'<div data-origen="pagina-embebida" data-slug="{slug}">'
                + _balancear(cuerpo) + '</div>')
    # iterar: cada página embebida puede enlazar otra con su propio botón
    for _ in range(5):
        nuevo = RE_P_BOTON_MAS.sub(_sub, html)
        if nuevo == html:
            break
        html = nuevo
    return html



RE_INVITA_AUTOEVAL = re.compile(
    r'(resolver\s+la\s+siguiente\s+autoevaluaci|desarrolle\s+la\s+presente\s+autoevaluaci|'
    r'realice\s+la\s+siguiente\s+autoevaluaci)', re.I)

def _quitar_invitaciones_autoeval(html):
    """Elimina de las ACTIVIDADES los ítems/párrafos que solo invitaban a la
    autoevaluación ("resolver la siguiente autoevaluación…", "Desarrolle la
    presente autoevaluación…"): el iframe ya se trasladó a su pestaña, así que
    la invitación queda huérfana dentro de las actividades. Solo se quitan
    elementos de texto puro (sin iframes/imágenes/recursos)."""
    if not html:
        return html
    def _limpiar(patron):
        def _sub(m):
            b = m.group(0)
            if re.search(r'<(iframe|img)|contenedor-recursos|container-resources', b, re.I):
                return b
            return '' if RE_INVITA_AUTOEVAL.search(b) else b
        return re.sub(patron, _sub, html, flags=re.S | re.I)
    html = _limpiar(r'<li[^>]*>(?:(?!</?li[\s>]).)*?</li>')
    html = _limpiar(r'<p[^>]*>(?:(?!</p>).)*?</p>')
    return html



FRASE_ACTIVIDAD_UNICA = ('Continuemos con el aprendizaje mediante su participación '
                         'en la actividad que se describe a continuación:')

FRASES_ACTIVIDADES = [
    'Continuemos con el aprendizaje mediante su participación en las actividades que se '
    'describen a continuación:',
    'Reforcemos el aprendizaje resolviendo las siguientes actividades.',
    'Es momento de aplicar sus conocimientos a través de las actividades que se han '
    'planteado a continuación:',
    'Es hora de reforzar los conocimientos adquiridos resolviendo las siguientes '
    'actividades:',
]

RE_INVITA_ACTIVIDAD = re.compile(
    r'^\s*<p[^>]*>(?:(?!</p>).){0,300}?'
    r'(continuemos|avancemos|para\s+reforzar|le\s+invito|los?\s+invito|ponga\s+en\s+pr[aá]ctica)'
    r'(?:(?!</p>).)*?actividad(?:(?!</p>).)*?</p>', re.S | re.I)

def _unificar_intros_actividades(bloques, rotacion=0):
    """La frase de apertura ("Continuemos con el aprendizaje mediante su
    participación…") es por defecto y va UNA sola vez al inicio: se elimina la
    invitación propia de cada bloque fuente y se antepone una frase del
    listado rotativo (cambia de semana en semana para no repetirse)."""
    if not bloques:
        return bloques
    limpios = list(bloques)
    # UNA sola actividad → frase oficial singular fija; VARIAS → rotación
    # entre las frases oficiales plurales (cambia de semana en semana)
    if _contar_items_primer_nivel(''.join(bloques)) <= 1:
        frase = FRASE_ACTIVIDAD_UNICA
    else:
        frase = FRASES_ACTIVIDADES[rotacion % len(FRASES_ACTIVIDADES)]
    limpios[0] = f'<p data-origen="frase-actividades">{frase}</p>' + limpios[0]
    return limpios


def _contar_items_primer_nivel(html):
    """Cuenta las actividades: <li> de primer nivel dentro de <ol> (las listas
    anidadas no cuentan, igual que en la renumeración)."""
    n, pila = 0, []
    for m in RE_TAG_LISTA.finditer(html or ''):
        cierra, tag = m.group(1) == '/', m.group(2).lower()
        if tag in ('ol', 'ul'):
            if cierra:
                if pila:
                    pila.pop()
            else:
                pila.append(tag)
        elif not cierra and len(pila) == 1 and pila[0] == 'ol':
            n += 1
    return n


FRASES_AUTOEVAL = [
    'Estimado estudiante, para evaluar los aprendizajes adquiridos sobre la unidad {u}, '
    'le invito a desarrollar la autoevaluación que a continuación se presenta.',
    'Le invito a reforzar los conocimientos de la unidad {u}, participando en la '
    'siguiente autoevaluación:',
]


def _unificar_intros_autoeval(bloques, rotacion=0):
    """En la pestaña Autoevaluación, cada bloque traía su frase "Ha finalizado
    el estudio de la segunda/cuarta unidad…", que repetida se ve mal y usa la
    numeración vieja. Se quitan todas y se antepone UNA sola introducción
    genérica de la semana."""
    limpios = []
    for i, b in enumerate(bloques):
        # quitar la frase vieja ("Ha finalizado el estudio de la X unidad…"),
        # que repetida se veía mal y usaba la numeración vieja
        b2 = re.sub(r'^\s*<p[^>]*>(?:(?!</p>).)*?ha\s+finalizado\s+el\s+estudio(?:(?!</p>).)*?</p>',
                    '', b, count=1, flags=re.S | re.I)
        # frase OFICIAL rotativa antes de CADA autoevaluación, con el número
        # de la unidad (tomado del título del recurso: "Autoevaluación N")
        mn = re.search(r'autoevaluaci[oó]n\s+(\d+)', b, re.I)
        u_txt = mn.group(1) if mn else ''
        frase = FRASES_AUTOEVAL[(rotacion + i) % len(FRASES_AUTOEVAL)]
        frase = (frase.format(u=u_txt) if u_txt
                 else frase.format(u='').replace('la unidad ,', 'la unidad,')
                                        .replace('sobre la unidad ,', 'sobre la unidad,'))
        limpios.append(f'<p data-origen="frase-autoeval">{frase}</p>' + b2)
    return limpios


RE_MARK_TEMPORAL = re.compile(r'<mark data-ia="referencia-temporal"[^>]*>(.*?)</mark>', re.S)
RE_TEMPORAL = re.compile(r'\b([Ss]emanas?\s+\d+(?:\s*(?:,|y)\s*\d+)*|'
                         r'[Bb]imestres?\s+\d+|[Pp]rimer\s+bimestre|[Ss]egundo\s+bimestre)\b')

def _marcar_referencias_temporales(html):
    """Al unir semanas, frases como 'en la semana 7' o 'bimestre 1' pueden
    quedar obsoletas. Se marcan (solo en nodos de TEXTO, nunca dentro de
    atributos) para que el revisor decida si cambiarlas o dejarlas.
    Devuelve (html, detalles) donde detalles = [{'frase','contexto'}]."""
    partes = re.split(r'(<[^>]+>)', html)
    detalles = []
    for i, seg in enumerate(partes):
        if seg.startswith('<'):
            continue
        def _sub(m):
            # la oración completa donde aparece la mención: sirve de clave de
            # reemplazo (el revisor la edita en el tablero y se sustituye textual)
            ini = seg.rfind('.', 0, m.start()) + 1
            fin = seg.find('.', m.end())
            fin = len(seg) if fin == -1 else fin + 1
            detalles.append({'frase': m.group(1),
                             'contexto': seg[ini:fin].strip()})
            # sin estilo inline: el contenido se ve LIMPIO; las menciones se
            # listan en la alerta previa del previsualizador (el revisor decide)
            return ('<mark data-ia="referencia-temporal" title="Revisar: puede referirse '
                    'a la estructura vieja del curso">'
                    + m.group(1) + '</mark>')
        partes[i] = RE_TEMPORAL.sub(_sub, seg)
    return ''.join(partes), detalles


def _esc_attr(v):
    """Escapa una nota para guardarla en un atributo data-* (ya no se imprime
    como texto visible: el contenido de la pagina es solo lo academico)."""
    return (str(v or '').replace('&', '&amp;').replace('"', '&quot;')
            .replace('<', '&lt;').replace('>', '&gt;'))


CLASES_ESTRUCTURALES = ('focalizador', 'focuser', 'contenedor-figura', 'container-figure',
                        'tabla-general', 'table-general', 'tabla-diseno', 'table-design',
                        'contenedor-recursos', 'container-resources')


def _limpiar(html, sin_imagenes=False, conservar_clases=False):
    """Quita clases, ids y estilos del Canvas viejo y BALANCEA el fragmento
    (un </div> huérfano cerraría la pestaña de la plantilla donde se
    inserta). También elimina imágenes con rutas de exportación sin
    resolver ($IMS-CC-FILEBASE$).

    conservar_clases=True mantiene las clases ESTRUCTURALES (focalizador,
    tablas, figuras): son las que la plantilla nueva necesita para dar
    formato, y sin ellas el focalizador se pierde."""
    if conservar_clases:
        def _cls(m):
            vals = [c for c in m.group(1).split() if c in CLASES_ESTRUCTURALES]
            return f' class="{" ".join(vals)}"' if vals else ''
        html = re.sub(r'\sclass="([^"]*)"', _cls, html)
        html = re.sub(r'\s(?:id|style)="[^"]*"', '', html)
    else:
        html = re.sub(r'\s(?:class|id|style)="[^"]*"', '', html)
    # imagenes del token IMSCC del curso VIEJO (no resolubles): se quitan,
    # pero nunca las de la plantilla nueva (@@PLANTILLA@@)
    html = re.sub(r'<img(?![^>]*@@PLANTILLA@@)[^>]*\$IMS-CC-FILEBASE\$[^>]*>', '', html)
    if sin_imagenes:
        # iconos decorativos del tema viejo, no contenido
        html = re.sub(r'<img(?![^>]*@@PLANTILLA@@)[^>]*>', '', html)
    return _balancear(html).strip()


def _bloque_tras_heading(html, patron):
    """Contenido que sigue a un encabezado cuyo texto matchea `patron`:
    el div contenido-informacion siguiente si existe, o hasta el próximo
    encabezado."""
    for m in re.finditer(r'<(h[1-4])[^>]*>(.*?)</\1>', html, re.S | re.I):
        txt = re.sub('<[^>]+>', '', m.group(2)).replace('\xa0', ' ').strip()
        if re.search(patron, txt, re.I):
            j = html.find('contenido-informacion', m.end())
            if j != -1:
                return _div_balanceado(html, html.rfind('<div', 0, j))
            sig = re.search(r'<h[1-4][^>]*>', html[m.end():])
            fin = m.end() + sig.start() if sig else len(html)
            return html[m.end():fin].strip()
    return None



_FOTOS_SICA = {}   # caché usuario → url de la foto (evita repetir la llamada)

def _foto_docente_sica(usuario, log=None):
    """Foto del docente desde la API SICA de la UTPL. El tema global de Canvas
    debería resolverla vía JS, pero en la instancia test no corre, así que se
    resuelve aquí en el servidor y se deja la URL directa en el markup."""
    if not usuario:
        return None
    if usuario in _FOTOS_SICA:
        return _FOTOS_SICA[usuario]
    token = os.environ.get('SICA_TOKEN', 'rWMxU5jI6KLhT2k')
    url = None
    try:
        r = requests.get(f'https://sica.utpl.edu.ec/api/persons/{usuario}/',
                         params={'token': token}, timeout=10)
        r.raise_for_status()
        url = (r.json() or {}).get('image') or None
    except Exception as e:
        if log:
            log(f'  ⚠ SICA no respondió para {usuario}: {e} (queda el placeholder)')
    _FOTOS_SICA[usuario] = url
    return url


def _fuentes_inicio(canvas):
    """Extrae SOLO el contenido de las páginas viejas que alimentan el
    Inicio (nada de estilos ni menús del Canvas viejo)."""
    paginas = {}
    for m in canvas['modulos']:
        for it in m['items']:
            slug = (it.get('slug') or it.get('titulo') or '').lower()
            paginas[slug] = it.get('html') or ''
    def _pag(*claves):
        for slug, html in paginas.items():
            if any(k in slug for k in claves) and html:
                return html
        return ''

    inicio_v = _pag('inicio')
    info_gral = _pag('informacion-general', 'información general')
    perfil = _pag('perfil-del-profesor', 'perfil del profesor')
    tutorias = _pag('horario-de-tutorias', 'horario de tutor')

    f = {}
    # Visión general ← video de presentación de la página de inicio vieja
    mv = re.search(r'<iframe[^>]*></iframe>|<iframe[^>]*/>', inicio_v)
    if not mv:
        mv = re.search(r'<iframe.*?</iframe>', inicio_v, re.S)
    f['video'] = mv.group(0) if mv else None
    # Metodología de aprendizaje ← también de la página de inicio vieja
    met = _bloque_tras_heading(inicio_v, r'Metodolog\u00eda de aprendizaje|Metodología de aprendizaje')
    f['metodologia'] = _desenvolver_divs(_limpiar(met, sin_imagenes=True)) if met else None
    # Competencias y carga horaria ← Información general de la asignatura
    cg = _bloque_tras_heading(info_gral, r'Competencias gen')
    cp = _bloque_tras_heading(info_gral, r'Competencias del perfil')
    ch = _bloque_tras_heading(info_gral, r'N\u00famero de horas|Número de horas')
    # mismo caso que la metodologia: vienen envueltos en un <div> suelto
    f['competencias_genericas'] = _desenvolver_divs(_limpiar(cg, sin_imagenes=True)) if cg else None
    f['competencias_perfil'] = _desenvolver_divs(_limpiar(cp, sin_imagenes=True)) if cp else None
    if ch:
        ch = _limpiar(ch)
        ch = re.sub(r'<table', '<table class="table-design"', ch, count=1)
        ch = _normalizar_captions(ch)   # el titulo del caption va en cursiva
        ch = _centrar_horas(ch)         # solo la columna de horas va centrada
        f['carga_horaria'] = ch
    else:
        f['carga_horaria'] = None
    # Tu docente ← perfil del profesor + horario de tutorías (solo contenido)
    nom = re.search(r'Docente responsable:\s*(?:</strong>)?\s*</h\d>\s*<h\d[^>]*>(?:<strong>)?([^<]+)', perfil)
    if not nom:
        nom = re.search(r'Docente responsable[^<]*</[^>]+>\s*<[^>]+>([^<]+)', perfil)
    f['docente'] = nom.group(1).strip() if nom else None
    foto = re.search(r'<img[^>]*(?:perfil|docente)[^>]*>', perfil, re.I)
    f['foto'] = foto.group(0) if foto else None
    ig = _bloque_tras_heading(perfil, r'Informaci\u00f3n general|Información general')
    cu = _bloque_tras_heading(perfil, r'Curr\u00edculum|Currículum')
    # correo y teléfono se muestran bajo la foto (.profile-picture): se quitan
    # de la información general para que no aparezcan dos veces
    ig_limpio = _limpiar(ig) if ig else None
    if ig_limpio:
        ig_limpio = re.sub(
            r'<li[^>]*>(?:(?!</li>).)*?(?:Correo\s+electr[oó]nico|Tel[eé]fono)(?:(?!</li>).)*?</li>',
            '', ig_limpio, flags=re.S | re.I)
        ig_limpio = re.sub(
            r'<p[^>]*>(?:(?!</p>).)*?(?:Correo\s+electr[oó]nico|Tel[eé]fono)(?:(?!</p>).)*?</p>',
            '', ig_limpio, flags=re.S | re.I)
        ig_limpio = re.sub(r'<(ul|ol)[^>]*>\s*</\1>', '', ig_limpio)
        ig_limpio = _datos_docente_a_lista(ig_limpio)
    f['mentor_info'] = ig_limpio or None
    # usuario para la API SICA (foto del docente): nombre del correo
    mu = (re.search(r'id="usuarioDocente"[^>]*>\s*([^<\s]+)\s*<', perfil or '')
          or re.search(r'([A-Za-z0-9._-]+)(?:</span>)?@utpl\.edu\.ec', (ig or '') + (perfil or '')))
    f['usuario_sica'] = mu.group(1) if mu else None
    f['mentor_curriculum'] = _limpiar(cu) if cu else None
    # teléfono: va en .profile-picture en la plantilla nueva
    mt_tel = re.search(r'Tel[eé]fono\s*:?\s*(?:</strong>)?\s*([0-9][0-9\s().+-]{5,}(?:ext\.?\s*\d+)?)',
                       (perfil or '') + (ig or ''), re.I)
    f['telefono'] = mt_tel.group(1).strip() if mt_tel else None
    mt = re.search(r'<table.*?</table>', tutorias, re.S)
    if mt:
        t = _limpiar(mt.group(0))
        f['tutorias'] = re.sub(r'<table', '<table class="table-general"', t, count=1)
    else:
        f['tutorias'] = None
    return f


def construir_paginas(plan, canvas_viejo, mapa=None, base='', curso_destino=None, foro_url=None):
    """Plan revisado + curso viejo → página de INICIO + páginas de semana con
    la plantilla Rediseño 3, ya renumeradas. Sin mapa: previsualización."""
    secciones = _secciones_por_codigo(canvas_viejo)
    material, ctx_por_ra = _material_viejo(canvas_viejo)
    intros_viejas = _intros_unidad(canvas_viejo, sin_imagenes=False)   # tal cual = con sus imágenes
    _ras_todas = {r for dd in plan['semanas'].values()
                  for r in (dd.get('resultados_aprendizaje') or [])}
    intros_sem_viejas = _intros_semana_viejas(canvas_viejo, _ras_todas)
    adicionales = _paginas_adicionales(canvas_viejo)
    semanas_por_codigo = _semanas_de_codigo(canvas_viejo)
    ctx_ia = plan.get('contextualizaciones') or {}
    semana_ia = plan.get('semana_ia') or {}   # Agente A3: intro y cierre por semana
    unidades_ya_introducidas = set()   # una unidad puede repartirse en 2 semanas
    reemplazos = plan.get('reemplazos') or []   # ediciones de frases hechas en el tablero
    ras_txt, uni_txt, _ = _indices_canvas(canvas_viejo)
    txt_a_num = {(t or '').strip().lower(): n for n, t in ras_txt.items()}
    nav = list(plan['semanas'].keys())
    # temas conservados en TODO el plan (para saber dónde termina cada unidad)
    codigos_plan = {t['codigo'] for dd in plan['semanas'].values()
                    for t in (dd.get('temas') or [])
                    if t.get('accion') != 'del' and t.get('codigo')}
    ra_ultima_semana = {}   # RA-set → índice de la última semana donde apareció
    items_slug = _items_por_slug(canvas_viejo)
    slugs_embebidos = set()   # páginas del botón "Continuar" ya embebidas en un tema

    crudas = []
    ctx_grupos = {}   # conjunto de RA → primera semana que lo genera
    semanas_con_evaluacion = set()   # para la ruta de aprendizaje del Inicio
    for sem, d in plan['semanas'].items():
        temas_html, unidades_sem, semanas_origen, vistos = [], [], [], set()
        codigos_por_origen = {}   # semana vieja → códigos de tema que aportó
        for t in d['temas']:
            cod = t['codigo']
            if cod.count('.') > 1:
                continue   # subtema: su contenido ya viene dentro del tema padre
            if cod in vistos:
                continue   # continuaciones del mismo tema ya concatenadas
            vistos.add(cod)
            if t.get('html') and (t.get('origen') == 'nuevo' or t.get('accion') == 'mod'):
                # tema agregado por el docente, o tema existente cuyo
                # contenido editó el revisor: entra con numeración
                # PROVISIONAL en sus figuras/tablas; la re-enumeración
                # global del final le asigna los números definitivos y
                # corrige las referencias del resto del curso
                temas_html.append({'codigo': cod, 'titulo': t.get('titulo', ''),
                                   'html': _normalizar_tablas(_convertir_focalizadores(_balancear(t['html'])))})
                u = int(cod.split('.')[0])
                if u not in [x[0] for x in unidades_sem]:
                    unidades_sem.append((u, uni_txt.get(u, '')))
                continue
            if t['accion'] in ('keep', 'mod') and t['codigo'] in secciones:
                bruto = _embeber_boton_mas(secciones[t['codigo']], items_slug, slugs_embebidos)
                html = _normalizar_tablas(_convertir_focalizadores(bruto))
                if mapa is not None:
                    html = ca.reescribir_html(html, mapa, base, curso_destino)
                temas_html.append({'codigo': t['codigo'],
                                   'titulo': t.get('titulo', ''), 'html': html})
                u = int(t['codigo'].split('.')[0])
                if u not in [x[0] for x in unidades_sem]:
                    unidades_sem.append((u, uni_txt.get(u, '')))
                ns = _num_semana(t.get('semana_canvas'))
                if ns and ns not in semanas_origen:
                    semanas_origen.append(ns)
                if ns:
                    codigos_por_origen.setdefault(ns, []).append(t['codigo'])
                # incluir las semanas de CONTINUACION del tema (sus
                # actividades/autoevaluaciones tambien pertenecen aqui)
                for nc in semanas_por_codigo.get(cod, []):
                    if nc not in semanas_origen:
                        semanas_origen.append(nc)
                    codigos_por_origen.setdefault(nc, []).append(cod)
        huecos = set()
        for tk in d.get('tareas_ia', []):
            n = str(tk.get('tipo') or tk.get('t') or '').lower()
            if 'contextual' in n: huecos.add('contextualizacion')
            elif 'actividad' in n: huecos.add('actividad')
            elif 'autoeval' in n: huecos.add('autoevaluacion')
        ra = d.get('resultados_aprendizaje', [])
        ra_nums = [txt_a_num.get((r or '').strip().lower()) for r in ra]
        ra_nums = [n for n in ra_nums if n]
        ctx, fuentes, reusar_de, ctx_definitiva = None, None, None, False
        # mismo RA-set que la semana INMEDIATAMENTE anterior → contextualización
        # solo en la primera: aquí se ELIMINA el botón. Si las semanas con el
        # mismo RA están separadas, la contextualización va sí o sí.
        clave_ra = (tuple(sorted(ra_nums)) if ra_nums
                    else tuple(sorted((r or '').strip().lower() for r in ra)))
        idx_sem = nav.index(sem)
        sin_ctx = (clave_ra in ra_ultima_semana
                   and ra_ultima_semana[clave_ra] == idx_sem - 1)
        ra_ultima_semana[clave_ra] = idx_sem
        if sin_ctx:
            pass   # botón de Contextualización eliminado en esta semana
        elif sem in ctx_ia and ctx_ia[sem]:
            r = ctx_ia[sem]
            if isinstance(r, dict):
                # resultado del agente A1: incluye el veredicto
                ctx = r.get('contextualizacion') or ''
                esc = r.get('escenario')
                if r.get('reusada_de'):
                    nota = f"reutilizada de {r['reusada_de']} (mismos RA)"
                elif esc == 2:
                    nota = 'contextualización fuente evaluada — SÍ corresponde al RA; se mantiene tal cual'
                elif esc == 3:
                    nota = ('la fuente NO era contextualización del RA (bienvenida/introducción); '
                            'se generó una nueva')
                elif esc == 4:
                    nota = 'la semana une varios RA; se generó una contextualización nueva del conjunto'
                else:
                    nota = 'generada por el agente (no existía contextualización fuente)'
                # La nota del agente NO se imprime en la pagina: queda solo como
                # atributo data-* para el tablero/preview. En Canvas debe verse
                # unicamente el contenido academico.
                ctx = (f'<div data-ia="contextualizacion-agente" data-escenario="{esc or ""}"'
                       f' data-nota-ia="{_esc_attr(nota)}">{ctx}</div>')
                if r.get('texto_reubicado'):
                    # el texto retirado se conserva OCULTO (lo necesita el revisor
                    # en el tablero), pero sin ningun aviso visible en la pagina
                    ctx += ('<div data-ia="texto-reubicado" style="display:none">'
                            '<div class="ia-fuentes"><div class="ia-fuente">'
                            + r['texto_reubicado'].replace('<', '&lt;').replace('>', '&gt;')
                            + '</div></div></div>')
            else:
                ctx = r
            ctx_definitiva = True
        elif len(ra) == 1 and ra_nums:
            # la contextualización vieja NO se muestra como definitiva: el
            # agente debe dar veredicto (¿contextualiza el RA?) — si SÍ, se
            # conserva intacta (Escenario 2); si NO, genera nueva (Escenario 3)
            fuente_unica = ctx_por_ra.get(ra_nums[0])
            if fuente_unica:
                fuentes = [fuente_unica]
        elif len(ra) > 1:
            clave = tuple(sorted(ra_nums)) if ra_nums else tuple(sorted((r or '').strip().lower() for r in ra))
            if clave in ctx_grupos:
                # mismos RA que una semana anterior → la contextualización
                # generada es la MISMA: se reutiliza, no se genera otra
                reusar_de = ctx_grupos[clave]
            else:
                ctx_grupos[clave] = sem
                fuentes = [ctx_por_ra[n] for n in ra_nums if n in ctx_por_ra]
        # Ediciones del revisor en la Zona de práctica del tablero: sustituyen
        # el contenido traído del curso viejo. Un valor vacío significa que el
        # revisor eliminó ese bloque.
        _edit = (plan.get('practica_editada') or {}).get(sem) or {}
        _act_edit = _edit.get('actividades') or []
        _eval_edit = _edit.get('evaluadas') or []
        _auto_edit = _edit.get('autoevals') or []

        pares_act = []
        for _i, n in enumerate([x for x in semanas_origen if x in material]):
            _crudo = material[n]['actividades']
            if _i < len(_act_edit) and _act_edit[_i] is not None:
                _crudo = _act_edit[_i]          # editado por el revisor
            if not _crudo:
                continue                        # eliminado o inexistente
            pares_act.append((n, RE_INVITA_ACTIVIDAD.sub('', _convertir_focalizadores(
                _normalizar_tablas(_crudo)), count=1)))
        # título de rango SOLO cuando hay UNIÓN de semanas (2+ bloques): con
        # una sola semana fuente se omite, se da por entendido que las
        # actividades son de esa semana
        if len(pares_act) > 1:
            # Un mismo rango puede repetirse cuando dos semanas viejas aportan
            # los mismos temas (p. ej. las dos del 2.5): en ese caso el titulo
            # va UNA sola vez, no encabezando cada bloque.
            actividades, rotulos_vistos = [], set()
            for n, b in pares_act:
                rot = _rotulo_rango_actividades(codigos_por_origen.get(n))
                if rot and rot not in rotulos_vistos:
                    rotulos_vistos.add(rot)
                    actividades.append(_titulo_bloque_actividades(codigos_por_origen.get(n)) + b)
                else:
                    actividades.append(b)
            # si al final solo hubo UN rango distinto, el titulo no aporta
            # (no diferencia bloques): se quita y quedan las actividades solas
            if len(rotulos_vistos) < 2:
                actividades = [RE_H4_RANGO.sub('', a, count=1) for a in actividades]
        else:
            actividades = [b for _n, b in pares_act]
        # una sola frase de apertura (rotativa), sin las invitaciones repetidas
        # de cada bloque fuente
        actividades = _unificar_intros_actividades(actividades, rotacion=nav.index(sem))
        # numeración consecutiva y sin saltos a través de los bloques
        actividades = _renumerar_actividades(actividades)
        origen_autoeval = list(semanas_origen)
        unidades_presentes = {u for u, _ in unidades_sem}
        for t in d['temas']:
            cod = t.get('codigo') or ''
            if (t.get('accion') == 'del' and re.match(r'^\d+\.', cod)
                    and int(cod.split('.')[0]) in unidades_presentes):
                ns = _num_semana(t.get('semana_canvas'))
                if ns and ns not in origen_autoeval:
                    origen_autoeval.append(ns)   # solo autoevals, no actividades
                for nc in semanas_por_codigo.get(cod, []):
                    if nc not in origen_autoeval:
                        origen_autoeval.append(nc)
        autoevals = []
        for _i, n in enumerate([x for x in origen_autoeval if x in material]):
            _lista = material[n].get('autoevals') or []
            _ed = _auto_edit[_i] if _i < len(_auto_edit) else None
            for _j, _x in enumerate(_lista):
                if _ed and _j < len(_ed) and _ed[_j] is not None:
                    _x = _ed[_j]               # editada por el revisor
                if _x and _x.strip():          # vacia = eliminada
                    autoevals.append(_x)
        autoevals = _unificar_intros_autoeval(autoevals, rotacion=nav.index(sem))
        # Autoevaluación GENERADA por el agente A4: sustituye por completo al
        # recurso original (externo) de esa semana. Solo existe si el revisor
        # pidió regenerarla; si no toca nada, se conserva el recurso anterior.
        _ae_gen = (plan.get('autoevaluaciones_generadas') or {}).get(sem)
        if _ae_gen and (_ae_gen.get('html') or '').strip():
            autoevals = [_ae_gen['html']]
        # autoeval por unidad: solo si la unidad TERMINA en esta semana nueva.
        # una unidad termina aqui si su ultimo tema (en el curso viejo) esta
        # entre los temas que quedaron en la semana.
        codigos_sem = [t['codigo'] for t in temas_html]
        unidades_que_terminan = set()
        for u, _ in unidades_sem:
            # último tema de la unidad ENTRE LOS QUE QUEDARON EN EL PLAN
            # (si un tema fue eliminado, p. ej. el 4.4, no cuenta: la unidad
            # termina en su último tema conservado)
            tops_u = sorted([c for c in codigos_plan if c.count('.') == 1
                             and int(c.split('.')[0]) == u],
                            key=lambda c: [int(x) for x in c.split('.')])
            if tops_u and tops_u[-1] in codigos_sem:
                unidades_que_terminan.add(u)
        evaluadas = []
        for _i, n in enumerate([x for x in semanas_origen if x in material]):
            _crudo = material[n]['evaluadas']
            if _i < len(_eval_edit) and _eval_edit[_i] is not None:
                _crudo = _eval_edit[_i]
            if _crudo and _crudo.strip():
                evaluadas.append(_normalizar_tablas(_convertir_focalizadores(_crudo)))
        if evaluadas:
            # la ruta de aprendizaje del Inicio marca "Zona de evaluación"
            # en las semanas que traen actividad evaluada
            semanas_con_evaluacion.add(sem)
        if mapa is not None:
            actividades = [ca.reescribir_html(x, mapa, base, curso_destino) for x in actividades]
            evaluadas = [ca.reescribir_html(x, mapa, base, curso_destino) for x in evaluadas]
            autoevals = [ca.reescribir_html(x, mapa, base, curso_destino) for x in autoevals]
        # alertas de referencias temporales en el contenido migrado
        alertas = 0
        alertas_detalle = []
        for th in temas_html:
            th['html'] = _aplicar_reemplazos(th['html'], reemplazos)
            th['html'], k = _marcar_referencias_temporales(th['html'])
            u = int(th['codigo'].split('.')[0])
            for it in k:
                it['ubicacion'] = f"{sem} · Unidad {u} · tema {th['codigo']}"
            alertas += len(k); alertas_detalle.extend(k)
        actividades2 = []
        for x in actividades:
            x = _aplicar_reemplazos(x, reemplazos)
            x, k = _marcar_referencias_temporales(x)
            for it in k: it['ubicacion'] = f"{sem} · Actividades recomendadas"
            alertas += len(k); alertas_detalle.extend(k); actividades2.append(x)
        evaluadas2 = []
        for x in evaluadas:
            x = _aplicar_reemplazos(x, reemplazos)
            x, k = _marcar_referencias_temporales(x)
            for it in k: it['ubicacion'] = f"{sem} · Actividad evaluada"
            alertas += len(k); alertas_detalle.extend(k); evaluadas2.append(x)
        evaluadas = evaluadas2
        if ctx:
            ctx = _aplicar_reemplazos(ctx, reemplazos)
            ctx, k = _marcar_referencias_temporales(ctx)
            for it in k: it['ubicacion'] = f"{sem} · Contextualización"
            alertas += len(k); alertas_detalle.extend(k)
        extras = []
        for n in semanas_origen:
            for ad in adicionales.get(n, []):
                if ad['slug'] in slugs_embebidos:
                    continue   # ya quedó embebida dentro de su tema (botón Continuar)
                if ad['slug'] in [x['slug'] for x in extras]:
                    continue
                cuerpo = _normalizar_tablas(_convertir_focalizadores(ad['html']))
                if mapa is not None:
                    cuerpo = ca.reescribir_html(cuerpo, mapa, base, curso_destino)
                cuerpo = _aplicar_reemplazos(cuerpo, reemplazos)
                cuerpo, k = _marcar_referencias_temporales(cuerpo)
                for it in k:
                    it['ubicacion'] = f"{sem} · página adicional: {ad['titulo']}"
                alertas += len(k); alertas_detalle.extend(k)
                extras.append({'titulo': ad['titulo'], 'slug': ad['slug'],
                               'html': _balancear(cuerpo)})
        # solo las unidades que EMPIEZAN en esta semana llevan introduccion:
        # si la unidad viene continuada de una semana anterior no debe
        # quedar ni el texto repetido ni el hueco amarillo de la plantilla
        intros_sem = {u: intros_viejas.get(u, []) for u, _ in unidades_sem
                      if u not in unidades_ya_introducidas}
        # introducciones resueltas por el Agente A2 (si corrió): completa en
        # la semana donde la unidad empieza; continuación donde sigue
        intros_ia_sem = {}
        # La INTRODUCCION DE UNIDAD es SIEMPRE del docente y va TAL CUAL,
        # debajo del titulo "Unidad N." y antes del cuadro de subtemas. El
        # agente nunca la toca: lo que el A3 genera es la introduccion de la
        # SEMANA, que va ENCIMA del titulo de la unidad y solo una vez.
        for u, _tit in unidades_sem:
            fuentes_u = intros_viejas.get(u, [])
            if not fuentes_u:
                continue
            # La introduccion de UNIDAD va UNA sola vez: en la semana donde la
            # unidad EMPIEZA. Si la unidad viene arrastrada de una semana
            # anterior (continua aqui), NO se vuelve a colocar ningun parrafo
            # introductorio: el contenido sigue de corrido con sus temas.
            if u in unidades_ya_introducidas:
                continue
            partes = fuentes_u
            # focalizadores y tablas con las clases de la plantilla NUEVA
            cuerpo_iu = _normalizar_tablas(_convertir_focalizadores(''.join(partes)))
            intros_ia_sem[u] = (f'<div data-origen="introduccion-fuente" data-unidad="{u}">'
                                + cuerpo_iu + '</div>')
        # Agente A3 (Consolidación Semanal, prompt oficial): su introducción va
        # en el hueco de la primera unidad que EMPIEZA en la semana
        r3 = semana_ia.get(sem) or {}
        cierre_ia = None
        intro_semana = None
        if not (r3 and r3.get('aplica_ia')):
            # NO se unen semanas: la introduccion de la SEMANA se coloca TAL
            # CUAL la del curso viejo (la que iba encima del titulo de unidad)
            if len(semanas_origen) == 1:
                fuente_sem = intros_sem_viejas.get(semanas_origen[0])
                if fuente_sem:
                    intro_semana = ('<div data-origen="introduccion-semana-fuente" '
                                    f'data-semana-origen="{semanas_origen[0]}">'
                                    + _normalizar_tablas(_convertir_focalizadores(fuente_sem))
                                    + '</div>')
        if r3 and r3.get('aplica_ia'):
            # "Aplicar IA por union de semanas": introduccion de la SEMANA
            # (va arriba, antes de la primera unidad) y cierre generado
            if r3.get('cierre'):
                cierre_ia = r3['cierre']
            if r3.get('introduccion'):
                nota3 = ('introduccion de la semana generada uniendo las frases de inicio de '
                         'S' + ', S'.join(str(n) for n in (r3.get('semanas_origen') or []))
                         if r3.get('escenario') == 1 else
                         'introduccion de la semana generada desde el indice de temas')
                if r3.get('avisos'):
                    nota3 += ' · ⚠ ' + '; '.join(r3['avisos'])
                intro_semana = (f'<div data-ia="semana-agente"'
                                f' data-nota-ia="{_esc_attr(nota3)}">'
                                + r3['introduccion'] + '</div>')

        # las introducciones colocadas (tal cual o del agente) también pasan por
        # los reemplazos del revisor y la detección de referencias temporales
        # (p. ej. "durante las semanas 12 y 13" del metacurso viejo)
        for u in list(intros_ia_sem):
            v = _aplicar_reemplazos(intros_ia_sem[u], reemplazos)
            v, k = _marcar_referencias_temporales(v)
            for it in k:
                it['ubicacion'] = f"{sem} · Unidad {u} · introducción"
            alertas += len(k)
            alertas_detalle.extend(k)
            intros_ia_sem[u] = v
        # la introduccion de la SEMANA (tal cual del curso viejo o generada por
        # el A3) tambien debe escanearse: es justo donde viven las menciones
        # "durante las semanas 12 y 13" del metacurso antiguo, y quedaba fuera
        # del reporte porque solo se recorrian las intros de UNIDAD
        if intro_semana:
            intro_semana = _aplicar_reemplazos(intro_semana, reemplazos)
            intro_semana, k = _marcar_referencias_temporales(intro_semana)
            for it in k:
                it['ubicacion'] = f"{sem} · introducción de la semana"
            alertas += len(k)
            alertas_detalle.extend(k)
        if cierre_ia:
            cierre_ia = _aplicar_reemplazos(cierre_ia, reemplazos)
            cierre_ia, k = _marcar_referencias_temporales(cierre_ia)
            for it in k:
                it['ubicacion'] = f"{sem} · cierre de la semana"
            alertas += len(k)
            alertas_detalle.extend(k)
        # unidades que EMPIEZAN en esta semana (antes de marcarlas): solo
        # esas llevan el titulo "Unidad N." y su introduccion en el cuerpo
        unidades_inician = [u for u, _ in unidades_sem
                            if u not in unidades_ya_introducidas]
        for u, _tit in unidades_sem:
            unidades_ya_introducidas.add(u)
        body = render_semana(sem, temas_html, ra, huecos,
                             unidades=unidades_sem, unidades_inician=unidades_inician,
                             contextualizacion=ctx,
                             sin_contextualizacion=sin_ctx,
                             contexto_fuentes=fuentes, contexto_reusar_de=reusar_de,
                             actividades=actividades2 or None, evaluadas=evaluadas or None,
                             intros_unidad=intros_sem, intros_ia=intros_ia_sem,
                             autoevaluaciones=autoevals or None,
                             rango_temas=_rango_temas(temas_html),
                             mostrar_autoeval=bool(unidades_que_terminan),
                             cierre=cierre_ia, intro_semana=intro_semana,
                             extras=extras or None, ctx_definitiva=ctx_definitiva,
                             nav_semanas=nav, base_url=base if curso_destino else '',
                             curso_id=curso_destino)
        crudas.append({'semana': sem, 'body': body, 'huecos': sorted(huecos),
                       'temas': len(temas_html), 'alertas_temporales': alertas,
                       'alertas_detalle': alertas_detalle})

    fuentes_inicio = _fuentes_inicio(canvas_viejo)
    # ediciones del revisor sobre la página de Inicio (desde el tablero)
    for k, v in (plan.get('inicio') or {}).items():
        if v is not None:
            fuentes_inicio[k] = _balancear(v)
    # foto del docente desde SICA (resuelta en servidor; si falla, placeholder)
    if not fuentes_inicio.get('foto_url'):
        fuentes_inicio['foto_url'] = _foto_docente_sica(fuentes_inicio.get('usuario_sica'))
    # remapear-inicio: foto de la docente, video y demas archivos del
    # Inicio hacia el curso destino
    if mapa is not None:
        for k, v in fuentes_inicio.items():
            if isinstance(v, str) and v:
                fuentes_inicio[k] = ca.reescribir_html(v, mapa, base, curso_destino)
    inicio = plantilla.render_inicio(_nombre_asignatura(canvas_viejo, plan),
                                     nav, fuentes_inicio,
                                     base_url=base if curso_destino else '',
                                     curso_id=curso_destino, foro_url=foro_url,
                                     semanas_evaluacion=semanas_con_evaluacion)
    _av = getattr(plantilla.render_inicio, 'aviso_ruta', None)
    if _av:
        print(f"⚠ {_av}")
    crudas.insert(0, {'semana': 'Inicio', 'body': inicio, 'huecos': [], 'temas': 0})

    cuerpos, reporte = renumerar.renumerar_curso([p['body'] for p in crudas])
    for p, b in zip(crudas, cuerpos):
        p['body'] = b
    return crudas, reporte


# ---------------------------------------------------------------------------
# Generación
# ---------------------------------------------------------------------------
def _crear_curso(base, token, nombre, cuenta_id):
    r = _peticion('POST', f'{base}/api/v1/accounts/{cuenta_id}/courses',
                  headers={'Authorization': f'Bearer {token}'},
                  data={'course[name]': nombre, 'course[course_code]': nombre[:20]})
    return r.json()['id']


def _crear_modulo(base, token, curso_id, nombre, posicion):
    r = _peticion('POST', f'{base}/api/v1/courses/{curso_id}/modules',
                  headers={'Authorization': f'Bearer {token}'},
                  data={'module[name]': nombre, 'module[position]': posicion})
    return r.json()['id']


def _item_modulo(base, token, curso_id, modulo_id, page_url, titulo, posicion, publicar):
    r = requests.post(f'{base}/api/v1/courses/{curso_id}/modules/{modulo_id}/items',
                      headers={'Authorization': f'Bearer {token}'},
                      data={'module_item[type]': 'Page', 'module_item[page_url]': page_url,
                            'module_item[title]': titulo, 'module_item[position]': posicion,
                            'module_item[published]': str(publicar).lower()}, timeout=60)
    r.raise_for_status()
    return r.json()['id']


def _publicar_modulo(base, token, curso_id, modulo_id):
    _peticion('PUT', f'{base}/api/v1/courses/{curso_id}/modules/{modulo_id}',
              headers={'Authorization': f'Bearer {token}'},
              data={'module[published]': 'true'})


def _paginas_auxiliares(canvas, mapa, base, curso_destino):
    """Paginas auxiliares construidas con las PLANTILLAS OFICIALES:
    · Encuentros en linea → plantilla oficial (contenido viejo si existe).
    · Fuentes y recursos → pestañas Bibliografia / Glosario / Creditos,
      llenadas desde el curso viejo (referencias y creditos) si existen."""
    paginas_viejas = {}
    for m in canvas['modulos']:
        for it in m['items']:
            slug = (it.get('slug') or it.get('titulo') or '').lower()
            paginas_viejas[slug] = it.get('html') or ''

    def _busca(*claves):
        for slug, html in paginas_viejas.items():
            if any(k in slug for k in claves) and html:
                return html
        return None

    def _prep(html):
        if not html:
            return None
        out = _limpiar(html)
        if mapa is not None:
            out = ca.reescribir_html(out, mapa, base, curso_destino)
        return out

    def _sin_icono_inicial(html):
        """Quita el icono decorativo con que abrian las paginas del curso
        viejo (bibliografia, glosario, creditos): en la plantilla nueva la
        pestaña ya trae su encabezado, asi que ese icono sobra.

        Se hace con BeautifulSoup porque el markup real trae la imagen dentro
        de un <p> con un &nbsp; detras: con regex se borraba la <img> pero
        quedaba un <p>&nbsp;</p> vacio ocupando espacio.
        """
        if not html or '<img' not in html:
            return html
        try:
            from bs4 import BeautifulSoup
        except Exception:
            return html
        sopa = BeautifulSoup(html, 'html.parser')
        for img in sopa.find_all('img'):
            deco = (str(img.get('data-decorative', '')).lower() == 'true'
                    or img.get('role') == 'presentation')
            if not deco:
                break        # la primera imagen NO es decorativa: no se toca
            padre = img.parent
            img.decompose()
            # si el <p> contenedor queda sin texto real (solo &nbsp;), se quita
            if padre is not None and padre.name == 'p':
                resto = padre.get_text().replace('\xa0', ' ').strip()
                if not resto and not padre.find(['img', 'iframe', 'a', 'table']):
                    padre.decompose()
            break            # solo el icono INICIAL
        return str(sopa).strip()

    enc = _prep(_busca('encuentros-en-linea', 'encuentros en l'))
    bib = _sin_icono_inicial(_prep(_busca('referencias-bibliograficas', 'referencias bibl')))
    glo = _sin_icono_inicial(_prep(_busca('glosario')))
    cre = _sin_icono_inicial(_prep(_busca('creditos', 'créditos')))

    aux = [
        {'titulo': 'Encuentros en línea', 'modulo': 'Preliminares',
         'body': plantilla.render_encuentros(enc, base_url=base if curso_destino else '',
                                             curso_id=curso_destino)},
        {'titulo': 'Fuentes y recursos', 'modulo': 'Apartados finales',
         'body': plantilla.render_fuentes(bib, glo, cre,
                                          base_url=base if curso_destino else '',
                                          curso_id=curso_destino)},
    ]
    return aux



def _slugificar(txt):
    """Titulo -> slug comparable (sin tildes, minusculas, guiones)."""
    import unicodedata
    t = unicodedata.normalize('NFD', txt or '')
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')


def _paginas_sueltas(canvas, mapa, base, curso_destino):
    """Páginas del curso antiguo que NO van en módulos pero deben existir en
    el curso nuevo (anexos, autoevaluaciones, créditos, etc.): se crean tal
    cual con los assets remapeados, para que los enlaces internos sigan
    funcionando. Se excluyen las semanas, el inicio viejo (reemplazado por
    el nuevo) y las que ya se convirtieron en páginas auxiliares."""
    excluir = re.compile(r'^(semana[\s-]|inicio)', re.I)
    # su contenido ya se volco en la pagina de Inicio nueva (Vision General,
    # Planificacion, Tu docente) o en su propia pagina auxiliar: no se duplican
    ya_convertidas = ('referencias-bibliograficas', 'fuentes-y-recursos', 'encuentros-en-linea',
                      'creditos', 'glosario',
                      'perfil-del-profesor', 'perfil-profesor', 'perfil-docente',
                      'horario-de-tutorias', 'horario-tutorias', 'tutorias',
                      'informacion-general-de-la-asignatura', 'informacion-general',
                      'presentacion-de-la-asignatura', 'metodologia')
    out = []
    # se recorren las paginas de modulos Y las sueltas: hay paginas que no
    # pertenecen a ningun modulo (p. ej. "Autoevaluaciones", que no ven los
    # estudiantes pero alimenta la generacion de la guia) y deben crearse igual
    _todas = [it for m in canvas['modulos'] for it in m['items']]
    _todas += list(canvas.get('paginas_sueltas') or [])
    _vistos = set()
    for it in _todas:
            titulo = (it.get('titulo') or '').strip()
            slug = (it.get('slug') or titulo).lower()
            if slug in _vistos:
                continue
            _vistos.add(slug)
            if not titulo or not it.get('html'):
                continue
            if excluir.match(slug) or excluir.match(titulo) or excluir.match(_slugificar(titulo)):
                continue
            tit_norm = _slugificar(titulo)
            if any(k in slug for k in ya_convertidas) or any(k in tit_norm for k in ya_convertidas):
                continue
            body = it['html']
            if mapa is not None:
                body = ca.reescribir_html(body, mapa, base, curso_destino)
            out.append({'titulo': titulo, 'body': body})
    return out



def _peticion(metodo, url, *, reintentos=3, espera=5, log=None, **kw):
    """Llamada a la API de Canvas con REINTENTOS: la instancia puede tardar o
    cortar la conexión con páginas grandes (Read timed out). Reintenta ante
    timeouts, errores de conexión y 5xx, con espera progresiva."""
    kw.setdefault('timeout', 180)
    ultimo = None
    for intento in range(1, reintentos + 1):
        try:
            r = requests.request(metodo, url, **kw)
            if r.status_code >= 500 and intento < reintentos:
                ultimo = requests.HTTPError(f'{r.status_code} del servidor')
            else:
                r.raise_for_status()
                return r
        except (requests.Timeout, requests.ConnectionError) as e:
            ultimo = e
        except requests.HTTPError as e:
            if getattr(e.response, 'status_code', 0) < 500:
                raise            # 4xx: es un error real, no de red
            ultimo = e
        if intento < reintentos:
            pausa = espera * intento
            if log:
                log(f"    ↻ Canvas no respondió ({type(ultimo).__name__}); "
                    f"reintento {intento}/{reintentos - 1} en {pausa}s…")
            time.sleep(pausa)
    raise ultimo


def _crear_pagina(base, token, curso_id, titulo, body, publicar=False, log=None):
    r = _peticion('POST', f'{base}/api/v1/courses/{curso_id}/pages',
                  headers={'Authorization': f'Bearer {token}'},
                  data={'wiki_page[title]': titulo, 'wiki_page[body]': body,
                        'wiki_page[published]': str(publicar).lower()},
                  timeout=180, log=log)
    return r.json().get('url')


def generar(base, token, plan, canvas_viejo, cuenta_id,
            curso_destino=None, publicar=True,
            base_destino=None, token_destino=None, log=print):
    """
    plan: dict exportado por la interfaz de revisión (semanas, temas, tareas_ia).
    canvas_viejo: dict del curso extraído (para HTML y assets).
    curso_destino: si None, crea un curso nuevo en cuenta_id.
    Devuelve {curso_destino, paginas, mapa_assets}.
    """
    base = base.rstrip('/')
    base_destino = (base_destino or base).rstrip('/')
    token_destino = token_destino or token
    if base_destino != base:
        log(f"🌐 Instancias separadas: origen {base} → destino {base_destino}")
    curso_origen = canvas_viejo['curso_id']
    if curso_destino is None:
        curso_destino = _crear_curso(base, token, plan['curso'] + ' (extraordinario)', cuenta_id)
        log(f"🆕 Curso destino creado: {curso_destino}")

    secciones = _secciones_por_codigo(canvas_viejo)

    # 1) reunir los file_ids de TODO el curso viejo (temas, actividades,
    #    inicio y páginas sueltas usan imágenes/archivos)
    file_ids = set()
    for m in canvas_viejo['modulos']:
        for it in m['items']:
            if it.get('html'):
                file_ids |= set(ca.inventariar(it['html'])['file_ids'])
    # incluir los archivos de las páginas sueltas embebidas (botón "Continuar"),
    # que no están en los módulos y por eso no se copiaban: sus imágenes
    # quedaban apuntando al curso viejo
    for pg in (canvas_viejo.get('paginas_enlazadas') or {}).values():
        file_ids |= set(ca.inventariar(pg.get('html') or '')['file_ids'])
    log(f"🖼  Copiando {len(file_ids)} archivos del curso {curso_origen} (origen) "
        f"al curso {curso_destino} (destino)…")
    try:
        mapa = ca.copiar_archivos(
            base, token, curso_origen, curso_destino, sorted(file_ids),
            base_destino=base_destino, token_destino=token_destino,
            progreso=lambda i, t: (i % 5 == 0 or i == t) and log(f'    · {i}/{t} archivos'))
    except Exception as e:
        mapa = {fid: None for fid in file_ids}
        import traceback
        log(f"    ❌ FALLÓ la copia de archivos: {type(e).__name__}: {e}")
        log(f"       {traceback.format_exc().splitlines()[-3].strip()}")
        log("       Las imágenes quedarán apuntando al curso VIEJO "
            "(marcadas data-migracion=\"pendiente\"). Revise el token y los permisos "
            "sobre Archivos del curso destino.")
    ok = sum(1 for v in mapa.values() if v)
    log(f"    {ok}/{len(mapa)} archivos copiados" +
        ("" if ok == len(mapa) else f" — {len(mapa)-ok} pendientes (revisar permisos del token sobre Archivos del curso destino)"))

    # 2) construir páginas con la plantilla nueva + renumeración global
    # el foro de asesoria del curso DESTINO (aqui si hay credenciales)
    foro_url = _url_foro_asesoria(base_destino, token_destino, curso_destino, log=log)
    paginas_html, reporte = construir_paginas(plan, canvas_viejo, mapa=mapa,
                                              base=base_destino, curso_destino=curso_destino,
                                              foro_url=foro_url)
    # 3) recursos de la PLANTILLA OFICIAL (iconos, focalizadores, encabezados)
    dir_recursos = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plantilla_recursos')
    rutas_plantilla = {}
    if os.path.isdir(dir_recursos):
        log("🎨 Subiendo recursos de la plantilla oficial…")
        rutas_plantilla = ca.subir_recursos_plantilla(base_destino, token_destino,
                                                      curso_destino, dir_recursos)
        ok_r = sum(1 for v in rutas_plantilla.values() if v)
        log(f"    {ok_r}/{len(rutas_plantilla)} recursos de plantilla subidos")
        # los iconos de MARCADOR son nuevos: avisar si la carpeta no esta copiada
        _marc = [k for k in rutas_plantilla if 'Marcadores' in k]
        if not _marc:
            log('⚠ No se encontraron iconos en plantilla_recursos/Plantilla/'
                'Íconos/Marcadores/ — los marcadores (Resultado de aprendizaje, '
                'Contextualización, Zona de práctica…) se veran rotos')
        if ok_r < len(rutas_plantilla):
            faltan = [k for k, v in rutas_plantilla.items() if not v]
            log(f"    ⚠ no se subieron: {', '.join(faltan[:8])}"
                + (f" (+{len(faltan)-8} mas)" if len(faltan) > 8 else ""))
    else:
        log(f"⚠ No existe la carpeta {dir_recursos}: los focalizadores e iconos "
            "de la plantilla se veran rotos en Canvas")


    paginas, slugs = [], {}
    for pg in paginas_html:
        # las marcas de referencias temporales son SOLO de revision:
        # el revisor ya fue alertado antes de subir; el curso final va limpio
        pg['body'] = RE_MARK_TEMPORAL.sub(r'\1', pg['body'])
        pg['body'] = ca.reescribir_tokens_plantilla(pg['body'], rutas_plantilla,
                                                    base_destino, curso_destino)
        slug = _crear_pagina(base_destino, token_destino, curso_destino, pg['semana'], pg['body'], publicar, log=log)
        slugs[pg['semana']] = slug
        paginas.append({'semana': pg['semana'], 'slug': slug,
                        'temas': pg['temas'], 'huecos': pg['huecos']})
        log(f"  ✓ {pg['semana']}: {pg['temas']} temas, huecos IA: {pg['huecos']}")
    _sr = getattr(ca.reescribir_tokens_plantilla, 'sin_resolver', None)
    if _sr:
        log(f"⚠ {len(_sr)} recurso(s) de plantilla sin resolver (se veran rotos): "
            + ', '.join(sorted(_sr)[:8]))
    log(f"🔢 Renumeración: {len(reporte['figuras'])} figuras y {len(reporte['tablas'])} tablas "
        f"cambiaron de número; {len(reporte['referencias_rotas'])} referencias rotas marcadas")

    # 3b) páginas auxiliares que van en módulos
    aux = _paginas_auxiliares(canvas_viejo, mapa, base_destino, curso_destino)
    for a in aux:
        a['body'] = ca.reescribir_tokens_plantilla(a['body'], rutas_plantilla,
                                                   base_destino, curso_destino)
        a['slug'] = _crear_pagina(base_destino, token_destino, curso_destino, a['titulo'], a['body'], publicar, log=log)
        log(f"  ✓ página auxiliar: {a['titulo']}")

    # 4) estructura de MÓDULOS: Preliminares / Contenido / Apartados finales
    modulos = []
    m_pre = _crear_modulo(base_destino, token_destino, curso_destino, 'Preliminares', 1)
    pos = 1
    if 'Inicio' in slugs:
        _item_modulo(base_destino, token_destino, curso_destino, m_pre, slugs['Inicio'], 'Inicio', pos, publicar); pos += 1
    for a in aux:
        if a['modulo'] == 'Preliminares':
            _item_modulo(base_destino, token_destino, curso_destino, m_pre, a['slug'], a['titulo'], pos, publicar); pos += 1
    modulos.append({'nombre': 'Preliminares', 'id': m_pre})

    m_con = _crear_modulo(base_destino, token_destino, curso_destino, 'Contenido', 2)
    pos = 1
    for pg in paginas_html:
        if pg['semana'] != 'Inicio':
            _item_modulo(base_destino, token_destino, curso_destino, m_con, slugs[pg['semana']], pg['semana'], pos, publicar); pos += 1
    modulos.append({'nombre': 'Contenido', 'id': m_con})

    m_fin = _crear_modulo(base_destino, token_destino, curso_destino, 'Apartados finales', 3)
    pos = 1
    for a in aux:
        if a['modulo'] == 'Apartados finales':
            _item_modulo(base_destino, token_destino, curso_destino, m_fin, a['slug'], a['titulo'], pos, publicar); pos += 1
    modulos.append({'nombre': 'Apartados finales', 'id': m_fin})

    if publicar:
        for mo in modulos:
            _publicar_modulo(base_destino, token_destino, curso_destino, mo['id'])
        log("✅ Páginas y módulos PUBLICADOS")
    else:
        log("⚠ Curso creado SIN publicar (modo borrador)")
    fallos = getattr(ca, '_fallos', {})
    if fallos:
        log(f"⚠ {len(fallos)} archivo(s) NO se pudieron copiar; sus imagenes quedan "
            f"apuntando al curso viejo:")
        for fid, motivo in list(fallos.items())[:10]:
            log(f"     · file {fid}: {motivo}")
    pend = getattr(ca.reescribir_html, 'pendientes', set())
    if pend:
        log(f"⚠ {len(pend)} imagen(es) siguen apuntando al curso viejo (no se pudieron "
            f"copiar): file ids {', '.join(sorted(pend)[:8])}"
            + ("…" if len(pend) > 8 else ""))
    log(f"📦 Módulos creados: Preliminares / Contenido / Apartados finales")

    # 5) Inicio como PÁGINA PRINCIPAL del curso (Canvas exige publicarla)
    if 'Inicio' in slugs:
        try:
            h = {'Authorization': f'Bearer {token_destino}'}
            requests.put(f'{base_destino}/api/v1/courses/{curso_destino}/pages/{slugs["Inicio"]}',
                         headers=h, data={'wiki_page[front_page]': 'true',
                                          'wiki_page[published]': 'true'}, timeout=60).raise_for_status()
            requests.put(f'{base_destino}/api/v1/courses/{curso_destino}',
                         headers=h, data={'course[default_view]': 'wiki'}, timeout=60).raise_for_status()
            log("🏠 'Inicio' fijada como página principal del curso (publicada, requerido por Canvas)")
        except Exception as e:
            log(f"    ⚠ No se pudo fijar 'Inicio' como página principal: {e}")

    # 6) páginas del curso antiguo que NO van en módulos (se crean igual)
    sueltas = _paginas_sueltas(canvas_viejo, mapa, base_destino, curso_destino)
    # ediciones del revisor sobre las EVALUACIONES del curso antiguo:
    # sustituyen el contenido; una cadena vacia significa que se eliminan
    _ev_edit = plan.get('evaluaciones_editadas') or {}
    if _ev_edit:
        _antes = len(sueltas)
        _filtradas = []
        for s in sueltas:
            _k = s.get('slug') or s.get('titulo') or ''
            if _k in _ev_edit:
                _nuevo = _ev_edit[_k]
                if not (_nuevo or '').strip():
                    log(f"  – evaluación eliminada por el revisor: {s['titulo']}")
                    continue
                s['body'] = _nuevo
                log(f"  ✎ evaluación editada por el revisor: {s['titulo']}")
            _filtradas.append(s)
        sueltas = _filtradas
        if _antes != len(sueltas):
            log(f"    ({_antes - len(sueltas)} página(s) no se crearán)")
    for s in sueltas:
        s['slug'] = _crear_pagina(base_destino, token_destino, curso_destino, s['titulo'], s['body'], publicar)
        log(f"  ✓ página suelta (sin módulo): {s['titulo']}")

    return {'curso_destino': curso_destino, 'paginas': paginas, 'mapa_assets': mapa,
            'renumeracion': reporte, 'modulos': modulos,
            'auxiliares': [{'titulo': a['titulo'], 'slug': a['slug'], 'modulo': a['modulo']} for a in aux],
            'sueltas': [{'titulo': s['titulo'], 'slug': s['slug']} for s in sueltas]}