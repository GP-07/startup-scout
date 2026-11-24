from startups.constants import ContactStatus, OpeningsStatus

STARTUPS_PER_PAGE = 50
RUNS_PER_SOURCE = 20
HTMX_REQUEST_HEADER = "HX-Request"
# Openings filter of the startup list. By default it shows only startups with active openings.
OPENINGS_FILTER_ALL = "all"
OPENINGS_FILTER_DEFAULT = OpeningsStatus.ACTIVE
OPENINGS_FILTER_CHOICES = [
    (OpeningsStatus.ACTIVE, "Con búsquedas activas"),
    (OpeningsStatus.UNVERIFIED, "Señal sin verificar"),
    (OpeningsStatus.NONE, "Sin búsquedas activas"),
    (OpeningsStatus.NOT_CHECKED, "Sin señal"),
    (OPENINGS_FILTER_ALL, "Todas"),
]
CONTACT_FILTER_PERSON = "person"
CONTACT_FILTER_GENERAL = "general"
CONTACT_FILTER_NONE = "none"
CONTACT_FILTER_CHOICES = [
    ("", "Todos"),
    (CONTACT_FILTER_PERSON, "Con CEO, CTO o founder"),
    (CONTACT_FILTER_GENERAL, "Solo mail general"),
    (CONTACT_FILTER_NONE, "Sin contacto"),
]
ANALYSIS_FILTER_NONE = "none"
ANALYSIS_FILTER_DRAFT = "draft"
ANALYSIS_FILTER_SENT = "sent"
ANALYSIS_FILTER_CHOICES = [
    ("", "Todos"),
    (ANALYSIS_FILTER_NONE, "Sin análisis"),
    (ANALYSIS_FILTER_DRAFT, "Solo borradores"),
    (ANALYSIS_FILTER_SENT, "Enviado"),
]
# Time difference from Madrid (startups/locations.py). Unknown countries are kept in the "near"
# options so that no startup is lost for lack of data.
TIMEZONE_FILTER_NEAR = "near"
TIMEZONE_FILTER_NEAR_OR_OPENING = "near_or_opening"
TIMEZONE_FILTER_FAR = "far"
TIMEZONE_FILTER_UNKNOWN = "unknown"
TIMEZONE_FILTER_CHOICES = [
    ("", "Todas"),
    (TIMEZONE_FILTER_NEAR, "Sede a menos de 5 h de Madrid (incluye país desconocido)"),
    (TIMEZONE_FILTER_NEAR_OR_OPENING, "Sede o algún puesto a menos de 5 h (incluye desconocido)"),
    (TIMEZONE_FILTER_FAR, "Sede a 5 h o más"),
    (TIMEZONE_FILTER_UNKNOWN, "País desconocido (sin contar remotos)"),
]
HOURS_DECIMAL_SEPARATOR = ","
MINUS_SIGN = "−"
ORDER_PRIORITY = ""
ORDER_NEWEST = "newest"
ORDER_MOST_OPENINGS = "most_openings"
ORDER_CHOICES = [
    (ORDER_PRIORITY, "Búsqueda más reciente"),
    (ORDER_NEWEST, "Vistas más recientemente"),
    (ORDER_MOST_OPENINGS, "Más búsquedas"),
]
# Openings shown in each row of the list; the detail page shows them all.
OPENINGS_PER_ROW = 3
# Labels of the startup fields merged from the sources, in display order.
MERGED_FIELD_LABELS = (
    ("name", "Nombre"),
    ("website", "Web"),
    ("description", "Descripción"),
    ("country", "País"),
    ("city", "Ciudad"),
)
# Analysis bodies are Markdown: these tags survive sanitizing the rendered HTML.
MARKDOWN_EXTENSIONS = ["extra", "sane_lists"]
INVALID_WEBSITE_MESSAGE = "La URL no tiene un dominio válido."
MISSING_DISCARD_REASON_MESSAGE = "Para descartar hace falta un motivo."
CONTACT_WITHOUT_CHANNEL_MESSAGE = "Cargá al menos un mail o un perfil."
UNKNOWN_COUNTRY_MESSAGE = "Elegí un país de la lista."
# Contacts in a startup: confirmed first, rejected last; within each, the strongest role first.
CONTACT_STATUS_ORDER = (ContactStatus.CONFIRMED, ContactStatus.CANDIDATE, ContactStatus.REJECTED)
STATIC_VERSION_PARAMETER = "v"
HTMX_SCRIPT_URL = "https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js"
