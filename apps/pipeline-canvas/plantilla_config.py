# -*- coding: utf-8 -*-
"""
plantilla_config.py — Fuente única de verdad para los assets fijos de la
plantilla institucional (theme ed-*).

Dos capas:

1) Los archivos viven en assets/plantilla/ y se suben a Canvas Files con
   canvas_subir_plantilla.py, que genera mapa_plantilla.json:
       nombre_logico -> {"file_id": int, "url": str, "carpeta": str}
   donde nombre_logico = ruta relativa sin 'assets/plantilla/' ni extensión.
   Ej: "iconos/resultado_aprendizaje", "iconos/hover/home", "banners/hero_inicio".

2) Este módulo mapea los ROLES semánticos que el render necesita a esos
   nombres lógicos. El render nunca conoce file_ids: pide un rol, este config
   lo traduce a nombre_logico, y el mapa lo resuelve a file_id/url en el curso.

Así, cambiar un icono = reemplazar el archivo en assets/ + re-subir; agregar un
focalizador = una línea en FOCALIZADORES. El resto del pipeline no se toca.
"""

# ------------------------------------------------------------------
# ROLES DE ICONO usados por el render (rol -> nombre_logico en el mapa)
# ------------------------------------------------------------------
# Página de Inicio
ICONOS_INICIO = {
    "home":                 "iconos/home",
    "vision_general":       "iconos/vision_general",
    "planificacion":        "iconos/planificacion",
    "mentor":               "iconos/mentor",
    "plan_docente":         "iconos/plan_docente",
    "guia_didactica":       "iconos/guia_didactica",
    "carga_horaria":        "iconos/carga_horaria",
    "metodologia":          "iconos/metodologia",
    "metodologia_aprendizaje": "iconos/metodologia_aprendizaje",
    "propositos_aprendizaje":  "iconos/propositos_aprendizaje",
    "datos_informacion":    "iconos/datos_informacion",
    "mail":                 "iconos/mail",
    "phone":                "iconos/phone",
    # Quicknav inferior
    "foro_asesoria_permanente": "iconos/foro_asesoria_permanente",
    "encuentros_en_linea":  "iconos/encuentros_en_linea",
    "calendario_actividades": "iconos/calendario_actividades",
    "fuentes_recursos":     "iconos/fuentes_recursos",
}

# Semana (contenido)
ICONOS_SEMANA = {
    "resultado_aprendizaje": "iconos/resultado_aprendizaje",
    "contextualizacion":     "iconos/contextualizacion",
    "orientaciones_didacticas": "iconos/orientaciones_didacticas",
    "tema":                  "iconos/tema",
    "zona_practica":         "iconos/zona_practica",
    # Tabs de la Zona de Práctica (cada uno tiene versión hover _mo)
    "actividades_recomendadas": "iconos/actividades_recomendadas",
    "autoevaluacion":        "iconos/autoevaluacion",
    "actividad_evaluada":    "iconos/actividad_evaluada",
}

# Banners fijos (encabezados)
BANNERS = {
    "hero_inicio":   "banners/hero_inicio",     # portada de la página Inicio
    "header_semana": "banners/header_semana",   # cabecera de cada semana
}


def hover_de(nombre_logico):
    """Devuelve el nombre lógico de la versión hover (_mo) de un icono, si existe
    en assets/plantilla/iconos/hover/. El render decide si la usa."""
    if nombre_logico.startswith("iconos/"):
        base = nombre_logico.split("/", 1)[1]
        return "iconos/hover/%s" % base
    return None


# ------------------------------------------------------------------
# FOCALIZADORES (callouts dentro del contenido de la semana)
# ------------------------------------------------------------------
# El JSON canónico YA trae el subtipo de cada focalizador (campo "subtipo").
# DI entregó 18 iconos de focalizador (assets/plantilla/focalizadores/*.png),
# uno por cada tipo que la plantilla soporta. Cada curso usa solo algunos:
# Gastronomía Sostenible usa 4 -> reflexione, recuerde, orientacion_actividades,
# apoyo_visual.
#
# CATÁLOGO: los 18 iconos disponibles (nombre lógico -> archivo en el mapa).
# El nombre lógico se normaliza igual que el subtipo del JSON (snake_case, sin
# tildes), así el emparejamiento subtipo->icono es directo salvo excepciones.
FOCALIZADORES_ICONOS = {
    "apuntar":                "focalizadores/apuntar",
    "avancemos":              "focalizadores/avancemos",
    "buscar":                 "focalizadores/buscar",
    "caso":                   "focalizadores/caso",
    "ejemplo":                "focalizadores/ejemplo",
    "ejercicio":              "focalizadores/ejercicio",
    "enlace":                 "focalizadores/enlace",
    "foro":                   "focalizadores/foro",
    "importante":             "focalizadores/importante",
    "informacion_importante": "focalizadores/informacion_importante",
    "lectura":                "focalizadores/lectura",
    "muy_bien":               "focalizadores/muy_bien",
    "nota":                   "focalizadores/nota",
    "observe":                "focalizadores/observe",
    "orientacion_actividades":"focalizadores/orientacion_actividades",
    "recuerde":               "focalizadores/recuerde",
    "reflexione":             "focalizadores/reflexione",
    "video":                  "focalizadores/video",
}

