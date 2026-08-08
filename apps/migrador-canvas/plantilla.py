#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plantilla.py — v3 "tal cual": las páginas se construyen por CIRUGÍA sobre
los archivos OFICIALES del export de la plantilla Rediseño 3
(plantilla_oficial/semana.html, inicio.html, fuentes-y-recursos.html,
encuentros-en-linea.html). Solo se rellenan los slots (por id); todo lo
demás — íconos $IMS-CC-FILEBASE$, atributos, estructura — queda byte a
byte como el export. Los tokens $IMS-CC-FILEBASE$ se resuelven después:
en la subida real, contra los recursos subidos al curso destino; en la
previsualización, contra /plantilla_recursos/ servido localmente.

Caso no cubierto por la plantilla oficial (varias unidades en una misma
semana): se mantiene el layout ya acordado — encabezado de unidad +
introducción IA + cuadro de temas por cada unidad, separados con <hr> —
construido con los mismos fragmentos oficiales.
"""
import os
import re
from html import escape

DIR_OFICIAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plantilla_oficial')
_CACHE = {}



# Textos que cambiaron en la plantilla oficial: si el archivo en disco aun
# tiene el viejo, es que no se copio la version nueva.
_PLANTILLA_OBSOLETA = {
    'inicio.html': [('Tu Mentor', 'Tu docente')],
}
_YA_AVISADO = set()


def _avisar_plantilla_vieja(ruta, nombre):
    """Avisa por consola si la plantilla oficial en disco esta desactualizada."""
    if nombre in _YA_AVISADO or nombre not in _PLANTILLA_OBSOLETA:
        return
    try:
        s = open(ruta, encoding='utf-8').read()
    except OSError:
        return
    for viejo, nuevo in _PLANTILLA_OBSOLETA[nombre]:
        if viejo in s:
            print(f'\n  *** ATENCION: plantilla_oficial/{nombre} esta DESACTUALIZADA: '
                  f'contiene "{viejo}" y deberia decir "{nuevo}".\n'
                  f'      Copie la version nueva sobre {ruta}\n')
            _YA_AVISADO.add(nombre)



def _cuerpo(nombre):
    """Contenido del <body> (el div.ed-container) del archivo oficial.

    La cache se invalida sola cuando el archivo cambia en disco (mtime), asi
    al actualizar la plantilla oficial no hace falta reiniciar el servidor."""
    ruta = os.path.join(DIR_OFICIAL, nombre)
    _avisar_plantilla_vieja(ruta, nombre)
    try:
        sello = os.path.getmtime(ruta)
    except OSError:
        sello = 0
    if _CACHE.get(nombre, (None, None))[0] != sello:
        raw = open(ruta, encoding='utf-8').read()
        m = re.search(r'<body>(.*)</body>', raw, re.S)
        _CACHE[nombre] = (sello, _con_footer((m.group(1) if m else raw).strip()))
        _avisar_plantilla_vieja(nombre, raw)
    return _CACHE[nombre][1]


# Footer institucional: barra azul de marca con el logo UTPL a la derecha.
# Se inyecta en TODAS las paginas (inicio, semanas, encuentros, fuentes...)
# para no tener que editarlo en cada archivo de plantilla_oficial/.
# El estilo vive en style.css / style_app.css (.ed-container .ed-footer).
FOOTER_HTML = '<footer class="ed-footer"><span>UTPL</span></footer>'


def _con_footer(cuerpo):
    """Anade el footer como ULTIMO elemento DENTRO de .ed-container.

    Debe ir dentro del contenedor porque el selector del CSS es
    '.ed-container .ed-footer'. Si el cuerpo ya trae un footer no se
    duplica, y si no se encuentra el cierre del contenedor se anade al
    final (mejor eso que perderlo)."""
    if 'ed-footer' in cuerpo:
        return cuerpo
    cierre = cuerpo.rfind('</div>')
    if cierre == -1:
        return cuerpo + FOOTER_HTML
    return cuerpo[:cierre] + FOOTER_HTML + cuerpo[cierre:]


def _avisar_plantilla_vieja(nombre, raw):
    """Avisa por consola si el archivo de plantilla_oficial/ es una version
    anterior (p. ej. inicio.html con 'Tu Mentor' en vez de 'Tu docente')."""
    marcas = {'inicio.html': [('Tu Mentor', 'Tu docente')]}
    for viejo, nuevo in marcas.get(nombre, []):
        if viejo in raw:
            print(f"[PLANTILLA DESACTUALIZADA] plantilla_oficial/{nombre} contiene "
                  f"'{viejo}'; deberia decir '{nuevo}'. Copie la version nueva del "
                  f"archivo a plantilla_oficial/.", flush=True)


def _rango_elemento(html, id_):
    """(inicio_tag, inicio_inner, fin_inner, fin_tag) del elemento con id."""
    m = re.search(r'<(\w+)([^>]*\bid="%s"[^>]*)>' % re.escape(id_), html)
    if not m:
        return None
    tag = m.group(1)
    ini_inner = m.end()
    nivel, k = 1, ini_inner
    c = -1
    while nivel:
        a = html.find(f'<{tag}', k)
        c = html.find(f'</{tag}>', k)
        if c == -1:
            return None
        if a != -1 and a < c:
            nivel += 1
            k = a + len(tag) + 1
        else:
            nivel -= 1
            k = c + len(tag) + 3
    return m.start(), ini_inner, c, k


def _set_inner(html, id_, inner):
    r = _rango_elemento(html, id_)
    if not r:
        return html
    return html[:r[1]] + inner + html[r[2]:]


# ---------------------------------------------------------------------------
# Iconos de MARCADOR de la plantilla oficial (carpeta
# plantilla_recursos/Plantilla/Íconos/Marcadores/). Se referencian con el
# marcador @@PLANTILLA@@, que canvas_assets sustituye por la URL real del
# archivo ya subido al curso; en el previsualizador lo resuelve tokens_a_local.
# La ruta va URL-encoded porque "Íconos" lleva tilde (Í → %C3%8D).
# ---------------------------------------------------------------------------
DIR_MARCADORES = '@@PLANTILLA@@/Plantilla/%C3%8Dconos/Marcadores'

ICONOS_MARCADOR = {
    'resultado_aprendizaje':  'ic_resultado_aprendizaje_m_metacurso_utpl_julio_2026.svg',
    'contextualizacion':      'ic_contextualizacion_m_metacurso_utpl_julio_2026.svg',
    'zona_practica':          'ic_zona_practica_m_metacurso_utpl_julio_2026.svg',
    'propositos_aprendizaje': 'ic_propositos_aprendizaje_m_metacurso_utpl_julio_2026.svg',
    'metodologia':            'ic_metodologia_aprendizaje_m_metacurso_utpl_julio_2026.svg',
    'carga_horaria':          'ic_carga_horaria_m_metacurso_utpl_julio_2026.svg',
    'encuentros_en_linea':    'ic_encuentros_en_linea_m_metacurso_utpl_julio_2026.svg',
    'calendario_actividades': 'ic_calendario_actividades_m_metacurso_utpl_julio_2026.svg',
    'fuentes_recursos':       'ic_fuentes_recursos_m_metacurso_utpl_julio_2026.svg',
}


def icono_marcador(clave, alt='', ancho=30):
    """<img> del icono de marcador correspondiente. Devuelve '' si no existe."""
    nombre = ICONOS_MARCADOR.get(clave)
    if not nombre:
        return ''
    return (f'<img src="{DIR_MARCADORES}/{nombre}" alt="{escape(alt)}" '
            f'role="presentation" width="{ancho}" loading="lazy">')


def _hueco(tipo, nota, fuentes=None, extra_attrs=''):
    f = ''
    if fuentes:
        # ESCAPADAS: el HTML crudo de las fuentes (contextualizaciones viejas,
        # descripciones) traia divs sin balancear que rompian el colapsable
        # de la contextualizacion (bug del acordeon de la Semana 2)
        f = ('<div class="ia-fuentes" style="display:none">' +
             ''.join(f'<div class="ia-fuente">{escape(x)}</div>' for x in fuentes) + '</div>')
    # El aviso NO se imprime como texto: el hueco queda marcado con data-* para
    # que el tablero lo liste en la revision, pero la pagina de Canvas no
    # muestra ningun mensaje ajeno al contenido academico.
    return (f'<div data-ia="{tipo}"{extra_attrs} data-ia-nota="{escape(nota, quote=True)}"'
            f' data-ia-pendiente="1">{f}</div>')


def _pag(nombre, base_url='', curso_id=None):
    slug = nombre.lower().replace(' ', '-')
    if base_url and curso_id:
        return f'{base_url}/courses/{curso_id}/pages/{slug}'
    return f'#{slug}'


def _slug_id(codigo):
    """'5.2' -> '5-2' (para IDs de pestaña unicos y estables)."""
    return re.sub(r'[^0-9a-zA-Z]+', '-', str(codigo or '')).strip('-')


def _ctab(unidad, temas):
    """Cuadro de temas con el markup oficial (#topics .ctab).

    El ID se deriva del CODIGO del tema, no de su posicion. Antes era
    ctab-u{unidad}-{i+1}: cuando una unidad se reparte en dos semanas (p. ej.
    la Unidad 5 con el 5.1 en una semana y el 5.2 en otra) ambos temas eran
    i=0 y generaban el mismo id ctab-u5-1; al coexistir dos bloques con IDs
    repetidos, getElementById devuelve solo el primero y la pestaña del
    segundo tema (el 5.2) no abria. Con el codigo, cada ID es unico.
    """
    nav, panels = [], []
    ids = []
    usados = set()
    for i, t in enumerate(temas):
        base = f'ctab-u{unidad}-{_slug_id(t["codigo"]) or (i + 1)}'
        tid, n = base, 2
        while tid in usados:          # dos temas con el mismo codigo: desempatar
            tid = f'{base}-{n}'; n += 1
        usados.add(tid)
        ids.append(tid)
    for i, t in enumerate(temas):
        act = ' is-active' if i == 0 else ''
        rotulo = f'{t["codigo"]}. {t.get("titulo", "")}'.strip().rstrip('.')
        nav.append(f'<li class="ctab__tab{act}" data-target="{ids[i]}">{escape(rotulo)}</li>')
    for i, t in enumerate(temas):
        act = ' is-active' if i == 0 else ''
        panels.append(f'<div id="{ids[i]}" class="ctab__panel{act}" '
                      f'data-codigo="{t["codigo"]}">{t["html"]}</div>')
    # El CSS y el JS del tema global califican TODAS las reglas de las
    # pestañas con un ancestro .content:
    #     .ed-container .content .ctab__tab { ... }
    # Sin ese contenedor las pestañas no reciben estilos ni escuchan el clic,
    # y el tema queda sin poder abrirse (caso del 5.2).
    return (f'<div class="content">'
            f'<div id="topics-u{unidad}" class="ctab">'
            f'<ul class="ctab__nav">{"".join(nav)}</ul>{"".join(panels)}</div>'
            f'</div>')


# ===========================================================================
# Página de SEMANA
# ===========================================================================

# Frases de cierre de semana: se rotan según la posición de la semana para que
# el cierre no sea repetitivo. Estilo formal, sin tutear, sin referencias
# temporales ni menciones a materias específicas.
FRASES_CIERRE = [
    'Con esto concluye el estudio de los temas propuestos. Le invitamos a repasar los '
    'contenidos revisados y a resolver las actividades planteadas, ya que la práctica '
    'constante consolida el aprendizaje.',
    'Ha llegado al final de este recorrido de contenidos. Recuerde que puede volver sobre '
    'los recursos cuantas veces lo necesite y comunicarse con su docente ante cualquier '
    'inquietud.',
    'Felicitaciones por el avance alcanzado. Le animamos a poner en práctica lo aprendido '
    'y a complementar su estudio con los recursos propuestos en cada apartado.',
    'Excelente trabajo. Los contenidos revisados serán la base de los siguientes '
    'aprendizajes, por lo que le sugerimos repasarlos con detenimiento antes de continuar.',
    'Ha culminado la revisión de estos contenidos. Le motivamos a continuar con entusiasmo '
    'y a aplicar lo aprendido en las actividades y proyectos planteados.',
    'Buen trabajo al completar este apartado. Le recomendamos retomar los puntos que le '
    'hayan resultado más complejos y apoyarse en las actividades para afianzarlos.',
]


def render_semana(semana, temas_html, ra, huecos, *,
                  unidades=None, contextualizacion=None, contexto_fuentes=None,
                  contexto_reusar_de=None, actividades=None, evaluadas=None,
                  autoevaluaciones=None, rango_temas='', extras=None,
                  ctx_definitiva=False, sin_contextualizacion=False,
                  intros_unidad=None, intros_ia=None, cierre=None, intro_semana=None,
                  unidades_inician=None,
                  mostrar_autoeval=True,
                  nav_semanas=None,
                  base_url='', curso_id=None):
    unidades = unidades or []
    nav_semanas = nav_semanas or []
    intros_unidad = intros_unidad or {}
    intros_ia = intros_ia or {}
    # unidades que EMPIEZAN en esta semana: solo esas llevan el titulo
    # "Unidad N." en el cuerpo. Si no se informa, se asume que todas
    # empiezan aqui (comportamiento previo para varias unidades).
    unidades_inician = (set(unidades_inician)
                        if unidades_inician is not None
                        else {n for n, _ in unidades})
    uni_titulo = dict(unidades)
    html = _cuerpo('semana.html')

    # ---- títulos de unidad: FUERA del banner ---------------------------------
    # El banner de semana es solo la imagen; los titulos van DEBAJO, como texto
    # de la pagina. La plantilla oficial todavia los trae dentro de
    # <header class="ed-header">, asi que el migrador los saca automaticamente
    # (no hace falta editar semana.html a mano).
    if unidades:
        # REGLA: el titulo arriba (debajo del banner) va SOLO cuando la semana
        # tiene UNA unidad. Con dos o mas, arriba no va nada y cada titulo
        # aparece abajo encabezando su propio bloque de temas (si no, la
        # unidad se veria repetida dos veces en la pagina).
        if len(unidades) == 1:
            n, t = unidades[0]
            h2s = (f'<h2 id="unit_{n}" class="unit"><strong>Unidad {n}.</strong> '
                   f'{escape(t)}</h2>')
        else:
            h2s = ''
    else:
        h2s = f'<h2 class="unit"><strong>{escape(semana)}</strong></h2>'

    # 1) quitar del <header> cualquier <h2 class="unit"> de la plantilla
    def _vaciar_header(m):
        interior = re.sub(r'<h2[^>]*class="unit"[^>]*>.*?</h2>', '', m.group(2),
                          flags=re.S | re.I)
        return m.group(1) + interior + m.group(3)

    html = re.sub(r'(<header class="ed-header"[^>]*>)(.*?)(</header>)',
                  _vaciar_header, html, count=1, flags=re.S | re.I)

    # 1b) si la plantilla YA fue modificada a mano y trae los <h2 class="unit">
    #     fuera del banner, se eliminan tambien: los titulos reales se insertan
    #     en el paso 2 y de lo contrario quedarian duplicados
    html = re.sub(r'<h2[^>]*class="unit"[^>]*>.*?</h2>', '', html, flags=re.S | re.I)

    # 2) colocar el titulo de unidad ENTRE el nav de semanas y el recuadro del
    #    RA. El orden correcto de la pagina es:
    #        banner -> nav de semanas -> [TITULO DE UNIDAD] ->
    #        <section id="container-learning-outcome"> (recuadro con RA + ctx)
    #    Se ancla ANTES de esa seccion para que el titulo quede por encima del
    #    recuadro (fuera de el) y DEBAJO del nav. Insertarlo tras el banner,
    #    como se hacia antes, lo dejaba ARRIBA del nav de semanas.
    if h2s:
        m_lo = re.search(r'<section id="container-learning-outcome"[^>]*>', html, re.I)
        if m_lo:
            html = html[:m_lo.start()] + h2s + html[m_lo.start():]
        else:
            # sin seccion de RA: dejar el titulo tras el banner (comportamiento previo)
            m_sec = re.search(r'<section id="week_course"[^>]*>.*?</section>', html,
                              re.S | re.I)
            if m_sec:
                html = html[:m_sec.end()] + h2s + html[m_sec.end():]
            else:
                html = re.sub(r'<h2 id="unit_1"[^>]*>.*?</h2>', lambda m: h2s, html,
                              count=1, flags=re.S)

    # ---- botonera: home + semanas reales ------------------------------------
    html = html.replace('$WIKI_REFERENCE$/pages/gf44ceb4edc7df11962d0acb0e8701a9a',
                        _pag('inicio', base_url, curso_id))
    # La semana en la que se esta viendo la pagina lleva class="active": el CSS
    # de la plantilla ya define ese estado
    # (.container-homepage-bnt .block a.active), pero sin la clase todas las
    # semanas se veian iguales y no se distinguia en cual estaba el estudiante.
    links = ' '.join(f'<a title="{escape(s)}" href="{_pag(s, base_url, curso_id)}" '
                     f'data-course-type="wikiPages" data-published="true"'
                     f'{" class=\"active\"" if s == semana else ""}'
                     f'>{s.split()[-1]}</a>'
                     for s in nav_semanas)
    html = re.sub(r'(<div class="block">).*?(</div>)',
                  lambda m: m.group(1) + '<span><strong>Semanas</strong></span> ' + links + m.group(2),
                  html, count=1, flags=re.S)

    # ---- RA y contextualizacion ---------------------------------------------
    # La plantilla nueva ya NO usa id="learning_outcomes" ni
    # id="contextualization": son dos <div class="content-learning-outcomes">
    # consecutivos (el 1º = RA, el 2º = contextualizacion), cada uno precedido
    # por su cabecera <div class="title-learning-outcomes">. Tampoco existe el
    # acordeon .collapse: la contextualizacion es un bloque fijo.
    def _rango_bloque_ra(html_, indice):
        """(inicio_apertura, fin_apertura, inicio_cierre, fin_cierre) del bloque
        .content-learning-outcomes nº indice, contando la anidación de <div>.

        No se usa una expresión regular con .*? porque el contenido puede traer
        <div> anidados (focalizadores, tablas, figuras) y el no-greedy cortaría
        en el </div> equivocado.
        """
        # tolerante al markup real: cualquier etiqueta (div/ul/section...) y la
        # clase acompañada de otras. Antes exigia <div class="..."> exacto y
        # si la plantilla usaba <ul> u otra clase el texto de ejemplo
        # ("Lorem ipsum") se quedaba sin reemplazar.
        ap = re.compile(r'<(?P<tag>\w+)[^>]*\bclass="[^"]*\bcontent-learning-outcomes\b[^"]*"[^>]*>',
                        re.I)
        aperturas = list(ap.finditer(html_))
        if indice >= len(aperturas):
            return None
        m = aperturas[indice]
        prof, pos = 1, m.end()
        etiqueta = m.group('tag')
        tag = re.compile(r'<(/?)' + re.escape(etiqueta) + r'\b[^>]*>', re.I)
        while prof:
            mm = tag.search(html_, pos)
            if not mm:
                return None            # HTML desbalanceado: no se toca
            prof += -1 if mm.group(1) else 1
            pos = mm.end()
        return (m.start(), m.end(), pos - len(mm.group(0)), pos)

    def _set_bloque_ra(html_, indice, contenido):
        """Reemplaza el interior del bloque .content-learning-outcomes nº indice
        (0 = Resultado de Aprendizaje, 1 = Contextualizacion)."""
        r = _rango_bloque_ra(html_, indice)
        if not r:
            return html_
        return html_[:r[1]] + contenido + html_[r[2]:]

    def _quitar_bloque_ra(html_, indice):
        """Elimina la cabecera y el contenido del bloque nº indice."""
        r = _rango_bloque_ra(html_, indice)
        if not r:
            return html_
        # retroceder hasta el inicio de su cabecera .title-learning-outcomes
        cab = None
        for m in re.finditer(r'<\w+[^>]*\bclass="[^"]*\btitle-learning-outcomes\b[^"]*"[^>]*>',
                             html_, re.I):
            if m.start() < r[0]:
                cab = m
            else:
                break
        inicio = cab.start() if cab else r[0]
        return html_[:inicio] + html_[r[3]:]

    # ---- RA: viñetas solo si hay 2+ ------------------------------------------
    if len(ra) == 1:
        ra_inner = f'<p>{ra[0]}</p>'
    else:
        ra_inner = '<ul>' + ''.join(f'<li>{r}</li>' for r in ra) + '</ul>'
    # ---- normalizar la plantilla al formato NUEVO ----------------------------
    # Si semana.html todavia trae la estructura antigua (div#learning_outcomes
    # dentro de .title-learning-outcomes + acordeon .collapse para la
    # contextualizacion), se reescribe aqui al formato del rediseño:
    #   <div class="title-learning-outcomes"> icono + <h3>Resultado…</h3></div>
    #   <div class="content-learning-outcomes"> … </div>
    #   <div class="title-learning-outcomes"> icono + <h3>Contextualización</h3></div>
    #   <div class="content-learning-outcomes"> … </div>
    # Asi el migrador entrega SIEMPRE el formato nuevo, sin que nadie tenga que
    # editar la plantilla a mano.
    if 'id="learning_outcomes"' in html and 'content-learning-outcomes' not in html:
        m_sec = re.search(r'(<section id="container-learning-outcome"[^>]*>)(.*?)(</section>)',
                          html, re.S | re.I)
        if m_sec:
            interior = m_sec.group(2)
            # iconos NUEVOS de marcador; si la carpeta aun no existe se
            # reutilizan los que trajera la plantilla, para no quedar sin icono
            iconos = re.findall(r'<img[^>]*>', interior, re.I)
            ico_ra = (icono_marcador('resultado_aprendizaje', 'Resultado de aprendizaje')
                      or (iconos[0] if iconos else ''))
            ico_ctx = (icono_marcador('contextualizacion', 'Contextualización')
                       or (iconos[1] if len(iconos) > 1 else ico_ra))
            nuevo_bloque = (
                f'{m_sec.group(1)}'
                f'<div class="title-learning-outcomes">{ico_ra}'
                f'<h3>Resultado de Aprendizaje</h3></div>'
                f'<div class="content-learning-outcomes" id="learning_outcomes"></div>'
                f'<div class="title-learning-outcomes">{ico_ctx}'
                f'<h3>Contextualización</h3></div>'
                f'<div class="content-learning-outcomes" id="contextualization"></div>'
                f'{m_sec.group(3)}')
            html = html[:m_sec.start()] + nuevo_bloque + html[m_sec.end():]

    # La plantilla puede venir en DOS estructuras distintas:
    #   (a) original : <div id="learning_outcomes"> + acordeon con
    #                  <div id="contextualization"> dentro de .collapse
    #   (b) rediseño : dos <div class="content-learning-outcomes"> seguidos
    # Se detecta cual es y se usa la via correspondiente, para que el mismo
    # generador sirva con la plantilla actual y con la nueva.
    # OJO: se comprueba la CLASE, no el id. Tras normalizar, los bloques nuevos
    # conservan sus id para compatibilidad, pero la estructura ya es la nueva.
    _estructura_por_id = ('content-learning-outcomes' not in html
                          and 'id="learning_outcomes"' in html)

    if _estructura_por_id:
        html = _set_inner(html, 'learning_outcomes', ra_inner)
    elif _rango_bloque_ra(html, 0):
        html = _set_bloque_ra(html, 0, ra_inner)
        # aviso de diagnostico: si el placeholder sigue en la salida es que la
        # plantilla en disco no coincide con lo que este generador espera
        if 'Texto del resultado de aprendizaje' in html:
            print('  *** El placeholder del RA sigue presente tras el reemplazo: '
                  'revise plantilla_oficial/semana.html')
    else:
        print('\n  *** ATENCION: en plantilla_oficial/semana.html no se encontro '
              'ni id="learning_outcomes" ni class="content-learning-outcomes".\n'
              '      El Resultado de Aprendizaje NO se reemplazara y quedara el '
              'texto de ejemplo de la plantilla.\n')

    # ---- contextualización ---------------------------------------------------
    if contextualizacion and (len(ra) == 1 or ctx_definitiva):
        ctx_inner = contextualizacion
    elif contexto_reusar_de:
        ctx_inner = (f'<div data-ia="contextualizacion-reusar"'
                     f' data-origen="{escape(contexto_reusar_de, quote=True)}"'
                     f' data-ia-pendiente="1"></div>')
    else:
        if len(ra) > 1:
            nota = ('la semana une varios RA → crear una contextualización NUEVA que abarque '
                    'todos los RA; validar antes cada fuente y descartar las que no sean '
                    'contextualizaciones de RA (p. ej. bienvenidas o introducciones de semana)')
        elif contexto_fuentes:
            nota = ('evaluar la contextualización fuente y dar VEREDICTO: si SÍ contextualiza '
                    'el RA, mantenerla tal cual; si NO (bienvenida, introducción de asignatura '
                    'o de semana, lista de temas), generar una contextualización nueva del RA')
        else:
            nota = 'generar la contextualización del RA (no existe fuente)'
        ctx_inner = _hueco('contextualizacion', nota, fuentes=contexto_fuentes)
    if sin_contextualizacion:
        # el RA es el mismo de la semana inmediatamente anterior: la
        # contextualización va solo en la primera aparición, aquí se elimina.
        if _estructura_por_id:
            # plantilla original: se quita el acordeón completo (botón + panel)
            html = re.sub(r'<div class="collapse">.*?<div id="contenido-collapse".*?</div>\s*</div>\s*</div>',
                          '', html, count=1, flags=re.S)
        else:
            html = _quitar_bloque_ra(html, 1)
    else:
        if _estructura_por_id:
            html = _set_inner(html, 'contextualization', ctx_inner)
        else:
            html = _set_bloque_ra(html, 1, ctx_inner)

    # ---- contenido -----------------------------------------------------------
    grupos, orden = {}, []
    for t in temas_html:
        u = int(t['codigo'].split('.')[0])
        if u not in grupos:
            grupos[u] = []
            orden.append(u)
        grupos[u].append(t)

    def _intro(u):
        # la introduccion de UNIDAD ya viene resuelta (tal cual del docente);
        # solo si el curso viejo no traia ninguna descripcion queda el aviso
        if u in intros_ia:
            return intros_ia[u]
        fuentes_u = intros_unidad.get(u) or None
        if not fuentes_u:
            return ''          # la unidad no tenia descripcion: sin aviso
        return _hueco('introduccion',
                      f'unir las descripciones fuente y generar la introducción de la Unidad {u}',
                      fuentes=fuentes_u,
                      extra_attrs=f' data-unidad="{u}"')

    if len(orden) <= 1:
        # UNA unidad: la página oficial tal cual (#introduction + #topics)
        u = orden[0] if orden else 0
        # introduccion de la SEMANA (Agente A3) arriba, y debajo la de la
        # unidad (del docente); si no hay agente, solo la de la unidad
        _iu = (_intro(u) if u else
               _hueco('introduccion', 'generar la introducción de la semana'))
        # UNA sola unidad: el titulo ya se emitio ARRIBA (debajo del banner),
        # asi que aqui no se repite.
        html = _set_inner(html, 'introduction',
                          (intro_semana or '') + _iu)
        r = _rango_elemento(html, 'topics')
        if r and u:
            html = html[:r[0]] + _ctab(u, grupos[u]) + html[r[3]:]
        elif r:
            html = html[:r[0]] + html[r[3]:]
    else:
        # VARIAS unidades (caso no cubierto por la plantilla oficial):
        # encabezado + introducción IA + cuadro por unidad, separados con <hr>
        bloques = []
        if intro_semana:
            # introduccion de la SEMANA (Agente A3): va arriba, antes del
            # primer titulo de unidad. Las intros de unidad siguen siendo del docente
            bloques.append(intro_semana)
        for u in orden:
            # sin <hr> entre unidades: la linea divisoria sobra, el propio
            # titulo "Unidad N." ya separa visualmente los bloques
            # Con DOS o mas unidades el titulo va AQUI, encabezando su bloque
            # de temas (arriba no se emite ninguno, para no duplicarlos).
            bloques.append(f'<div class="subtitle-section"><h3><strong>Unidad {u}.</strong> '
                           f'{escape(uni_titulo.get(u, ""))}</h3></div>')
            bloques.append(_intro(u))
            bloques.append(_ctab(u, grupos[u]))
        ri = _rango_elemento(html, 'introduction')
        rt = _rango_elemento(html, 'topics')
        html = html[:ri[0]] + ''.join(bloques) + html[rt[3]:]

    # ---- titulo del tab: SIEMPRE "Actividades recomendadas" a secas ----------
    # (sin rango ni numeración; los rangos van, si hay unión de semanas, en los
    # títulos internos de cada bloque)
    src_label = re.search(r'(data-tab="recommended_activities".*?<span>)([^<]*)(</span>)', html, re.S)
    if src_label:
        html = (html[:src_label.start(2)] +
                'Actividades recomendadas' + html[src_label.end(2):])

    # ---- paginas adicionales del curso: al final del contenido ----------------
    if extras:
        bloque_extras = []
        for e in extras:
            bloque_extras.append('<hr>')
            bloque_extras.append(f'<div class="subtitle-section"><h3>{escape(e["titulo"])}</h3></div>')
            bloque_extras.append(f'<div data-origen="pagina-adicional" data-slug="{e["slug"]}">{e["html"]}</div>')
        mzona = re.search(r'<div class="title-section[^"]*">(?:(?!</div>).)*?Zona de pr', html, re.S)
        if mzona:
            ini = html.rfind('<div class="title-section', 0, mzona.end())
            html = html[:ini] + ''.join(bloque_extras) + html[ini:]
        else:
            html += ''.join(bloque_extras)

    # ---- cierre de la semana: lo genera el Agente A3; la frase rotativa ------
    # queda solo como RESPALDO cuando el agente aún no ha corrido
    if cierre:
        html = _set_inner(html, 'final_content',
                          f'<div data-ia="cierre-agente">{cierre}</div>')
    else:
        try:
            _idx = (nav_semanas or [semana]).index(semana)
        except ValueError:
            _idx = 0
        _frase = FRASES_CIERRE[_idx % len(FRASES_CIERRE)]
        html = _set_inner(html, 'final_content',
                          f'<p data-origen="cierre-rotativo">{_frase}</p>')

    # ---- zona de práctica ------------------------------------------------------
    if actividades:
        # el aviso de revision NO se imprime en la pagina; queda como atributo
        # data-* para que el tablero lo muestre en la fase de revision
        aviso = ''
        _rev_act = ' data-ia-nota="revisar"' if 'actividad' in huecos else ''
        # cada bloque abre con su <h4 class="ed-act-range"> (título de rango),
        # que es el separador visual entre tramos fusionados: sin <hr>
        html = _set_inner(html, 'recommended_activities',
                          f'<div data-ia="actividad-migrada"{_rev_act}>{aviso}{"".join(actividades)}</div>')
    else:
        html = _set_inner(html, 'recommended_activities',
                          _hueco('actividad', 'generar actividades recomendadas acordes a los temas de la semana'))
    if not mostrar_autoeval:
        # la unidad NO termina en esta semana (el tema continúa en otra):
        # se elimina la pestaña de autoevaluación (label + panel); el resto
        # de la Zona de práctica queda intacto
        html = re.sub(r'<a[^>]*data-tab="self_assessment"[^>]*>.*?</a>', '', html, flags=re.S)
        r = _rango_elemento(html, 'self_assessment')
        if r:
            html = html[:r[0]] + html[r[3]:]
    elif autoevaluaciones:
        html = _set_inner(html, 'self_assessment',
                          '<div data-ia="autoevaluacion-migrada" data-ia-nota="revisar">'
                          # sin <hr> entre autoevaluaciones: la linea divisoria
                          # sobra cuando la semana trae dos
                          + ''.join(autoevaluaciones) + '</div>')
    else:
        html = _set_inner(html, 'self_assessment',
                          _hueco('autoevaluacion', 'revisar/regenerar autoevaluación: puede contener '
                                 'preguntas de temas eliminados o modificados'))
    if evaluadas:
        html = _set_inner(html, 'activities_evaluated',
                          '<div data-ia="actividad-evaluada-migrada" data-ia-nota="revisar">'
                          + '<hr>'.join(evaluadas) + '</div>')
    else:
        html = _set_inner(html, 'activities_evaluated',
                          _hueco('actividad-evaluada', 'colocar enlaces de la actividad evaluada de la semana'))
    return html


# ===========================================================================
# Página de INICIO
# ===========================================================================
def render_inicio(nombre_curso, semanas, f, *, base_url='', curso_id=None, foro_url=None,
                  semanas_evaluacion=None):
    html = _cuerpo('inicio.html')

    # ---- nombre de la asignatura: FUERA del banner --------------------------
    # Igual que en las semanas, el banner de inicio es solo la imagen y el
    # nombre del curso va DEBAJO, sobre fondo blanco. La plantilla oficial aún
    # lo trae dentro de <header class="ed-header">, así que el migrador lo saca
    # automáticamente (no hace falta editar inicio.html a mano).
    _h2 = f'<h2 class="course-name">{escape(nombre_curso)}</h2>'

    def _vaciar_header_inicio(m):
        interior = re.sub(r'<h2[^>]*class="course-name"[^>]*>.*?</h2>', '',
                          m.group(2), flags=re.S | re.I)
        return m.group(1) + interior + m.group(3)

    html = re.sub(r'(<header class="ed-header"[^>]*>)(.*?)(</header>)',
                  _vaciar_header_inicio, html, count=1, flags=re.S | re.I)
    # si la plantilla ya fue modificada y lo trae fuera, se elimina para no duplicar
    html = re.sub(r'<h2[^>]*class="course-name"[^>]*>.*?</h2>', '', html,
                  flags=re.S | re.I)

    m_sec = re.search(r'<section id="header_course"[^>]*>.*?</section>', html,
                      re.S | re.I)
    if m_sec:
        html = html[:m_sec.end()] + _h2 + html[m_sec.end():]
    else:
        html = _h2 + html

    # Visión general ← video de presentación del inicio viejo
    if f.get('video'):
        html = _set_inner(html, 'overview', f'<p style="text-align: center;">{f["video"]}</p>')
    else:
        html = _set_inner(html, 'overview',
                          _hueco('vision-general', 'colocar el video de presentación de la asignatura'))

    # Planificación (los slots oficiales existen por id)
    html = _set_inner(html, 'generic_skills',
                      f.get('competencias_genericas') or
                      _hueco('proposito', 'competencias genéricas de la UTPL'))
    html = _set_inner(html, 'professional_profile_skills',
                      f.get('competencias_perfil') or
                      _hueco('proposito', 'competencias del perfil profesional'))
    html = _set_inner(html, 'learning_methodology',
                      f.get('metodologia') or
                      _hueco('metodologia', 'metodología de aprendizaje (inicio del curso viejo)'))
    if f.get('carga_horaria'):
        html = _set_inner(html, 'workload', f['carga_horaria'])

    # Tu docente: solo docente + info + currículum (tutorías va en página aparte)
    partes = []
    if f.get('docente'):
        # la FOTO la resuelve el JS del tema global vía la API SICA de la UTPL:
        # lee #usuarioDocente (nombre del correo institucional) y setea
        # img#fotoPerfil. Aquí solo se deja el markup con un placeholder.
        usuario = f.get('usuario_sica') or ''
        placeholder = ('$IMS-CC-FILEBASE$/Plantilla/%C3%8Dconos/Normales/'
                       'ic_dummie_metacurso_utpl_junio_2026.svg')
        # si el servidor ya resolvió la foto vía SICA, va la URL directa (no
        # depende del JS del tema); si no, placeholder + JS como antes
        src_foto = f.get('foto_url') or placeholder
        estilo_foto = ('border-radius:50%;object-fit:cover;width:120px;height:120px;'
                       if f.get('foto_url') else '')
        cab = (f'<span id="usuarioDocente" style="display:none">{escape(usuario)}</span>'
               f'<p style="text-align: center;"><img id="fotoPerfil" src="{src_foto}" '
               + (f'style="{estilo_foto}" ' if estilo_foto else '')
               + 'alt="Foto de perfil del docente" width="120" loading="lazy"></p>')
        partes.append(f'<div class="focuser">{cab}<div class="content-focuser">'
                      f'<p><strong>Docente responsable:</strong><br>{escape(f["docente"])}</p></div></div>')
    # ---- Tu docente (antes "Tu docente"): estructura nueva de la plantilla ----
    # .teacher > .profile-picture (foto, correo, teléfono) + .resume (nombre,
    # datos en lista y currículum en párrafo)
    usuario = f.get('usuario_sica') or ''
    placeholder = ('$IMS-CC-FILEBASE$/Plantilla/%C3%8Dconos/Normales/'
                   'ic_dummie_metacurso_utpl_junio_2026.svg')
    src_foto = f.get('foto_url') or placeholder
    foto = (f'<p><img id="fotoPerfil" src="{src_foto}" '
            'style="display: block; margin-left: auto; margin-right: auto;" '
            'alt="Foto de perfil" width="300" height="300" loading="lazy"></p>')
    datos = [foto]
    if usuario:
        datos.append(f'<p><strong>Correo electrónico: </strong>'
                     f'<span id="usuarioDocente">{escape(usuario)}</span>@utpl.edu.ec</p>')
    if f.get('telefono'):
        datos.append(f'<p><strong>Teléfono: </strong>{f["telefono"]}</p>')
    resume = []
    if f.get('docente'):
        resume.append(f'<h2>{escape(f["docente"])}</h2>')
    if f.get('mentor_info'):
        resume.append(f['mentor_info'])
    if f.get('mentor_curriculum'):
        resume.append(f['mentor_curriculum'])
    if not resume:
        resume.append(_hueco('mentor', 'información del docente responsable'))
    html = _set_inner(html, 'mentor',
                      '<div class="teacher">'
                      f'<div class="profile-picture">{"".join(datos)}</div>'
                      f'<div class="resume">{"".join(resume)}</div>'
                      '</div>')

    # Ruta de aprendizaje: weeks-block con las semanas reales.
    #
    # ESTADOS DE DEMOSTRACION (temporales, solo para la prueba):
    # el estado real (Completado / En progreso / En espera) es progreso de cada
    # estudiante y en produccion lo pinta el JS del tema global de Canvas. Para
    # la demo se queman: las dos primeras semanas completadas y la tercera en
    # progreso, de modo que se vean los tres colores del diseño.
    #
    #   >>> Para volver al comportamiento real: poner DEMO_ESTADOS = False <<<
    #
    # La ZONA DE EVALUACION si es estructural: va en las semanas que tienen
    # actividades evaluadas.
    DEMO_ESTADOS = True
    DEMO_COMPLETADAS = 2      # nº de semanas iniciales marcadas como completadas
    DEMO_EN_PROGRESO = 3      # nº de semana marcada como en progreso

    eval_set = set(semanas_evaluacion or [])
    weeks = []
    for i, s in enumerate(semanas):
        estado, clase = 'En espera', 'waiting'
        if DEMO_ESTADOS:
            if i < DEMO_COMPLETADAS:
                estado, clase = 'Completado', 'completed'
            elif i == DEMO_EN_PROGRESO - 1:
                estado, clase = 'En progreso', 'in-progress'
        zona = ('' if s not in eval_set else
                ' <a class="assessment" title="Zona de evaluación" href="#">'
                'Zona de evaluación</a>')
        weeks.append(f'<div class="week"><span class="state">{estado}</span> '
                     f'<a class="btn-week {clase}" title="{escape(s)}" '
                     f'href="{_pag(s, base_url, curso_id)}">{s.split()[-1]}</a>'
                     f'{zona}</div>')
    html = re.sub(r'(<div class="weeks-block">).*?(</div>\s*</section>)',
                  lambda m: m.group(1) + ''.join(weeks) + m.group(2), html, count=1, flags=re.S)
    # El circuito de la ruta lo dibuja el CSS del tema global segun la clase
    # week-N de la seccion, y solo existen variantes para ciertos totales
    # (el modelo oficial del Rediseño 3 es de 8 semanas). Con un total sin
    # variante propia (p. ej. 5 en una prueba parcial) el CSS seguia usando
    # el trazado de 8 y los botones quedaban descuadrados, con la fila
    # inferior vacia. Se elige la variante disponible mas cercana por encima
    # para que el circuito se dibuje completo.
    VARIANTES_RUTA = (5, 8, 16)   # variantes definidas en el CSS
    n = len(semanas)
    variante = next((v for v in VARIANTES_RUTA if v >= n), VARIANTES_RUTA[-1])
    html = re.sub(r'class="week-\d+"', f'class="week-{variante}"', html, count=1)
    render_inicio.aviso_ruta = (
        None if variante == n else
        f'La ruta de aprendizaje se dibuja con el trazado de {variante} semanas '
        f'porque el curso tiene {n}: las posiciones sobrantes quedan vacias.')

    # links de secciones generales hacia las páginas reales del curso destino
    html = _reubicar_href_por_title(html, 'Encuentros en línea',
                                    _pag('Encuentros en línea', base_url, curso_id))
    # Foro de asesoría permanente: apunta al foro ya creado en el curso destino
    if foro_url:
        html = _reubicar_href_por_title(html, 'Foro de asesoría permanente', foro_url)
    # Calendario de actividades (title="Programa" en la plantilla) -> syllabus
    if curso_id:
        syl = f"{(base_url or '').rstrip('/')}/courses/{curso_id}/assignments/syllabus"
        for t in ('Programa', 'Calendario de actividades'):
            html = _reubicar_href_por_title(html, t, syl)
    html = _reubicar_href_por_title(html, 'Fuentes y recursos',
                                    _pag('Fuentes y recursos', base_url, curso_id))
    return html


def _reubicar_href_por_title(html, title, href):
    def _sub(m):
        return re.sub(r'href="[^"]*"', f'href="{href}"', m.group(0), count=1)
    return re.sub(r'<a\b[^>]*title="%s"[^>]*>' % re.escape(title), _sub, html)


# ===========================================================================
# Páginas auxiliares oficiales
# ===========================================================================
def render_fuentes(bibliografia=None, glosario=None, creditos=None, *, base_url='', curso_id=None):
    html = _cuerpo('fuentes-y-recursos.html')
    html = html.replace('$WIKI_REFERENCE$/pages/gf44ceb4edc7df11962d0acb0e8701a9a',
                        _pag('inicio', base_url, curso_id))
    html = _set_inner(html, 'bibliography',
                      bibliografia or _hueco('fuentes', 'colocar las referencias bibliográficas del curso'))
    # Glosario: si el curso viejo no trae ninguno, la pestaña se ELIMINA
    # (label + panel) en vez de quedar vacía. Mismo criterio que la pestaña
    # de autoevaluación cuando la unidad no termina en la semana.
    if glosario and re.sub(r'<[^>]+>', '', glosario).strip():
        html = _set_inner(html, 'glossary', glosario)
    else:
        activo_era_glosario = bool(
            re.search(r'<a[^>]*data-tab="glossary"[^>]*\bclass="[^"]*is-active', html, re.I)
            or re.search(r'<a[^>]*class="[^"]*is-active[^"]*"[^>]*data-tab="glossary"', html, re.I))
        html = re.sub(r'<a[^>]*data-tab="glossary"[^>]*>.*?</a>', '', html, flags=re.S)
        rg = _rango_elemento(html, 'glossary')
        if rg:
            html = html[:rg[0]] + html[rg[3]:]
        # si la pestaña eliminada era la activa, activar la primera que quede
        # (si no, el contenedor arrancaria sin ningun panel visible)
        if activo_era_glosario:
            m = re.search(r'<a[^>]*data-tab="([^"]+)"', html)
            if m:
                tab = m.group(1)
                ma = re.search(r'<a[^>]*data-tab="' + re.escape(tab) + r'"[^>]*>', html)
                if ma:
                    etiqueta = ma.group(0)
                    if 'class="' in etiqueta:
                        nueva = re.sub(r'class="([^"]*)"', r'class="\1 is-active"',
                                       etiqueta, count=1)
                    else:
                        nueva = etiqueta[:-1] + ' class="is-active">'
                    html = html[:ma.start()] + nueva + html[ma.end():]
                r2 = _rango_elemento(html, tab)
                if r2 and 'is-active' not in html[r2[0]:r2[1]]:
                    ap = html[r2[0]:r2[1]]
                    if 'class="' in ap:
                        ap2 = re.sub(r'class="([^"]*)"', r'class="\1 is-active"', ap, count=1)
                    else:
                        ap2 = ap[:-1] + ' class="is-active">'
                    html = html[:r2[0]] + ap2 + html[r2[1]:]
    html = _set_inner(html, 'credits',
                      creditos or _hueco('creditos', 'colocar los créditos del curso'))
    return html


def render_encuentros(contenido=None, *, base_url='', curso_id=None):
    html = _cuerpo('encuentros-en-linea.html')
    html = html.replace('$WIKI_REFERENCE$/pages/gf44ceb4edc7df11962d0acb0e8701a9a',
                        _pag('inicio', base_url, curso_id))
    if contenido:
        html = re.sub(r'(<div class="indentation-3">).*?(</div>\s*</div>\s*)$',
                      lambda m: m.group(1) + contenido + m.group(2), html, count=1, flags=re.S)
    else:
        html = html.replace('<div class="indentation-3">',
                            '<div class="indentation-3" data-ia="encuentros"'
                            ' data-ia-pendiente="1">', 1)
    return html