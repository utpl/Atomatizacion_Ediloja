#!/usr/bin/env python3
"""
extraer_canvas.py — Extrae el contenido de un curso Canvas ya virtualizado a JSON canónico.

Uso:
    export CANVAS_TOKEN="tu_token"
    python3 extraer_canvas.py --curso 11078 [--base https://utpl.instructure.com] [--out canvas_11078.json]

Extrae: módulos → items → páginas (HTML completo), quizzes (autoevaluaciones),
assignments (actividades) y discussions. Clasifica cada página por tipo
(contextualización / tema / actividad / autoevaluación / solucionario) según título.

Además de los módulos, extrae TODAS las páginas del curso (/pages), incluidas
las que no pertenecen a ningún módulo: "Autoevaluaciones" (banco de preguntas
con solucionarios que alimenta la generación de la guía), "Datos generales",
anexos y demás. Antes se perdían porque /modules solo devuelve lo que alguien
colocó explícitamente dentro de un módulo.
"""
import argparse, json, os, re, sys, time
import requests

def api(base, token, path, params=None):
    """GET paginado contra la API de Canvas."""
    url = f"{base}/api/v1{path}"
    headers = {"Authorization": f"Bearer {token}"}
    out = []
    params = dict(params or {}, per_page=100)
    while url:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code == 403 and "Rate Limit" in r.text:
            time.sleep(2); continue
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            return data
        out.extend(data)
        url = r.links.get("next", {}).get("url")
        params = None  # el link 'next' ya trae los params
    return out

RE_TEMA = re.compile(r'\b(\d+\.\d+(?:\.\d+)?)\b')
RE_UNIDAD = re.compile(r'\bunidad\s+(\d+)\b', re.I)
RE_SEMANA = re.compile(r'\bsemana\s+(\d+)\b', re.I)

def clasificar(titulo):
    t = titulo.lower()
    if 'autoevaluaci' in t: return 'autoevaluacion'
    if 'solucionario' in t: return 'solucionario'
    if 'contextualizaci' in t or 'resultado' in t and 'aprendizaje' in t: return 'contextualizacion'
    if 'actividad' in t: return 'actividad'
    if 'evaluaci' in t: return 'evaluacion'
    if RE_TEMA.search(titulo): return 'tema'
    return 'otro'