# Overrides: para subtipos cuyo nombre NO coincide con un icono del catálogo,
# o que necesitan una clase CSS distinta de "focuser <subtipo>".
# 'apoyo_visual' (1 uso en Gastronomía) no tiene icono homónimo -> se apunta a
# 'observe' de forma TENTATIVA (confirmar con DI cuál corresponde).
FOCALIZADORES_OVERRIDE = {
    # apoyo_visual no tiene tipo homónimo en el theme; se mapea a 'observe'.
    # La clase inglesa de 'observe' está PENDIENTE con DI; se deja español tentativo.
    "apoyo_visual": {"clase": "focuser observe", "icono": "focalizadores/observe"},  # TENTATIVO
}

# PLANTILLA NUEVA (Rediseño 3): la CLASE CSS del focalizador va en INGLÉS,
# aunque el PNG del icono sigue en español (f_reflexione.png, etc.).
# Confirmado contra semana.html oficial. Solo 4 traducciones vienen en el export;
# el resto queda PENDIENTE con DI (ver auditoría). Mientras tanto, los subtipos
# sin traducción conocida mantienen su nombre español como clase (se ven, solo
# sin el matiz de color exacto del theme).
FOCALIZADOR_CLASE_EN = {
    "reflexione": "reflection",
    "lectura":    "reading",
    "importante": "important",
    "video":      "video",
    # PENDIENTE DI: apuntar, avancemos, buscar, caso, ejemplo, ejercicio, enlace,
    # foro, informacion_importante, muy_bien, nota, observe,
    # orientacion_actividades, recuerde, apoyo_visual.
}


def clase_focuser(subtipo):
    """Traduce el subtipo (español, del JSON) a la clase CSS inglesa del theme
    nuevo. Si no hay traducción conocida, usa el subtipo tal cual (fallback)."""
    ingles = FOCALIZADOR_CLASE_EN.get(subtipo, subtipo)
    return "focuser %s" % ingles


# PENDIENTE CON DI: el nombre EXACTO de la clase CSS de cada focalizador en el
# theme ed-* nuevo (la base solo mostró "focuser important"). Aquí se asume
# "focuser <subtipo>"; ajústese si DI usa otro nombre.
FOCALIZADOR_DEFAULT = "reflexione"


def focalizador_de(subtipo):
    """Resuelve un subtipo de focalizador del JSON a {clase, icono}.
    1) override explícito, 2) icono homónimo del catálogo, 3) default.
    La clase CSS se traduce al inglés del theme nuevo vía clase_focuser()."""
    if subtipo in FOCALIZADORES_OVERRIDE:
        return FOCALIZADORES_OVERRIDE[subtipo]
    if subtipo in FOCALIZADORES_ICONOS:
        return {"clase": clase_focuser(subtipo), "icono": FOCALIZADORES_ICONOS[subtipo]}
    # desconocido -> default
    d = FOCALIZADOR_DEFAULT
    return {"clase": clase_focuser(d), "icono": FOCALIZADORES_ICONOS[d]}


# ------------------------------------------------------------------
# FRASES por defecto (placeholder). Las definitivas las entrega DI.
# ------------------------------------------------------------------
# Umbral en PALABRAS del texto entre el título de unidad y el primer subtema:
#   <= UMBRAL  -> va arriba en #introduction
#   >  UMBRAL  -> arriba va FRASE_INTRO_DEFAULT y el texto largo se mueve a una
#                 pestaña 'Introducción' antes del 1.1
UMBRAL_INTRO_PALABRAS = 40

FRASE_INTRO_DEFAULT = ("Damos inicio al estudio de los temas planificados para la semana. En esta sección se desarrolla el contenido esencial para comprender los conceptos clave. "
                       "Le invitamos a revisar detalladamente el material para avanzar con éxito en su aprendizaje.")

# Frase de cierre, siempre presente antes de la Zona de Práctica (placeholder).
FRASE_FINAL_DEFAULT = ("Con esto concluimos la revisión de los temas de esta semana. "
                       "Recuerde repasar los puntos clave y realizar las actividades sugeridas para consolidar lo aprendido antes de avanzar a la siguiente semana.")

# Límite sugerido para la frase final (palabras). Solo informativo por ahora.
UMBRAL_FINAL_PALABRAS = 25
