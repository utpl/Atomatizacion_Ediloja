#!/usr/bin/env python3
"""
renumerar.py — Re-enumeración de FIGURAS y TABLAS tras eliminar/agregar/
reubicar contenido, corrigiendo también las referencias dentro del texto
("fíjese en la figura 7", "ver tabla 3", "en la Figura 12 se observa…").

La numeración del curso es GLOBAL (continúa entre semanas), por eso se
renumera el curso completo en el orden final de las páginas:

    paginas, reporte = renumerar_curso(["<html semana 1>", "<html semana 2>", ...])

Estrategia en dos pasadas para evitar colisiones en cadena (7→6 y luego 6→5):
  1ª pasada: cada "Figura N" / "Tabla N" (en captions y en texto) se
             sustituye por un marcador único ⟦FIG:N⟧ / ⟦TAB:N⟧.
  2ª pasada: los marcadores se resuelven con el número nuevo según el
             orden real de aparición de los captions.
Las referencias a números que ya no existen (el elemento fue eliminado)
se marcan con <span data-ia="referencia-rota" ...> para que el agente IA
o el revisor las resuelva.
"""
import re

MARK_FIG = '\u27e6FIG:{}\u27e7'   # ⟦FIG:n⟧
MARK_TAB = '\u27e6TAB:{}\u27e7'

# captions: <figcaption>…Figura 7…</figcaption> / <caption>…Tabla 3…</caption>
RE_CAP_FIG = re.compile(r'(<figcaption\b[^>]*>.*?)(Figura)(\s|&nbsp;|<[^>]+>)*?(\d+)',
                        re.S | re.I)
RE_CAP_TAB = re.compile(r'(<caption\b[^>]*>.*?)(Tabla)(\s|&nbsp;|<[^>]+>)*?(\d+)',
                        re.S | re.I)
# referencias en el texto (fuera de captions, la 1ª pasada ya las cubrió)
RE_TXT_FIG = re.compile(r'\b(figura|fig\.?)(\s|&nbsp;)+(\d+)\b', re.I)
RE_TXT_TAB = re.compile(r'\b(tabla)(\s|&nbsp;)+(\d+)\b', re.I)


def _marcar(html):
    """1ª pasada: números de figuras/tablas → marcadores; devuelve el orden
    real de aparición de captions (para asignar la numeración nueva)."""
    orden_fig, orden_tab = [], []

    def cap_fig(m):
        orden_fig.append(int(m.group(4)))
        sep = m.group(0)[len(m.group(1)) + len(m.group(2)):-len(m.group(4))]
        return m.group(1) + m.group(2) + sep + MARK_FIG.format(m.group(4)) + '\u27e8CAP\u27e9'

    def cap_tab(m):
        orden_tab.append(int(m.group(4)))
        sep = m.group(0)[len(m.group(1)) + len(m.group(2)):-len(m.group(4))]
        return m.group(1) + m.group(2) + sep + MARK_TAB.format(m.group(4)) + '\u27e8CAP\u27e9'

    html = RE_CAP_FIG.sub(cap_fig, html)
    html = RE_CAP_TAB.sub(cap_tab, html)
    html = RE_TXT_FIG.sub(lambda m: m.group(1) + m.group(2) + MARK_FIG.format(m.group(3)), html)
    html = RE_TXT_TAB.sub(lambda m: m.group(1) + m.group(2) + MARK_TAB.format(m.group(3)), html)
    return html, orden_fig, orden_tab


def _resolver(html, mapa_fig, mapa_tab):
    """2ª pasada: marcadores → número nuevo (o marca de referencia rota)."""
    rotas = []

    def fig(m):
        viejo = int(m.group(1))
        if viejo in mapa_fig:
            return str(mapa_fig[viejo])
        rotas.append(('figura', viejo))
        return (f'<span data-ia="referencia-rota" data-tipo="figura" data-num="{viejo}" '
                f'style="background:#ffe3e3">{viejo}</span>')

    def tab(m):
        viejo = int(m.group(1))
        if viejo in mapa_tab:
            return str(mapa_tab[viejo])
        rotas.append(('tabla', viejo))
        return (f'<span data-ia="referencia-rota" data-tipo="tabla" data-num="{viejo}" '
                f'style="background:#ffe3e3">{viejo}</span>')

    html = re.sub(r'\u27e6FIG:(\d+)\u27e7', fig, html)
    html = re.sub(r'\u27e6TAB:(\d+)\u27e7', tab, html)
    html = html.replace('\u27e8CAP\u27e9', '')
    return html, rotas


def renumerar_curso(paginas_html):
    """Renumera figuras y tablas de forma GLOBAL en el orden de las páginas.
    Devuelve (paginas_nuevas, reporte) donde reporte incluye los mapas
    viejo→nuevo y las referencias rotas encontradas."""
    marcadas, orden_fig, orden_tab = [], [], []
    for html in paginas_html:
        h, of, ot = _marcar(html)
        marcadas.append(h)
        orden_fig.extend(of)
        orden_tab.extend(ot)

    # numeración nueva según orden real de aparición de captions;
    # si un número viejo aparece dos veces (raro), gana la primera aparición
    mapa_fig, mapa_tab = {}, {}
    for i, viejo in enumerate(orden_fig, 1):
        mapa_fig.setdefault(viejo, i)
    for i, viejo in enumerate(orden_tab, 1):
        mapa_tab.setdefault(viejo, i)

    nuevas, rotas_todas = [], []
    for i, h in enumerate(marcadas):
        nueva, rotas = _resolver(h, mapa_fig, mapa_tab)
        nuevas.append(nueva)
        rotas_todas.extend({'pagina': i, 'tipo': t, 'numero': n} for t, n in rotas)

    reporte = {
        'figuras': {str(k): v for k, v in sorted(mapa_fig.items()) if k != v},
        'tablas': {str(k): v for k, v in sorted(mapa_tab.items()) if k != v},
        'total_figuras': len(orden_fig),
        'total_tablas': len(orden_tab),
        'referencias_rotas': rotas_todas,
    }
    return nuevas, reporte
