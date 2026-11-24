"""The business rules that filter startups and openings, read from where the code keeps them.

The rules page shows them read-only. Nothing here is a copy: the values come from the constants
and the tables the pipeline uses, so the page cannot drift from what actually runs.
"""

from dataclasses import dataclass, field

from sources.constants import DISCARDED_SOURCES, DISCOVERY_HOUR, SOURCE_DESCRIPTIONS
from sources.models import Source
from startups.constants import (
    ANYWHERE_WORDS,
    COUNTRIES_REQUIRING_WORK_AUTHORIZATION,
    COUNTRIES_WITHOUT_WORK_AUTHORIZATION,
    ENGINEERING_ROLE_PHRASES,
    EXCLUDED_TECHNICAL_SPECIALTY_PHRASES,
    FRONTEND_ROLE_PHRASES,
    FULL_STACK_ROLE_PHRASES,
    GENERIC_APPLICATION_PHRASES,
    GENERIC_COUNTRY_DOMAINS,
    LANGUAGE_REQUIREMENT_WORDS,
    MAX_HOURS_FROM_REFERENCE,
    MULTILINGUAL_LANGUAGE,
    NON_IDENTIFYING_DOMAINS,
    NON_SOFTWARE_ENGINEERING_PHRASES,
    OPENINGS_MAX_AGE_DAYS,
    OPENINGS_RECHECK_DAYS,
    OPTIONAL_LANGUAGE_WORDS,
    OTHER_LANGUAGES,
    REFERENCE_TIMEZONE,
    SOFTWARE_ROLE_PHRASES,
    SPONSORSHIP_REFUSAL_WORDS,
    SPONSORSHIP_WORDS,
    WORK_AUTHORIZATION_REQUIREMENTS,
    JobBoardProvider,
    LocationSource,
)
from startups.locations import country_name
from startups.models import BlacklistedDomain


@dataclass(frozen=True)
class RuleGroup:
    """A rule: a label, an explanation and the values it uses (words, countries, domains)."""

    label: str
    text: str = ""
    values: tuple = ()
    # Long lists start folded.
    folded: bool = False


@dataclass(frozen=True)
class RuleSection:
    slug: str
    title: str
    intro: str
    groups: list = field(default_factory=list)


def business_rules():
    """The sections of the rules page, in the order the pipeline applies them."""
    return [
        _sources_section(),
        _openings_section(),
        _roles_section(),
        _languages_section(),
        _countries_section(),
        _location_section(),
        _blacklist_section(),
    ]


def _sources_section():
    sources = [
        RuleGroup(
            label=f"{source.name} · {'activa' if source.enabled else 'deshabilitada'}",
            text=SOURCE_DESCRIPTIONS.get(source.key, ""),
        )
        for source in Source.objects.order_by("name")
    ]
    discarded = [
        RuleGroup(label=f"Descartada: {name}", text=reason) for name, reason in DISCARDED_SOURCES
    ]
    return RuleSection(
        slug="fuentes",
        title="Fuentes de startups",
        intro=(
            "Las fuentes automáticas corren una vez por día desde las "
            f"{DISCOVERY_HOUR}:00 (hora de Madrid). Antes de sumar una fuente se leen su "
            "robots.txt y sus términos de uso."
        ),
        groups=sources + discarded,
    )


def _openings_section():
    return RuleSection(
        slug="busquedas",
        title="Búsquedas activas",
        intro=(
            "Una startup entra a la lista si publica hoy, en su web o en su tablero, al menos un "
            "puesto de los que busco. El resto de los puestos se descarta: no se guarda."
        ),
        groups=[
            RuleGroup(
                label="Antigüedad",
                text=(
                    "Un puesto con fecha cuenta si se publicó en los últimos "
                    f"{OPENINGS_MAX_AGE_DAYS} días; uno sin fecha, mientras siga publicado. Se "
                    "vuelven a verificar cada "
                    f"{OPENINGS_RECHECK_DAYS} días."
                ),
            ),
            RuleGroup(
                label="Tableros leídos por su API oficial",
                values=tuple(label for _, label in JobBoardProvider.choices),
            ),
            RuleGroup(
                label="Postulaciones genéricas que no son un puesto",
                values=GENERIC_APPLICATION_PHRASES,
            ),
        ],
    )