def extraer_curso(base, token, course_id, log=print):
    """Extrae un curso Canvas completo a dict. Reutilizable desde el backend."""
    base = base.rstrip('/')
    curso = api(base, token, f'/courses/{course_id}')
    log(f"📚 {curso.get('name')} ({course_id})")
    modulos = api(base, token, f'/courses/{course_id}/modules', {'include[]': 'items'})
    resultado = {'curso_id': course_id, 'nombre': curso.get('name'),
                 'extraido': time.strftime('%Y-%m-%d %H:%M'), 'modulos': []}
    for m in modulos:
        mod = {'id': m['id'], 'nombre': m['name'], 'posicion': m['position'],
               'semana': (RE_SEMANA.search(m['name']) or [None, None])[1] if RE_SEMANA.search(m['name']) else None,
               'unidad': (RE_UNIDAD.search(m['name']) or [None, None])[1] if RE_UNIDAD.search(m['name']) else None,
               'items': []}
        items = m.get('items') or api(base, token, f'/courses/{course_id}/modules/{m["id"]}/items')
        for it in items:
            item = {'id': it['id'], 'titulo': it['title'], 'tipo_canvas': it['type'],
                    'clasificacion': clasificar(it['title']),
                    'codigo_tema': (RE_TEMA.search(it['title']) or [None, None])[1] if RE_TEMA.search(it['title']) else None}
            try:
                if it['type'] == 'Page':
                    pg = api(base, token, f'/courses/{course_id}/pages/{it["page_url"]}')
                    item['slug'] = it['page_url']; item['html'] = pg.get('body', '')
                elif it['type'] == 'Quiz':
                    qz = api(base, token, f'/courses/{course_id}/quizzes/{it["content_id"]}')
                    item['descripcion_html'] = qz.get('description', '')
                    item['preguntas'] = api(base, token, f'/courses/{course_id}/quizzes/{it["content_id"]}/questions')
                elif it['type'] == 'Assignment':
                    asg = api(base, token, f'/courses/{course_id}/assignments/{it["content_id"]}')
                    item['descripcion_html'] = asg.get('description', ''); item['puntos'] = asg.get('points_possible')
                elif it['type'] == 'Discussion':
                    ds = api(base, token, f'/courses/{course_id}/discussion_topics/{it["content_id"]}')
                    item['descripcion_html'] = ds.get('message', '')
            except requests.HTTPError as e:
                item['error'] = str(e)
            mod['items'].append(item)
            log(f"  ✓ [{item['clasificacion']:<16}] {it['title'][:60]}")
        resultado['modulos'].append(mod)

    # ── páginas SUELTAS enlazadas con el botón/enlace "Continuar" ──
    # En el curso viejo, cuando un tema era muy largo, la continuación se
    # ponía en OTRA página (fuera de los módulos) enlazada con "Continuar".
    # Esas páginas no aparecen en /modules, así que se rastrean desde el HTML
    # y se descargan aparte para que el migrador pueda EMBEBERLAS en el tema
    # (en la plantilla nueva la secuencia sigue de corrido, sin páginas extra).
    vistos = {it.get('slug') for m in resultado['modulos']
              for it in m['items'] if it.get('slug')}
    pendientes = []
    def _slugs_continuar(html):
        out = []
        for mm in re.finditer(r'<p[^>]*>(?:(?!</p>).)*?</p>', html or '', re.S | re.I):
            b = mm.group(0)
            if '/pages/' in b and ('boton-mas' in b or re.search(r'continuar', b, re.I)):
                ms = re.search(r'href="[^"]*/pages/([^"/?#]+)', b, re.I)
                if ms:
                    out.append(ms.group(1).lower())
        return out
    for m in resultado['modulos']:
        for it in m['items']:
            pendientes += _slugs_continuar(it.get('html'))
    enlazadas = {}
    while pendientes:
        slug = pendientes.pop(0)
        if slug in vistos or slug in enlazadas:
            continue
        try:
            pg = api(base, token, f'/courses/{course_id}/pages/{slug}')
            enlazadas[slug] = {'titulo': pg.get('title'), 'html': pg.get('body', '')}
            log(f"  ✓ [pagina-enlazada ] {pg.get('title', slug)[:60]}")
            # la página enlazada puede tener a su vez otro "Continuar"
            pendientes += _slugs_continuar(enlazadas[slug]['html'])
        except requests.HTTPError as e:
            log(f"  ✗ página enlazada {slug}: {e}")
    if enlazadas:
        resultado['paginas_enlazadas'] = enlazadas

    # ── TODAS las páginas del curso, estén o no en un módulo ─────────────
    # /modules solo devuelve lo que alguien colocó dentro de un módulo. Páginas
    # como "Autoevaluaciones" (banco de preguntas con solucionarios, que no ven
    # los estudiantes pero alimenta la generación de la guía), "Datos generales"
    # o los anexos viven en /pages sin pertenecer a ningún módulo: hasta ahora
    # se perdían por completo en la migración.
    sueltas = []
    try:
        indice = api(base, token, f'/courses/{course_id}/pages')
        for p in indice:
            slug = (p.get('url') or '').lower()
            if not slug or slug in vistos or slug in enlazadas:
                continue
            try:
                pg = api(base, token, f'/courses/{course_id}/pages/{slug}')
            except requests.HTTPError as e:
                log(f"  ✗ página suelta {slug}: {e}")
                continue
            cuerpo = pg.get('body') or ''
            if not cuerpo.strip():
                continue
            sueltas.append({'id': p.get('page_id'),
                            'titulo': pg.get('title') or slug,
                            'slug': slug,
                            'html': cuerpo,
                            'clasificacion': clasificar(pg.get('title') or slug),
                            'publicada': bool(p.get('published'))})
            log(f"  ✓ [pagina-suelta   ] {(pg.get('title') or slug)[:60]}")
    except requests.HTTPError as e:
        log(f"  ✗ no se pudo listar /pages: {e}")

    resultado['paginas_sueltas'] = sueltas
    if sueltas:
        log(f"  → {len(sueltas)} página(s) fuera de módulos")
    return resultado


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--curso', required=True, type=int)
    ap.add_argument('--base', default='https://utpl.instructure.com')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    token = os.environ.get('CANVAS_TOKEN')
    if not token:
        sys.exit('❌ Falta CANVAS_TOKEN en el entorno')
    resultado = extraer_curso(args.base, token, args.curso)
    out = args.out or f'canvas_{args.curso}.json'
    json.dump(resultado, open(out, 'w'), ensure_ascii=False, indent=2)
    n = sum(len(m['items']) for m in resultado['modulos'])
    s = len(resultado.get('paginas_sueltas') or [])
    print(f"\n💾 {out} — {len(resultado['modulos'])} módulos, {n} items, {s} páginas sueltas")

if __name__ == '__main__':
    main()
