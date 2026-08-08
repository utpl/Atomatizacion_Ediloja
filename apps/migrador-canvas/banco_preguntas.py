#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
banco_preguntas.py — Modelo canónico de las autoevaluaciones del curso.

PROBLEMA QUE RESUELVE
---------------------
La página "Autoevaluaciones" del curso antiguo guarda la misma información dos
veces: las preguntas en <div id="autoevaluacion_N"> y las respuestas en
<table id="solucionario_N">. El extractor anterior las leía por separado y las
cruzaba por POSICIÓN (enumerate), lo que provocaba tres fallos:

  1. Desalineación. El índice contaba solo las preguntas bien formadas, así que
     una pregunta sin opciones anidadas desplazaba todas las respuestas
     siguientes: la pregunta 5 recibía la retroalimentación de la 4.
  2. Pérdidas silenciosas. Las preguntas que no encajaban en el patrón
     esperado se descartaban sin dejar rastro.
  3. Duplicación. Editar una pregunta no actualizaba el solucionario, porque
     eran dos estructuras independientes.

SOLUCIÓN
--------
Una ÚNICA fuente de verdad: cada Pregunta lleva su enunciado, sus opciones, su
respuesta correcta y su retroalimentación en el mismo objeto. El solucionario
NO se almacena: se RENDERIZA a partir del banco cuando hace falta. Así es
imposible que ambos se desincronicen, y agregar, editar o eliminar una pregunta
es una sola operación.