def _roles_section():
    return RuleSection(
        slug="puestos",
        title="Puestos que busco",
        intro=(
            "Se decide por el título, comparando palabras enteras sin mayúsculas ni tildes. "
            "Las palabras de seniority solas (Senior, Lead, Staff) no hacen técnico un puesto."
        ),
        groups=[
            RuleGroup(
                label="1. Se descartan siempre estas especialidades",
                text="Aunque el título tenga una palabra de software.",
                values=EXCLUDED_TECHNICAL_SPECIALTY_PHRASES,
            ),
            RuleGroup(
                label="2. Frontend puro",
                text=(
                    "Un título con una de estas palabras se descarta, salvo que también diga: "
                    + ", ".join(FULL_STACK_ROLE_PHRASES)
                    + "."
                ),
                values=FRONTEND_ROLE_PHRASES,
            ),
            RuleGroup(
                label="3. Palabras de software: alcanzan solas",
                values=SOFTWARE_ROLE_PHRASES,
            ),
            RuleGroup(
                label="4. Palabras genéricas de ingeniería",
                text="Cuentan salvo que el título nombre otra disciplina o rol (lista siguiente).",
                values=ENGINEERING_ROLE_PHRASES,
            ),
            RuleGroup(
                label="Otras disciplinas o roles que solo llevan la palabra",
                values=NON_SOFTWARE_ENGINEERING_PHRASES,
            ),
        ],
    )


def _languages_section():
    return RuleSection(
        slug="idiomas",
        title="Idiomas",
        intro=(
            "Se descarta un puesto que pide un idioma además del inglés y el español: si lo nombra "
            "el título, o una oración de la descripción lo nombra junto con una palabra de "
            "requisito y sin una de opcional."
        ),
        groups=[
            RuleGroup(
                label="Otros idiomas",
                values=tuple(name for name, _ in OTHER_LANGUAGES) + (MULTILINGUAL_LANGUAGE,),
            ),
            RuleGroup(label="Palabras de requisito", values=LANGUAGE_REQUIREMENT_WORDS),
            RuleGroup(label="Palabras que lo hacen opcional", values=OPTIONAL_LANGUAGE_WORDS),
        ],
    )


def _countries_section():
    return RuleSection(
        slug="paises",
        title="Dónde puedo trabajar",
        intro=(
            "Ciudadanía italiana y residencia española. El lugar de un puesto sale de su "
            "ubicación, del país que da el tablero, de un país en el título o, si no dice nada, "
            "de la sede de la startup. Si también nombra un lugar donde puedo trabajar o una "
            "región, se conserva."
        ),
        groups=[
            RuleGroup(
                label="Se descartan siempre los puestos solo en",
                values=_country_names(COUNTRIES_REQUIRING_WORK_AUTHORIZATION),
            ),
            RuleGroup(
                label="Sin visa (UE, EEE y Suiza)",
                text=(
                    "Fuera de estos países, un puesto se descarta solo si su descripción dice que "
                    "no patrocina visas o exige autorización para trabajar allí."
                ),
                values=_country_names(COUNTRIES_WITHOUT_WORK_AUTHORIZATION),
                folded=True,
            ),
            RuleGroup(
                label="No patrocina: una oración con una de estas palabras…",
                values=SPONSORSHIP_WORDS,
            ),
            RuleGroup(label="…y una negación", values=SPONSORSHIP_REFUSAL_WORDS),
            RuleGroup(
                label="Exige autorización para trabajar", values=WORK_AUTHORIZATION_REQUIREMENTS
            ),
            RuleGroup(
                label="Abierto desde cualquier lugar",
                text="Un puesto sin lugar que dice esto no toma el país de la sede.",
                values=ANYWHERE_WORDS,
            ),
        ],
    )


def _location_section():
    return RuleSection(
        slug="ubicacion",
        title="Sede y diferencia horaria",
        intro=(
            f"La diferencia se mide contra {REFERENCE_TIMEZONE}, hoy, con el horario de verano de "
            f'ambos lados. El filtro "cerca" es menos de {MAX_HOURS_FROM_REFERENCE} h e incluye '
            "el país desconocido y las startups solo remotas. Ante varios candidatos, gana el más "
            "cercano a Madrid."
        ),
        groups=[
            RuleGroup(
                label="De dónde sale la sede, por prioridad",
                values=tuple(label for _, label in LocationSource.choices),
            ),
            RuleGroup(
                label="Dominios de país que no indican país",
                values=tuple(f".{domain}" for domain in sorted(GENERIC_COUNTRY_DOMAINS)),
            ),
        ],
    )


def _blacklist_section():
    entries = BlacklistedDomain.objects.order_by("domain")
    return RuleSection(
        slug="lista-negra",
        title="Lista negra y plataformas",
        intro=(
            "Sitios que no son startups. Una startup en la lista negra queda descartada y no se "
            "vuelve a inspeccionar; si una fuente la trae de nuevo, entra descartada. Se agrega "
            "desde su ficha."
        ),
        groups=[
            RuleGroup(
                label="Lista negra",
                text="" if entries else "Vacía.",
                values=tuple(f"{entry.domain} · {entry.reason}" for entry in entries),
            ),
            RuleGroup(
                label="Plataformas que no identifican a una startup",
                text="Un link a estos dominios no es la web de la startup.",
                values=tuple(sorted(NON_IDENTIFYING_DOMAINS)),
                folded=True,
            ),
        ],
    )


def _country_names(codes):
    return tuple(sorted(f"{country_name(code)} ({code})" for code in codes))
