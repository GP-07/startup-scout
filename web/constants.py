from startups.constants import ContactStatus

STARTUPS_PER_PAGE = 50
RUNS_PER_SOURCE = 20
HTMX_REQUEST_HEADER = "HX-Request"
# Values of the yes/no filters of the startup list.
FILTER_YES = "yes"
FILTER_NO = "no"
YES_NO_CHOICES = [("", "Todas"), (FILTER_YES, "Sí"), (FILTER_NO, "No")]
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
# Contacts in a startup: confirmed first, rejected last; within each, the strongest role first.
CONTACT_STATUS_ORDER = (ContactStatus.CONFIRMED, ContactStatus.CANDIDATE, ContactStatus.REJECTED)
HTMX_SCRIPT_URL = "https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js"
