#!/usr/bin/env python3
"""
canvas_assets.py — Inventario y migración de assets entre cursos Canvas.

Resuelve "sacar imágenes y focalizadores y todo lo que haya en el viejo y pasarlo al nuevo":

  1. inventariar(html)            → lista estructurada de todos los assets de una página/tema
  2. copiar_archivos(...)         → copia los archivos (imágenes, PDFs, audios) del curso
                                     viejo al nuevo vía Canvas Files API → devuelve mapa id_viejo→id_nuevo
  3. reescribir_html(html, mapa)  → reemplaza file IDs / URLs viejos por los nuevos

Los iframes externos (Genially, YouTube, Educaplay) NO se copian: apuntan a servidores
externos y se conservan tal cual. Solo se migran los archivos alojados en Canvas.
"""
import re, time, requests
from html.parser import HTMLParser

# courses/<id>/files/<file_id>
RE_FILE = re.compile(r'/courses/(\d+)/files/(\d+)')
# igual pero capturando el host (necesario al migrar entre instancias)
RE_FILE_URL = re.compile(r'(?:https?://[^/\s"\'>]+)?/courses/(\d+)/files/(\d+)')
RE_FILE_ID_ATTR = re.compile(r'\bid="(\d+)"')


def _clase(attrs):
    for k, v in attrs:
        if k == 'class':
            return v
    return ''