El cruce con el solucionario se hace por el NÚMERO que escribió el docente
(no por posición), con posición como respaldo, y todo lo que no cuadra genera
una advertencia explícita en vez de desaparecer.
"""
import re
import uuid

# Tipos de pregunta reconocidos
OPCION_MULTIPLE = 'opcion_multiple'      # una sola respuesta correcta
RESPUESTA_MULTIPLE = 'respuesta_multiple'  # varias correctas
VERDADERO_FALSO = 'verdadero_falso'

RE_NUM = re.compile(r'^\s*(\d+)\s*[\.\)]?\s*')
RE_LETRA = re.compile(r'^\s*([a-eA-E])\s*[\.\)]\s*')
RE_VF = re.compile(r'^\s*(verdadero|falso|true|false|v|f)\s*\.?\s*$', re.I)


def _limpiar(t):
    return re.sub(r'\s+', ' ', (t or '')).strip()


def _texto(nodo):
    return _limpiar(nodo.get_text(' ')) if nodo is not None else ''


class Pregunta:
    """Unidad independiente y completa. Todo lo relativo a una pregunta vive
    aquí: enunciado, opciones, respuestas correctas, retroalimentación general
    y por opción, recursos y puntuación.

    El solucionario NO es un dato aparte: se deriva de `correctas` y
    `retroalimentacion` (ver `Banco.solucionario()`).
    """

    __slots__ = ('id', 'numero', 'enunciado', 'tipo', 'opciones', 'correctas',
                 'retroalimentacion', 'retro_opcion', 'recursos', 'puntos',
                 'avisos')

    def __init__(self, enunciado='', numero=None, tipo=OPCION_MULTIPLE,
                 opciones=None, correctas=None, retroalimentacion='',
                 retro_opcion=None, recursos=None, puntos=None, id=None):
        self.id = id or f'p_{uuid.uuid4().hex[:10]}'
        self.numero = numero
        self.enunciado = enunciado
        self.tipo = tipo
        self.opciones = list(opciones or [])
        self.correctas = sorted(set(correctas or []))   # índices en `opciones`
        self.retroalimentacion = retroalimentacion
        self.retro_opcion = dict(retro_opcion or {})    # {indice: texto}
        self.recursos = list(recursos or [])            # imágenes, tablas, iframes
        self.puntos = puntos
        self.avisos = []

    # -- consultas ---------------------------------------------------------
    @property
    def letra_correcta(self):
        """'a', 'b'… o 'a, c' si hay varias. '' si no hay respuesta."""
        return ', '.join(chr(97 + i) for i in self.correctas
                         if 0 <= i < len(self.opciones))

    @property
    def completa(self):
        return bool(self.enunciado and len(self.opciones) >= 2 and self.correctas)

    def validar(self):
        """Advertencias sin descartar la pregunta. Devuelve lista de textos."""
        av = []
        if not self.enunciado:
            av.append('sin enunciado')
        if len(self.opciones) < 2:
            av.append(f'solo {len(self.opciones)} opción(es)')
        if not self.correctas:
            av.append('sin respuesta correcta marcada')
        for i in self.correctas:
            if not (0 <= i < len(self.opciones)):
                av.append(f'respuesta correcta fuera de rango ({i})')
        if self.tipo == OPCION_MULTIPLE and len(self.correctas) > 1:
            av.append('marcada como opción múltiple pero tiene varias correctas')
        if not self.retroalimentacion:
            av.append('sin retroalimentación')
        vacias = [i + 1 for i, o in enumerate(self.opciones) if not _limpiar(o)]
        if vacias:
            av.append(f'opción(es) vacía(s): {vacias}')
        self.avisos = av
        return av

    # -- edición -----------------------------------------------------------
    def set_correcta(self, indice_o_letra):
        """Marca la respuesta correcta. Acepta índice (0) o letra ('a')."""
        if isinstance(indice_o_letra, str) and indice_o_letra.strip():
            i = ord(indice_o_letra.strip().lower()[0]) - 97
        else:
            i = int(indice_o_letra)
        self.correctas = [i] if 0 <= i < len(self.opciones) else []
        return self

    def to_dict(self):
        return {'id': self.id, 'numero': self.numero, 'enunciado': self.enunciado,
                'tipo': self.tipo, 'opciones': self.opciones,
                'correctas': self.correctas, 'letra_correcta': self.letra_correcta,
                'retroalimentacion': self.retroalimentacion,
                'retro_opcion': self.retro_opcion, 'recursos': self.recursos,
                'puntos': self.puntos, 'avisos': self.avisos,
                'completa': self.completa}

    @classmethod
    def from_dict(cls, d):
        p = cls(enunciado=d.get('enunciado', ''), numero=d.get('numero'),
                tipo=d.get('tipo', OPCION_MULTIPLE), opciones=d.get('opciones'),
                correctas=d.get('correctas'),
                retroalimentacion=d.get('retroalimentacion', ''),
                retro_opcion=d.get('retro_opcion'), recursos=d.get('recursos'),
                puntos=d.get('puntos'), id=d.get('id'))
        p.validar()
        return p


class Banco:
    """Conjunto ordenado de preguntas de UNA autoevaluación.

    Mantiene el orden en que aparecen en Canvas y renumera automáticamente al
    agregar o eliminar, de modo que nunca queden huecos ni referencias
    huérfanas en el solucionario (que se deriva de aquí, no se guarda).
    """

    def __init__(self, numero=None, titulo='', preguntas=None):
        self.numero = numero            # 1..N (autoevaluacion_N)
        self.titulo = titulo
        self.preguntas = list(preguntas or [])
        self.avisos = []
        self.renumerar()

    # -- operaciones de edición -------------------------------------------
    def renumerar(self):
        """Numeración consecutiva desde 1, respetando el orden actual."""
        for i, p in enumerate(self.preguntas, 1):
            p.numero = i
        return self

    def agregar(self, pregunta, posicion=None):
        """Añade una pregunta. Aparece automáticamente en el solucionario."""
        if posicion is None:
            self.preguntas.append(pregunta)
        else:
            self.preguntas.insert(max(0, min(posicion, len(self.preguntas))),
                                  pregunta)
        self.renumerar()
        return pregunta

    def eliminar(self, id_pregunta):
        """Elimina del banco Y del solucionario (que se deriva del banco)."""
        antes = len(self.preguntas)
        self.preguntas = [p for p in self.preguntas if p.id != id_pregunta]
        self.renumerar()
        return len(self.preguntas) < antes

    def mover(self, id_pregunta, nueva_posicion):
        p = self.obtener(id_pregunta)
        if not p:
            return False
        self.preguntas.remove(p)
        self.preguntas.insert(max(0, min(nueva_posicion, len(self.preguntas))), p)
        self.renumerar()
        return True

    def obtener(self, id_pregunta):
        return next((p for p in self.preguntas if p.id == id_pregunta), None)

    def actualizar(self, id_pregunta, **campos):
        """Edita una pregunta. El cambio se refleja solo en el solucionario
        porque este se genera a partir de estos mismos datos."""
        p = self.obtener(id_pregunta)
        if not p:
            return None
        for k, v in campos.items():
            if k == 'correcta':
                p.set_correcta(v)
            elif hasattr(p, k):
                setattr(p, k, v)
        p.validar()
        return p

    # -- validación --------------------------------------------------------
    def validar(self):
        """Advertencias de todo el banco, sin detener el procesamiento."""
        self.avisos = []
        for p in self.preguntas:
            for a in p.validar():
                self.avisos.append({'pregunta_id': p.id, 'numero': p.numero,
                                    'enunciado': p.enunciado[:70], 'aviso': a})
        return self.avisos

    # -- derivados ---------------------------------------------------------
    def solucionario(self):
        """Solucionario DERIVADO del banco. No se almacena: se calcula.

        Así es imposible que quede desincronizado con las preguntas.
        """
        return [{'numero': p.numero, 'pregunta_id': p.id,
                 'respuesta': p.letra_correcta or '—',
                 'retroalimentacion': p.retroalimentacion or ''}
                for p in self.preguntas]

    def to_dict(self):
        return {'numero': self.numero, 'titulo': self.titulo,
                'preguntas': [p.to_dict() for p in self.preguntas],
                'solucionario': self.solucionario(),
                'avisos': self.avisos,
                'total': len(self.preguntas),
                'completas': sum(1 for p in self.preguntas if p.completa)}

    @classmethod
    def from_dict(cls, d):
        b = cls(numero=d.get('numero'), titulo=d.get('titulo', ''),
                preguntas=[Pregunta.from_dict(p) for p in (d.get('preguntas') or [])])
        b.validar()
        return b


# ---------------------------------------------------------------------------
# Extracción desde el HTML de la página "Autoevaluaciones"
# ---------------------------------------------------------------------------
def _recursos_de(nodo):
    """Imágenes, tablas e iframes asociados a una pregunta."""
    out = []
    if nodo is None:
        return out
    for img in nodo.find_all('img'):
        out.append({'tipo': 'imagen', 'src': img.get('src', ''),
                    'alt': img.get('alt', '')})
    for ifr in nodo.find_all('iframe'):
        out.append({'tipo': 'iframe', 'src': ifr.get('src', ''),
                    'titulo': ifr.get('title', '')})
    for tb in nodo.find_all('table'):
        out.append({'tipo': 'tabla', 'html': str(tb)})
    return out


def _tipo_de(opciones):
    """Deduce el tipo de pregunta a partir de sus opciones."""
    if len(opciones) == 2 and all(RE_VF.match(o or '') for o in opciones):
        return VERDADERO_FALSO
    return OPCION_MULTIPLE


def _leer_solucionarios(sopa):
    """{n_autoeval: {n_pregunta: (letras, retroalimentacion)}}

    Se indexa por el NÚMERO que escribió el docente, no por posición: es lo
    que permite cruzar sin desalinearse aunque falte alguna pregunta.
    """
    soluciones = {}
    for tabla in sopa.find_all('table', id=re.compile(r'^solucionario_(\d+)$', re.I)):
        n = int(re.search(r'(\d+)$', tabla.get('id')).group(1))
        filas = {}
        for tr in tabla.find_all('tr'):
            celdas = tr.find_all(['td', 'th'])
            if len(celdas) < 3:
                continue
            num = _texto(celdas[0])
            resp = _texto(celdas[1]).lower()
            retro = _texto(celdas[2])
            if not num.isdigit():
                continue
            letras = re.findall(r'[a-e]', resp)
            if letras:
                filas[int(num)] = (letras, retro)
        if filas:
            soluciones[n] = filas
    return soluciones


def _preguntas_de_lista(lista, recursos_padre=True):
    """Preguntas de un <ol> con opciones anidadas.

    Cada <li> de primer nivel es una pregunta; su <ol>/<ul> anidado son las
    opciones. Se conserva el orden y se respeta el número explícito del
    docente si el enunciado empieza por "N." o si el <li> trae value=N.
    """
    out = []
    for li in lista.find_all('li', recursive=False):
        anid = li.find(['ol', 'ul'])
        # enunciado: todo el contenido directo menos la lista de opciones
        partes = []
        for x in li.contents:
            if getattr(x, 'name', None) in ('ol', 'ul'):
                continue
            partes.append(x if isinstance(x, str) else x.get_text(' '))
        enun = _limpiar(''.join(partes))

        # número explícito: atributo value o prefijo "N." en el texto
        numero = None
        if li.get('value') and str(li['value']).isdigit():
            numero = int(li['value'])
        m = RE_NUM.match(enun)
        if m:
            if numero is None:
                numero = int(m.group(1))
            enun = enun[m.end():].strip()

        opciones, retro_op = [], {}
        if anid:
            for j, o in enumerate(anid.find_all('li', recursive=False)):
                txt = _texto(o)
                txt = RE_LETRA.sub('', txt)      # quitar "a." si viene escrito
                opciones.append(txt)

        p = Pregunta(enunciado=enun, numero=numero, opciones=opciones,
                     tipo=_tipo_de(opciones), retro_opcion=retro_op,
                     recursos=_recursos_de(li) if recursos_padre else [])
        out.append(p)
    return out


def extraer_banco(html):
    """HTML de la página "Autoevaluaciones" → {N: Banco}.

    A diferencia del extractor anterior:
      · conserva el orden original y TODAS las preguntas (las incompletas
        también, marcadas con advertencias, en vez de descartarlas en silencio);
      · cruza con el solucionario por el NÚMERO del docente, con la posición
        solo como respaldo;
      · no guarda el solucionario: lo deriva del banco.
    """
    if not html:
        return {}
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}
    sopa = BeautifulSoup(html, 'html.parser')
    soluciones = _leer_solucionarios(sopa)

    bancos = {}
    for div in sopa.find_all('div', id=re.compile(r'^autoevaluacion_(\d+)$', re.I)):
        n = int(re.search(r'(\d+)$', div.get('id')).group(1))
        lista = div.find('ol')
        if not lista:
            continue

        titulo = ''
        cap = div.find(['h1', 'h2', 'h3', 'h4'])
        if cap:
            titulo = _texto(cap)

        preguntas = _preguntas_de_lista(lista)
        sol = soluciones.get(n, {})

        # cruce por NÚMERO del docente; si no hay, por posición
        for pos, p in enumerate(preguntas, 1):
            clave = p.numero if (p.numero in sol) else pos
            letras, retro = sol.get(clave, (None, ''))
            if letras:
                idx = [ord(l) - 97 for l in letras]
                p.correctas = [i for i in idx if 0 <= i < len(p.opciones)]
                if len(p.correctas) > 1:
                    p.tipo = RESPUESTA_MULTIPLE
                if len(idx) != len(p.correctas):
                    p.avisos.append('el solucionario indica una opción inexistente')
            p.retroalimentacion = retro or p.retroalimentacion

        b = Banco(numero=n, titulo=titulo or f'Autoevaluación {n}',
                  preguntas=preguntas)
        b.validar()
        # avisos de coherencia entre banco y solucionario
        if sol and len(sol) != len(preguntas):
            b.avisos.append({'pregunta_id': None, 'numero': None,
                             'enunciado': '',
                             'aviso': f'el solucionario tiene {len(sol)} entradas '
                                      f'y el banco {len(preguntas)} preguntas'})
        bancos[n] = b
    return bancos


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def _esc(t):
    return (str(t or '').replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def render_banco_html(banco):
    """Banco → HTML de la página "Autoevaluaciones" (preguntas + solucionario).

    El solucionario se genera aquí a partir del banco: por eso editar una
    pregunta lo actualiza sin ninguna sincronización manual.
    """
    n = banco.numero
    preguntas = []
    for p in banco.preguntas:
        ops = ''.join(f'<li>{_esc(o)}</li>' for o in p.opciones)
        preguntas.append(f'<li>{_esc(p.enunciado)}<ol type="a">{ops}</ol></li>')
    filas = ''.join(
        f'<tr><td>{s["numero"]}</td><td>{_esc(s["respuesta"])}</td>'
        f'<td>{_esc(s["retroalimentacion"])}</td></tr>'
        for s in banco.solucionario())
    return (
        f'<div id="autoevaluacion_{n}">'
        f'<p>En los siguientes enunciados, seleccione solo una respuesta correcta:</p>'
        f'<ol>{"".join(preguntas)}</ol>'
        f'<p class="boton-secundario"><a href="#solucionario_{n}">Ir al solucionario</a></p>'
        f'</div>'
        f'<table id="solucionario_{n}" class="table-general">'
        f'<caption><strong>{_esc(banco.titulo)}</strong></caption>'
        f'<thead><tr><th scope="col">Pregunta</th><th scope="col">Respuesta</th>'
        f'<th scope="col">Retroalimentación</th></tr></thead>'
        f'<tbody>{filas}</tbody></table>')


def render_interactiva(banco):
    """Banco → autoevaluación interactiva para la pestaña de la semana.

    Sin JavaScript ni recursos externos: radios + CSS, para que el sanitizador
    de Canvas no pueda desactivarla.
    """
    if not banco.preguntas:
        return ''
    uid = f'ae{banco.numero}'
    bloques = []
    for i, p in enumerate(banco.preguntas, 1):
        nombre = f'{uid}_{i}'
        ops = []
        for j, o in enumerate(p.opciones):
            ok = ' ae-ok' if j in p.correctas else ''
            ops.append(f'<label class="ae-op{ok}"><input type="radio" '
                       f'name="{nombre}"><span>{_esc(o)}</span></label>')
        bloques.append(
            f'<li class="ae-preg"><p class="ae-enun">{_esc(p.enunciado)}</p>'
            f'<div class="ae-ops">{"".join(ops)}</div>'
            f'<p class="ae-fb"><strong>Retroalimentación.</strong> '
            f'{_esc(p.retroalimentacion)}</p></li>')
    estilo = (
        '<style>'
        '.ae-wrap{border:1px solid #bbd6e7;border-radius:8px;padding:14px 18px;margin:1em 0}'
        '.ae-preg{margin:0 0 1.2em;padding-bottom:1em;border-bottom:1px solid #e3edf5;list-style:none}'
        '.ae-preg:last-child{border-bottom:0;margin-bottom:0}'
        '.ae-enun{font-weight:600;color:#083e70;margin:0 0 .6em}'
        '.ae-op{display:block;padding:6px 10px;margin:4px 0;border:1px solid #c8ddeb;'
        'border-radius:6px;cursor:pointer}'
        '.ae-op:hover{background:#f0f5f9}'
        '.ae-op input{margin-right:8px}'
        '.ae-op:has(input:checked){border-color:#adb5bd;background:#f1f3f5}'
        '.ae-op.ae-ok:has(input:checked){border-color:#087f5b;background:#d8f5a2}'
        '.ae-fb{display:none;margin:.6em 0 0;padding:8px 12px;border-radius:6px;'
        'background:#fcf5e5;border-left:4px solid #eaa621;font-size:.95em}'
        '.ae-preg:has(input:checked) .ae-fb{display:block}'
        '</style>')
    return (f'{estilo}<div class="ae-wrap" data-ia="autoevaluacion-generada">'
            f'<ol style="margin:0;padding:0">{"".join(bloques)}</ol></div>')