class _Inventario(HTMLParser):
    """Recorre el HTML y clasifica assets sin depender de la plantilla."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.assets = []
        self._depth_focal = 0
        self._cur_fig = None
        self._buf = []
        self._in_footer = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get('class', '')
        if tag == 'img':
            src = a.get('src', '')
            m = RE_FILE.search(a.get('data-api-endpoint', '') or src)
            self.assets.append({
                'tipo': 'imagen',
                'file_id': m.group(2) if m else a.get('id'),
                'src': src, 'alt': a.get('alt', ''),
                'width': a.get('width'), 'height': a.get('height'),
                'decorativa': a.get('data-decorative') == 'True',
                'en_focalizador': self._depth_focal > 0,
            })
        elif tag == 'iframe':
            src = a.get('src', '')
            dom = re.sub(r'https?://([^/]+)/.*', r'\1', src)
            self.assets.append({'tipo': 'iframe', 'src': src, 'dominio': dom,
                                'titulo': a.get('title', ''), 'externo': True})
        elif tag == 'div' and 'focalizador' in cls:
            self._depth_focal += 1
            self.assets.append({'tipo': 'focalizador', 'estilo': a.get('style', '')})
        elif tag == 'div' and 'contenedor-recurso' in cls:
            self.assets.append({'tipo': 'contenedor-recursos'})
        elif tag == 'table':
            self.assets.append({'tipo': 'tabla', 'clase': cls})
        elif tag == 'figure':
            self.assets.append({'tipo': 'figura', 'clase': cls})
        elif tag == 'a':
            href = a.get('href', '')
            m = RE_FILE.search(href)
            if m:  # enlace a archivo Canvas (pdf, doc, audio)
                self.assets.append({'tipo': 'archivo_enlazado', 'file_id': m.group(2), 'href': href})

    def handle_endtag(self, tag):
        if tag == 'div' and self._depth_focal > 0:
            self._depth_focal -= 1


def inventariar(html):
    """Devuelve dict con conteos y lista de assets de un fragmento HTML."""
    p = _Inventario()
    p.feed(html or '')
    file_ids = sorted({a['file_id'] for a in p.assets
                       if a.get('file_id') and str(a['file_id']).isdigit()})
    resumen = {}
    for a in p.assets:
        resumen[a['tipo']] = resumen.get(a['tipo'], 0) + 1
    return {'resumen': resumen, 'assets': p.assets, 'file_ids': file_ids}


# ---------------------------------------------------------------------------
# Migración de archivos entre cursos vía Canvas API
# ---------------------------------------------------------------------------
def _folder_raiz(base, token, course_id):
    """Carpeta raíz del curso destino. Prueba varios endpoints porque
    algunos requieren permisos distintos (by_path suele dar 403 con
    tokens de docente). Devuelve None si ninguno está permitido."""
    h = {'Authorization': f'Bearer {token}'}
    for url, extraer in (
        (f'{base}/api/v1/courses/{course_id}/folders/root', lambda j: j.get('id')),
        (f'{base}/api/v1/courses/{course_id}/folders/by_path', lambda j: j[-1]['id']),
        (f'{base}/api/v1/courses/{course_id}/folders?per_page=100',
         lambda j: next((f['id'] for f in j if f.get('parent_folder_id') is None), None)),
    ):
        try:
            r = requests.get(url, headers=h, timeout=30)
            if r.status_code == 200:
                fid = extraer(r.json())
                if fid:
                    return fid
        except requests.RequestException:
            pass
    return None


_fallos = {}   # file_id -> motivo por el que no se pudo copiar


def _reintentar(fn, intentos=3, espera=4):
    """Reintenta ante timeouts o cortes de conexión con Canvas."""
    ultimo = None
    for i in range(1, intentos + 1):
        try:
            return fn()
        except (requests.Timeout, requests.ConnectionError) as e:
            ultimo = e
            if i < intentos:
                time.sleep(espera * i)
    raise ultimo


# Carpeta unica donde aterrizan los archivos migrados del curso viejo. Sin
# parent_folder_path Canvas los manda a "unfiled", y como la copia corre en
# 5 hilos, cada hilo creaba su propia carpeta "unfiled" duplicada.
CARPETA_MIGRADOS = 'Migrados'


def _subir_por_descarga(base_origen, token_origen, base_destino, token_destino,
                        curso_destino, fid, carpeta_path=CARPETA_MIGRADOS):
    """Descarga el archivo de la instancia ORIGEN y lo sube a la instancia
    DESTINO con el flujo estándar de 3 pasos (POST /courses/:id/files).
    Es la única vía posible cuando origen y destino son instancias
    distintas (producción → test), y también el fallback cuando copy_file
    no está permitido."""
    ho = {'Authorization': f'Bearer {token_origen}'}
    h = {'Authorization': f'Bearer {token_destino}'}
    meta = _reintentar(lambda: requests.get(f'{base_origen}/api/v1/files/{fid}', headers=ho, timeout=60))
    if meta.status_code != 200:
        _fallos[fid] = f'metadatos HTTP {meta.status_code} (archivo borrado o sin permiso en origen)'
        return None
    meta = meta.json()
    if meta.get('hidden') or meta.get('locked'):
        _fallos[fid] = 'archivo oculto/bloqueado en el curso origen'
    contenido = _reintentar(lambda: requests.get(meta['url'], headers=ho, timeout=180))
    if contenido.status_code != 200:
        _fallos[fid] = f'descarga HTTP {contenido.status_code}'
        return None
    datos = {'name': meta['display_name'],
             'size': meta.get('size') or len(contenido.content),
             'content_type': meta.get('content-type', ''),
             'on_duplicate': 'rename'}
    if carpeta_path:
        # carpeta fija: evita las multiples "unfiled" creadas en paralelo
        datos['parent_folder_path'] = carpeta_path
    paso1 = requests.post(f'{base_destino}/api/v1/courses/{curso_destino}/files',
                          headers=h, data=datos, timeout=60)
    if paso1.status_code not in (200, 201):
        _fallos[fid] = (f'no se pudo iniciar la subida al destino: HTTP {paso1.status_code} '
                        f'{paso1.text[:120]}')
        return None
    p1 = paso1.json()
    paso2 = requests.post(p1['upload_url'],
                          data=p1.get('upload_params', {}),
                          files={'file': (meta['display_name'], contenido.content)},
                          timeout=300)
    if paso2.status_code in (200, 201):
        return paso2.json().get('id')
    if paso2.status_code in (301, 302, 303):
        conf = requests.post(paso2.headers['Location'], headers=h, timeout=60)
        if conf.status_code in (200, 201):
            return conf.json().get('id')
        _fallos[fid] = f'confirmacion de subida HTTP {conf.status_code}'
        return None
    _fallos[fid] = f'subida al destino HTTP {paso2.status_code} {paso2.text[:120]}'
    return None


def _asegurar_carpeta(base, token, curso_id, ruta):
    """Crea la carpeta en el curso destino si no existe, y devuelve su id.
    Canvas reutiliza la carpeta cuando ya esta creada, asi que llamarla una
    vez antes de la copia en paralelo evita carpetas duplicadas."""
    h = {'Authorization': f'Bearer {token}'}
    try:
        r = requests.get(f'{base}/api/v1/courses/{curso_id}/folders/by_path/{ruta}',
                         headers=h, timeout=30)
        if r.status_code == 200:
            j = r.json()
            if j:
                return j[-1].get('id')
    except requests.RequestException:
        pass
    try:
        raiz = _folder_raiz(base, token, curso_id)
        if not raiz:
            return None
        r = requests.post(f'{base}/api/v1/folders/{raiz}/folders',
                          headers=h, data={'name': ruta}, timeout=30)
        if r.status_code in (200, 201):
            return r.json().get('id')
    except requests.RequestException:
        pass
    return None


def copiar_archivos(base, token, curso_origen, curso_destino, file_ids, carpeta_destino=None,
                    base_destino=None, token_destino=None, progreso=None):
    """
    Copia cada archivo del curso origen al destino. Estrategia:
      1. copy_file sobre la carpeta raíz (rápido, servidor a servidor);
      2. si no hay carpeta o copy_file da 401/403 → descarga+subida
         (flujo estándar de 3 pasos, permitido a docentes);
      3. lo que falle queda mapeado a None (la página marca esas imágenes
         con data-migracion="pendiente" y siguen apuntando al curso viejo).
    Nunca lanza excepción: la subida del curso no debe morir por un archivo.
    """
    base_destino = (base_destino or base).rstrip('/')
    token_destino = token_destino or token
    misma_instancia = base_destino == base.rstrip('/')
    h = {'Authorization': f'Bearer {token_destino}'}
    if misma_instancia and carpeta_destino is None:
        carpeta_destino = _folder_raiz(base_destino, token_destino, curso_destino)
    # copy_file solo sirve dentro de la MISMA instancia; entre producción y
    # test siempre se va por descarga+subida
    usar_copy = [misma_instancia and carpeta_destino is not None]
    if not usar_copy[0]:
        # crear la carpeta destino UNA sola vez, antes de lanzar los hilos:
        # si se deja que la creen los 5 hilos a la vez, Canvas genera
        # carpetas duplicadas por la carrera entre peticiones
        _asegurar_carpeta(base_destino, token_destino, curso_destino,
                          CARPETA_MIGRADOS)
    mapa = {}

    def _uno(fid):
        try:
            if usar_copy[0]:
                r = requests.post(
                    f'{base_destino}/api/v1/folders/{carpeta_destino}/copy_file',
                    headers=h, data={'source_file_id': fid, 'on_duplicate': 'rename'},
                    timeout=60)
                if r.status_code in (200, 201):
                    return fid, r.json().get('id')
                if r.status_code in (401, 403):
                    usar_copy[0] = False  # sin permiso: cambiar de estrategia
            return fid, _subir_por_descarga(base, token, base_destino, token_destino,
                                            curso_destino, fid)
        except requests.RequestException as e:
            _fallos[fid] = f'{type(e).__name__}: {e}'
            return fid, None

    # en PARALELO (5 hilos): entre instancias distintas cada archivo son ~4
    # peticiones (descarga + subida en 3 pasos); en serie 63 archivos tomaban
    # varios minutos
    from concurrent.futures import ThreadPoolExecutor
    hechos = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        for fid, nuevo in ex.map(_uno, file_ids):
            mapa[fid] = nuevo
            hechos += 1
            if progreso:
                try:
                    progreso(hechos, len(file_ids))
                except Exception:
                    pass
    return mapa


def reescribir_html(html, mapa_ids, base, curso_destino):
    """
    Reemplaza toda referencia a courses/<viejo>/files/<id_viejo> por
    courses/<destino>/files/<id_nuevo>, y actualiza id="..." de las <img>.
    Los file IDs sin nuevo equivalente se dejan intactos y se marcan con data-migracion="pendiente".
    """
    pendientes = set()

    def _sub_url(m):
        curso_v, fid = m.group(1), m.group(2)
        nuevo = mapa_ids.get(fid)
        if nuevo:
            return base.rstrip('/') + f'/courses/{curso_destino}/files/{nuevo}'
        pendientes.add(fid)   # quedó apuntando al curso viejo
        return m.group(0)
    nuevo_html = RE_FILE_URL.sub(_sub_url, html)

    # verifier viejos ya no sirven en el curso nuevo → quitarlos (Canvas los regenera)
    nuevo_html = re.sub(r'(\?|&)verifier=[A-Za-z0-9]+', '', nuevo_html)

    # actualizar atributo id="fid_viejo" de imágenes
    def _sub_id(m):
        fid = m.group(1)
        nuevo = mapa_ids.get(fid)
        return f'id="{nuevo}"' if nuevo else f'id="{fid}" data-migracion="pendiente"'
    nuevo_html = RE_FILE_ID_ATTR.sub(_sub_id, nuevo_html)
    reescribir_html.pendientes = pendientes
    return nuevo_html


if __name__ == '__main__':
    import json, sys
    canvas = json.load(open(sys.argv[1]))
    total = {}
    for m in canvas['modulos']:
        for it in m['items']:
            if not it.get('html'):
                continue
            inv = inventariar(it['html'])
            for k, v in inv['resumen'].items():
                total[k] = total.get(k, 0) + v
    print('Inventario global de assets:')
    for k, v in sorted(total.items(), key=lambda x: -x[1]):
        print(f'  {k:<20} {v}')

import os as _os
import urllib.parse as _up

# El token IMSCC solo se resuelve en exportaciones .imscc; via API Canvas no.
# El migrador emite @@PLANTILLA@@ y aqui se sustituye por la URL real del
# archivo ya subido. Se sigue aceptando el token viejo por compatibilidad.
RE_IMS = re.compile(r'(?:\$IMS-CC-FILEBASE\$|@@PLANTILLA@@)/([^"\s>]+)')


def subir_recursos_plantilla(base, token, curso_id, dir_local):
    """Sube el arbol de recursos de la plantilla oficial (iconos, encabezados,
    focalizadores) al curso destino conservando las carpetas, con el flujo
    estandar de 3 pasos. Devuelve {ruta_relativa: file_id}. Nunca lanza."""
    h = {'Authorization': f'Bearer {token}'}
    rutas = {}
    for raiz, _dirs, archivos in _os.walk(dir_local):
        for nombre in archivos:
            completo = _os.path.join(raiz, nombre)
            rel = _os.path.relpath(completo, dir_local).replace(_os.sep, '/')
            rutas[rel] = None
            try:
                contenido = open(completo, 'rb').read()
                carpeta = _os.path.dirname(rel)
                paso1 = requests.post(f'{base}/api/v1/courses/{curso_id}/files',
                                      headers=h,
                                      data={'name': nombre, 'size': len(contenido),
                                            'parent_folder_path': f'Plantilla_Recursos/{carpeta}' if carpeta else 'Plantilla_Recursos',
                                            'on_duplicate': 'overwrite'}, timeout=60)
                if paso1.status_code not in (200, 201):
                    continue
                p1 = paso1.json()
                paso2 = requests.post(p1['upload_url'], data=p1.get('upload_params', {}),
                                      files={'file': (nombre, contenido)}, timeout=300)
                if paso2.status_code in (200, 201):
                    rutas[rel] = paso2.json().get('id')
                elif paso2.status_code in (301, 302, 303):
                    conf = requests.post(paso2.headers['Location'], headers=h, timeout=60)
                    if conf.status_code in (200, 201):
                        rutas[rel] = conf.json().get('id')
            except Exception:
                rutas[rel] = None
    return rutas


def reescribir_tokens_plantilla(html, rutas, base, curso_id):
    """$IMS-CC-FILEBASE$/RUTA → URL del archivo subido al curso destino.
    Las rutas del token vienen URL-encoded (Íconos → %C3%8Dconos)."""
    sin_resolver = set()

    def _sub(m):
        rel = _up.unquote(m.group(1))
        fid = rutas.get(rel)
        if fid:
            return f'{base.rstrip("/")}/courses/{curso_id}/files/{fid}/preview'
        # el recurso no se subio (o falto en plantilla_recursos/): queda el
        # marcador crudo, que se ve roto en Canvas. Se registra para avisar.
        sin_resolver.add(rel)
        return m.group(0)
    salida = RE_IMS.sub(_sub, html)
    reescribir_tokens_plantilla.sin_resolver = sin_resolver
    return salida


def tokens_a_local(html, prefijo='/plantilla_recursos'):
    """Para la PREVISUALIZACION: $IMS-CC-FILEBASE$/RUTA → ruta local servida
    por Flask desde plantilla_recursos/."""
    return RE_IMS.sub(lambda m: f'{prefijo}/{_up.unquote(m.group(1))}', html)