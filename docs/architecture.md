# Arquitectura de startup-scout

Este documento explica qué hace cada parte del código y cómo fluye una startup por el sistema, desde que una fuente la publica hasta que la contacto. Describe el estado al cierre de la **fase 3**. Lo que todavía no existe está marcado como _pendiente_, con la fase en la que llega según el [plan del MVP](startup-scout-design.md#10-plan-del-mvp).

## 1. Vista general

startup-scout tiene una sola responsabilidad: **mantener una lista de startups sin duplicados y con historial**, alimentada por varias fuentes, para que yo las revise y contacte a mano.

El código se organiza en dos apps de Django con responsabilidades separadas:

| App | Responsabilidad | Sabe de… | No sabe de… |
|---|---|---|---|
| `sources` | **De dónde vienen los datos.** Qué fuentes existen, cómo leer cada una y qué reportó cada una | Fuentes, adaptadores, corridas, registros crudos | Cómo se identifica o se fusiona una startup |
| `startups` | **Qué es una startup para nosotros.** Identidad, deduplicación, merge, contactos, análisis y estados | Startups, dominios, merge, ingesta | Cómo se lee cada fuente en particular |

El contrato entre las dos es el dataclass `RawStartup`. Cada adaptador traduce su fuente a `RawStartup`, y la ingesta solo conoce ese formato. Agregar una fuente no toca nada de `startups`.

```
startup-scout/
├── config/                 Settings, URLs y WSGI de Django
├── sources/                App de fuentes
│   ├── adapters/
│   │   ├── base.py         Puerto SourceAdapter + RawStartup + SourceFetchResult
│   │   ├── algolia.py      Lectura paginada de la API de Algolia, compartida por los dos de HN
│   │   ├── html_text.py    Texto plano, links y dominio propio de los HTML de HN
│   │   ├── hacker_news.py  HackerNewsAdapter: Show HN y Launch HN
│   │   ├── hacker_news_hiring.py  HackerNewsHiringAdapter: "Ask HN: Who is hiring?"
│   │   └── manual.py       ManualSourceAdapter (alta manual por URL)
│   ├── registry.py         Mapeo en memoria: clave de fuente → adaptador
│   ├── runner.py           SourceRunner: corre una fuente y registra la corrida
│   ├── tasks.py            Tareas de huey: descubrimiento diario y una tarea por fuente
│   ├── management/commands/run_source.py   Correr una fuente a mano
│   ├── models.py           Source, SourceRecord, SourceRun
│   ├── constants.py        SourceKey, SourceRunStatus, parámetros de HN y del scheduler
│   ├── exceptions.py       UnknownSourceError, SourceFetchError
│   ├── migrations/         Esquema, alta de las fuentes y baja de Startupxplore
│   └── tests/              Incluye fixtures/ con respuestas ficticias de Algolia
├── startups/               App de startups
│   ├── domains.py          Normalización de dominios y de nombres
│   ├── redirects.py        Resolución de redirects (HttpRedirectResolver)
│   ├── merge.py            Merge de campos por prioridad de fuente
│   ├── ingestion.py        StartupIngestionService: dedupe + merge + concurrencia
│   ├── querysets.py        StartupQuerySet.with_hiring_signal(): señal por web o por aviso
│   ├── hiring_signal.py    Detección de búsquedas abiertas en un HTML (funciones puras)
│   ├── page_metrics.py     Métricas de la home y regla de "probable SPA vacía"
│   ├── inspection_stats.py Cuántas inspecciones sin señal son probables SPA vacías
│   ├── website_inspection.py  WebsiteInspectionService: visita la web, robots.txt, fallback
│   ├── tasks.py            Tarea de huey que inspecciona la web de una startup
│   ├── domain_cleanup.py   Saca de las startups los dominios que hoy se consideran plataformas
│   ├── management/commands/inspect_websites.py        Inspeccionar las startups existentes
│   ├── management/commands/prune_platform_domains.py  Aplicar domain_cleanup a lo ya cargado
│   ├── models.py           Startup, StartupDomain, WebsiteInspection, Contact, Analysis, StatusChange
│   ├── constants.py        Estados, roles, prioridades, patrones y límites
│   ├── exceptions.py       InvalidWebsiteError, IngestionConflictError
│   ├── migrations/
│   └── tests/
└── docs/
```

## 2. App `sources`

### 2.1 `Source` (modelo)

Una fila por fuente configurada: hoy `hacker_news` y `manual`. Las crea la data migration `0002_seed_initial_sources`. Esa migración también creaba `startupxplore`, y la `0003_remove_startupxplore` la borra (ver §5.3).

| Campo | Para qué |
|---|---|
| `key` | Clave estable y única (`SourceKey`). Es lo único que conecta la fila con el código |
| `name` | Nombre visible en la web |
| `enabled` | Permite apagar una fuente sin borrarla |
| `config` | Parámetros del adaptador en JSON. Por ejemplo, HN usa `{"tags": ["show_hn", "launch_hn"]}` |

**Decisión: en la base nunca se guarda el nombre de una clase.** La `key` se resuelve a un adaptador con un mapeo en memoria (ver 2.5). Así se puede renombrar o mover un adaptador sin tocar los datos, y la base no queda atada a la estructura del código.

### 2.2 `SourceRecord` (modelo)

**Lo que una fuente dijo sobre una startup.** Si una startup aparece en HN y además la cargo a mano, tiene dos `SourceRecord`.

| Campo | Para qué |
|---|---|
| `source`, `external_id` | Identifican el registro dentro de su fuente: el id del post de HN o la URL normalizada en el alta manual. **Únicos juntos**, así una fuente no puede cargar dos veces lo mismo |
| `startup` | A qué startup unificada pertenece |
| `data` | Los campos ya traducidos a nuestro formato (`name`, `website`, `description`, `country`, `city`). **De acá se recalcula el merge** |
| `payload` | La respuesta cruda de la fuente, tal cual llegó. Sirve para depurar y para reprocesar si cambia el mapeo |
| `url` | Link a la startup en la fuente |
| `published_at` | Cuándo lo publicó la fuente (el post o el comentario de HN), si la fuente lo informa. Sirve para saber si un aviso de "Who is hiring?" es reciente |
| `first_seen_at`, `fetched_at` | Cuándo apareció por primera vez y cuándo se actualizó por última vez |

Guardar los registros por separado, en vez de pisar los datos de la startup, es lo que hace el merge **recalculable**: si cambia la prioridad de las fuentes, se recalcula y listo.

### 2.3 `SourceRun` (modelo)

Una fila por cada vez que corre una fuente: estado (`running`, `succeeded`, `failed`), cuántos ítems vio, cuántos eran nuevos, el error si lo hubo y un `cursor` en JSON para retomar desde donde quedó. Por ejemplo, el último `created_at_i` visto en HN. La corrida siguiente arranca del cursor de la **última corrida exitosa**; una corrida fallida no lo mueve. Sirve como historial y como observabilidad de cada fuente.

### 2.4 `RawStartup` y `SourceAdapter` (`adapters/base.py`)

- **`RawStartup`**: dataclass inmutable con lo que reporta una fuente, ya mapeado a nuestros nombres de campo. `country` llega como código ISO 3166-1 alfa-2 (`ES`), y la conversión es responsabilidad del adaptador. `published_at` es la fecha de publicación en la fuente, opcional. `mergeable_data()` devuelve los campos que entran al merge.
- **`SourceFetchResult`**: lo que devuelve una corrida de un adaptador: la lista de `RawStartup` y el `cursor` desde el que tiene que arrancar la próxima.
- **`SourceAdapter`**: el puerto (ports & adapters). Cada fuente implementa `fetch_candidates(cursor)`, que recibe `{}` en la primera corrida, y devuelve un `SourceFetchResult`. Recibe su `config` desde la fila `Source` y, opcionalmente, un `httpx.Client`; si no se le pasa, lo crea recién cuando lo necesita. En los tests se le inyecta uno con `MockTransport`. `runs_periodically` indica si el descubrimiento diario la corre. Un adaptador solo sabe leer su fuente: no deduplica ni guarda nada. Si no puede leerla, lanza `SourceFetchError`.

### 2.5 `registry.py`

`SOURCE_ADAPTERS` es un diccionario en memoria de `key` a clase de adaptador: hoy `hacker_news → HackerNewsAdapter`, `hacker_news_hiring → HackerNewsHiringAdapter` y `manual → ManualSourceAdapter`. `get_adapter(source)` busca la clave de la fila y devuelve el adaptador instanciado con su `config`. Si la clave no tiene adaptador, lanza `UnknownSourceError`. `runs_periodically(source)` dice si la fuente entra en el descubrimiento diario. Un test verifica que toda fuente habilitada tenga adaptador.

### 2.6 `HackerNewsAdapter` (`adapters/hacker_news.py`)

Lee posts de la API pública de Algolia (`search_by_date`), sin autenticación.

- **Qué trae**: los `tags` de su `config`, que hoy son `show_hn` y `launch_hn`. "Show HN" es un tag de Algolia. "Launch HN" (startups de YC) no lo es: se busca como texto en `story` y después se filtra por título, porque la búsqueda también trae posts que solo lo mencionan.
- **Cursor**: el `created_at_i` del post más nuevo visto, incluidos los descartados por título. Cada corrida vuelve a leer una hora antes del cursor (`HACKER_NEWS_CURSOR_OVERLAP_SECONDS`), porque Algolia a veces indexa tarde. Repetir posts no duplica nada: se vuelven a ingresar como actualización. Sin cursor, arranca `HACKER_NEWS_INITIAL_LOOKBACK_DAYS` días atrás (7, configurable con `initial_lookback_days`).
- **Paginación**: de a 100 posts por página, hasta `nbPages`.
- **Mapeo a `RawStartup`**:
  - `external_id` es el `objectID` del post, y `url` es el link al post en HN.
  - `name` es el título sin el prefijo, hasta el primer separador (` – `, ` — `, ` - `, `, ` o `: `) y sin el batch de YC (`(YC F26)`). Si el título no tiene separador, el nombre es el título completo, y eso pasa bastante en Show HN.
  - `description` es la frase después del separador. Si no hay, se usa el texto del post en texto plano, hasta 500 caracteres.
  - `website` es el link del post si es un dominio propio. Si es una plataforma (GitHub, App Store, YouTube…), se usa el primer dominio propio que aparezca linkeado en el texto. Si no hay ninguno, se deja el link a la plataforma, que no identifica a la startup (ver §3.6).
  - `raw_payload` es el hit completo, sin `_highlightResult`. Incluye `author`, que en la fase 4 será el candidato a contacto.

### 2.7 `HackerNewsHiringAdapter` (`adapters/hacker_news_hiring.py`)

Lee los avisos del hilo mensual "Ask HN: Who is hiring?", que publica el usuario `whoishiring`. Cada comentario de primer nivel es una empresa que está contratando. Las reglas y su porqué están en el [diseño §2](startup-scout-design.md#hn-who-is-hiring).

- **Hilos**: busca en Algolia los posts de `whoishiring` de los últimos 45 días (`HACKER_NEWS_HIRING_THREAD_MAX_AGE_DAYS`) cuyo título empieza con "Ask HN: Who is hiring?". Así quedan afuera "Who wants to be hired?" y "Freelancer?". La primera corrida lee solo el hilo más nuevo (`initial_threads` en el `config`).
- **Comentarios**: `tags=comment,story_<id>`, quedándose con los que tienen `parent_id` igual al hilo.
- **Cursor**: el `created_at_i` del comentario más nuevo, con la misma hora de solapamiento que §2.6. Mientras un hilo tenga menos de 45 días se sigue leyendo, así los avisos que llegan a mitad de mes no se pierden.
- **Mapeo a `RawStartup`**: `name` sale del primer segmento del encabezado sin paréntesis; `description` es el encabezado completo; `website` sigue el orden coincidencia con el nombre → link en el encabezado → dominio de un mail que no sea de un proveedor de correo (`FREE_EMAIL_DOMAINS`); `published_at` es la fecha del comentario y `raw_payload` el comentario entero, con su `author`. Si no hay encabezado o no hay web propia, el aviso se descarta y se cuenta en el log.

`algolia.py` y `html_text.py` tienen lo que comparten los dos adaptadores de HN: la paginación de Algolia (que lanza `SourceFetchError` si la API falla), el texto plano, los links y `identifying_domain(url)`.

### 2.8 `ManualSourceAdapter` (`adapters/manual.py`)

No corre periódicamente: su `fetch_candidates` no trae nada. Expone `build_raw_startup(website, name="")`, que va a usar el formulario de alta manual de la web (fase 5):

- `external_id` es la URL normalizada (`acme.com/pricing`), así pegar dos veces el mismo sitio actualiza el mismo registro.
- Si no se da un nombre, usa el del dominio (`acme.com` → `Acme`).
- Si la URL no tiene dominio registrable, lanza `InvalidWebsiteError`.

### 2.9 `SourceRunner` (`runner.py`)

Corre una fuente de punta a punta:

1. Crea un `SourceRun` en `running`.
2. Toma el cursor de la última corrida exitosa.
3. Pide los candidatos al adaptador. Si falla (`SourceFetchError` o `UnknownSourceError`), cierra la corrida en `failed` con el error, y el cursor no se mueve.
4. Ingresa cada `RawStartup` con `StartupIngestionService`. Si una startup falla, el error queda anotado en `error` y la corrida sigue con las demás.
5. Por cada startup **creada**, llama a `on_startup_created`. Por defecto es `enqueue_website_inspection`, que encola la inspección de su web (§3.11). Es un parámetro para que los tests del runner no salgan a la red.
6. Guarda `items_seen`, `items_new` (startups **creadas**, no registros) y el cursor nuevo, y cierra en `succeeded`.

### 2.10 Tareas y comando (`tasks.py`, `run_source`)

- **`run_enabled_sources_task`**: tarea periódica de huey, todos los días a las 7:00 hora de Madrid (`DISCOVERY_HOUR`). Encola una `run_source_task` por cada fuente habilitada con `runs_periodically`, así una fuente que falla no frena a las otras.
- **`run_source_task(source_id)`**: corre `SourceRunner` dentro de un lock de huey (`source-run-<key>`), para que dos corridas de la misma fuente no lean el mismo cursor a la vez. Si ya hay una corriendo, la nueva se saltea.
- **`python manage.py run_source <key>`**: corre una fuente en el momento, fuera del horario. Sirve para probar o para forzar una corrida.

## 3. App `startups`

### 3.1 `Startup` (modelo)

La startup **unificada**: una sola fila por startup real, venga de las fuentes que venga.

| Campo | Para qué |
|---|---|
| `name`, `website`, `description`, `country`, `city` | Valores **calculados por el merge** a partir de los `SourceRecord`. No se editan directo: una edición manual será un registro de la fuente `manual`, que tiene la prioridad más alta |
| `field_sources` | De qué fuente salió cada campo, por ejemplo `{"name": "manual", "description": "hacker_news"}` |
| `normalized_name` | Nombre comparable (sin tildes, puntuación ni "S.L."/"Inc."). Indexado, se usa para detectar posibles duplicados |
| `possible_duplicate_of` | Si se sospecha que es la misma que otra startup. **Nunca se fusionan solas**: lo confirmo yo desde la web (fase 5) |
| `status` | En qué punto del proceso está (ver §5.5) |
| `discard_reason` | Por qué la descarté (por ahora, solo descarte manual) |
| `remote_policy` | `unknown`, `remote`, `hybrid` u `onsite`. Se carga a mano; la regla de ubicación que lo usaría quedó como mejora futura |
| `first_seen_at` | Cuándo la descubrimos. El listado ordena por este campo, de la más nueva a la más vieja |

### 3.2 `StartupDomain` (modelo)

**La identidad de la startup.** Cada startup tiene uno o más dominios normalizados y uno de ellos es el principal (`is_primary`). Los demás son alias, por ejemplo el dominio desde el que redirige su web. `domain` es **único en toda la tabla**: es el constraint que garantiza que no haya dos startups con el mismo dominio, incluso con ingestas concurrentes.

### 3.3 `Contact` (modelo)

Personas o canales para contactar a la startup: CEO, CTO, founder, otro cargo o un contacto general como `hello@`. Registra cómo se encontró (`found_via`: la fuente, la web de la startup o carga manual), la URL donde aparece (`evidence_url`) y su estado (`candidate`, `confirmed` o `rejected`). Los candidatos se confirman a mano. _El modelo existe; la extracción desde la web de la startup llega en la fase 4._

### 3.4 `Analysis` (modelo)

Mis análisis de una startup, en markdown. Puede haber varios por startup. "Enviado" significa `sent_at` no nulo (propiedad `is_sent`); `sent_to` apunta al contacto al que se lo mandé. _El modelo existe; el CRUD en la web llega en la fase 5._

### 3.5 `StatusChange` (modelo)

El historial de cambios de estado de cada startup: estado anterior, estado nuevo, una nota y la fecha. Lo escriben los cambios manuales y el paso automático a `contacted` al marcar un análisis como enviado. _Se empieza a escribir en la fase 5._

### 3.6 `domains.py`

- **`normalize_domain(website)`**: de cualquier URL o host obtiene su **dominio registrable**. Ejemplos: `https://www.Acme.com/pricing` → `acme.com`, `app.acme.com` → `acme.com`, `www.müller.de` → `xn--mller-kva.de`.
  - Usa la Public Suffix List **con los sufijos privados**, así `foo.vercel.app` y `bar.vercel.app` siguen siendo distintos.
  - La lista viene incluida en `tldextract`: no hay acceso a red ni caché en disco, y el resultado es determinístico.
  - **Hosts compartidos** que no están en la Public Suffix List (`substack.com`, `medium.com`, `itch.io`, `gitbook.io`, `wordpress.com`, etc.: `SHARED_HOST_DOMAINS`): se conserva el subdominio, así `acme.substack.com` identifica a Acme.
  - Si el valor no tiene un dominio registrable (vacío, IP, `localhost` o texto que no es una URL), lanza `InvalidWebsiteError`.
- **`is_identifying_domain(domain)`**: dice si un dominio identifica a **una** startup. Es falso para las plataformas donde el link apunta a contenido adentro (`github.com`, `apple.com`, `google.com`, `youtube.com`, `x.com`, `producthunt.com`, y marketplaces como `plugins.jetbrains.com`, `marketplace.visualstudio.com` o `vercel.com/templates`…, en `NON_IDENTIFYING_DOMAINS`) y para un host compartido sin subdominio. Sin esto, todos los Show HN que linkean a GitHub terminarían fusionados en una sola startup llamada `github.com`.
- **`normalize_url(website)`**: forma comparable de una URL completa: host sin `www.`, más el path (`acme.com/pricing`). La usa el alta manual como `external_id`.
- **`normalize_name(name)`**: forma comparable de un nombre. `"Ácme, S.L.U."` → `"acme"`. Saca tildes, puntuación, mayúsculas y sufijos legales del final (la lista está en `LEGAL_NAME_SUFFIXES`), pero deja siempre al menos una palabra.

### 3.7 `redirects.py`

`HttpRedirectResolver.resolve_final_url(url)` sigue los redirects de un sitio y devuelve la URL final, o `None` si el sitio no responde. Primero prueba con `HEAD`; si el servidor lo rechaza (403, 405, 501), reintenta con `GET` en streaming, sin descargar el cuerpo. Es una dependencia inyectable: en los tests se reemplaza por `FakeRedirectResolver`, sin red.

### 3.8 `merge.py`

- **`merge_source_data(records)`**: función pura. Recibe pares `(source_key, data)` y, **campo por campo**, se queda con el primer valor no vacío según `SOURCE_MERGE_PRIORITY` (`manual > hacker_news`). Las fuentes que no están en la lista van al final. Devuelve los valores y la procedencia de cada uno.
- **`recompute_startup(startup)`**: lee todos los `SourceRecord` de la startup, aplica el merge y guarda los campos, `normalized_name` y `field_sources`. Es idempotente: correrlo dos veces da lo mismo.

### 3.9 `ingestion.py`: `StartupIngestionService`

El corazón de la fase 1. `ingest(source, raw_startup)` convierte lo que reporta una fuente en una startup única, y devuelve un `IngestionResult(startup, created, record_created)`. El paso a paso está en §5.2.

### 3.10 `WebsiteInspection` (modelo)

El resultado de visitar la web propia de una startup. Hay uno por startup (`OneToOneField`, `startup.website_inspection`), y hoy responde una sola pregunta: **¿muestra búsquedas abiertas?**

| Campo | Para qué |
|---|---|
| `status` | `pending` (encolada), `done`, `blocked` (robots.txt no lo permite) o `failed` (no responde o devuelve error) |
| `inspected_at` | Cuándo se inspeccionó por última vez |
| `has_hiring_signal` | Si se encontró la señal. Indexado: el listado ordena por este campo |
| `hiring_signal_method` | `home` (estaba en la home) o `path_probe` (salió del fallback por rutas típicas) |
| `hiring_signal_kind` | Qué tipo de señal fue, de más fuerte a más débil: `job_board`, `link_path`, `link_text`, `email` o `phrase` |
| `hiring_signal_url`, `hiring_signal_text` | La evidencia: a dónde apuntaba y qué decía. Sirve para revisar falsos positivos |
| `home_text_length`, `home_link_count`, `home_has_app_root` | Lo que muestra la home sin JavaScript: largo del texto visible, cantidad de links y si tiene un contenedor de framework. Nulos si la home no se pudo leer. Sirven para medir las SPA vacías (§3.12) |
| `error` | El error, si la inspección falló |

En la fase 4 este mismo modelo va a sumar los contactos encontrados en la misma visita.

### 3.11 Búsquedas abiertas: `hiring_signal.py`, `website_inspection.py` y `tasks.py`

- **`hiring_signal.py`**: funciones **puras**, sin red ni base. `detect_hiring_signal(html, page_url)` devuelve la señal **más fuerte** de la página, o `None`. Recorre todos los links (nav, cuerpo y footer: es el mismo HTML) y el texto visible, sin scripts ni estilos:
  - `job_board`: links a plataformas de búsqueda (`JOB_BOARD_DOMAINS`: Greenhouse, Lever, Ashby, Workable…) o a la sección `/jobs` de LinkedIn, Wellfound o YC.
  - `link_path`: links **del mismo sitio** cuyo path tiene un segmento de búsqueda (`/careers`, `/jobs`, `/join-us`, `/empleo`…, en `HIRING_PATH_PATTERN`).
  - `link_text`: texto de link como "Careers" o "Jobs" (palabra sola y completa) o una frase como "Work with us" o "Trabaja con nosotros".
  - `email`: un `mailto:` a `jobs@`, `careers@`, `talent@`, etc.
  - `phrase`: frases en el texto visible como "We're hiring" o "Estamos contratando".

  Los links de `link_path` no cuentan si están bajo una sección de documentación o similar (`/docs`, `/api`, `/blog`, `/help`…, en `HIRING_PATH_EXCLUDED_SECTIONS`): `/docs/applications/jobs` habla de tareas programadas, no de búsquedas. "Join us" a secas no cuenta, salvo que el link vaya a una ruta de búsqueda. Los textos se comparan normalizados (`normalize_text`: minúsculas, sin tildes, la puntuación como espacios) y por palabra completa, así "Steve Jobs" no dispara nada.
- **`WebsiteInspectionService.inspect(startup)`**: hace la visita (§5.4) y guarda el `WebsiteInspection`. Si la startup no tiene dominio propio (por ejemplo, solo un link a GitHub), devuelve `None` y no guarda nada.
- **`enqueue_website_inspection(startup)`**: marca la inspección como `pending` y encola `inspect_website_task` en huey. La usa el runner al crear una startup.
- **`python manage.py prune_platform_domains`** (`domain_cleanup.py`): cuando se agrega una plataforma a `NON_IDENTIFYING_DOMAINS` o a `SHARED_HOST_DOMAINS`, las startups cargadas antes siguen teniendo ese dominio. Este comando borra esos dominios y su inspección (que en realidad inspeccionó la plataforma), y le reasigna a cada startup su dominio propio a partir de sus registros, si lo tiene. Ejemplo: `bolt.host` pasa a `acme-app.bolt.host`.
- **`python manage.py inspect_websites`**: inspecciona, de a una, las startups con dominio propio que nunca se inspeccionaron (o que quedaron `pending` o `failed`). Con `--all` las inspecciona todas de nuevo; `--limit N` acota la cantidad. Al terminar imprime un resumen. Con `--stats` no inspecciona nada: lista las probables SPA vacías (§3.12).
- **`prune_platform_domains`** también promueve a principal el dominio que quedó como alias cuando el principal era una plataforma. Pasa cuando el link de la fuente redirige a una plataforma, como `go.gene.com` → Workday.

### 3.12 Señal combinada y medición de SPA: `querysets.py`, `page_metrics.py`, `inspection_stats.py`

- **`Startup.objects.with_hiring_signal()`** anota tres booleanos, nunca nulos: `has_website_hiring_signal` (la inspección la encontró), `has_recent_hiring_post` (tiene un registro de `hacker_news_hiring` publicado en los últimos `HIRING_POST_MAX_AGE_DAYS`, 60) y `has_hiring_signal` (cualquiera de los dos). No hay un flag guardado que se desactualice: se calcula en cada consulta con un `Exists`.
- **Admin**: el listado de startups usa esa anotación para ordenar (con señal primero, después las más nuevas), para la columna "Señal desde" (Web, Who is hiring o las dos) y para el filtro "búsquedas abiertas". El orden se define en `get_ordering`, porque los checks del admin no aceptan una anotación en `ordering`.
- **`page_metrics.py`**: `measure_page(html)` mide la home y `is_probable_spa_shell(metrics)` aplica la regla: menos de `SPA_SHELL_MAX_TEXT_LENGTH` (200) caracteres visibles, o un contenedor de framework (`APP_ROOT_ELEMENT_IDS`) con menos de `SPA_SHELL_MIN_LINK_COUNT` (3) links. Son umbrales para revisar a mano, no una certeza.
- **`inspection_stats.spa_shell_stats()`**: entre las inspecciones `done` sin señal, cuenta las que todavía no tienen métricas (inspeccionadas antes de que existieran) y devuelve las probables SPA vacías.

## 4. Configuración relevante

| Setting / constante | Dónde | Para qué |
|---|---|---|
| `HUEY` | `config/settings.py` | Cola de tareas en Redis. `HUEY_IMMEDIATE=true` corre las tareas en línea, como en la CI |
| `SOURCE_MERGE_PRIORITY` | `startups/constants.py` | Orden de confianza entre fuentes para el merge |
| `MAX_INGESTION_ATTEMPTS` | `startups/constants.py` | Reintentos ante choques de concurrencia (3) |
| `REDIRECT_TIMEOUT_SECONDS` | `startups/constants.py` | Timeout al resolver redirects (10 s) |
| `HIRING_*`, `JOB_BOARD_DOMAINS`, `JOB_SECTION_DOMAINS` | `startups/constants.py` | Qué cuenta como señal de búsqueda: paths, textos, frases, mails y plataformas |
| `HIRING_FALLBACK_PATHS` | `startups/constants.py` | Rutas del fallback, en orden: `/careers`, `/jobs`, `/join-us`, `/trabaja-con-nosotros` |
| `INSPECTION_TIMEOUT_SECONDS`, `INSPECTION_USER_AGENT` | `startups/constants.py` | Timeout (10 s) y User-Agent identificable (`startup-scout/0.1`) de la inspección |
| `HIRING_POST_MAX_AGE_DAYS` | `startups/constants.py` | Cuánto dura la señal de un aviso en "Who is hiring?" (60 días) |
| `SPA_SHELL_*`, `APP_ROOT_ELEMENT_IDS` | `startups/constants.py` | Regla de "probable SPA vacía" |
| `HACKER_NEWS_HIRING_*`, `FREE_EMAIL_DOMAINS` | `sources/constants.py` | Hilos de "Who is hiring?", ventana de relectura y proveedores de correo que no sirven como web |

## 5. Proceso / pipeline

### 5.1 Vista de punta a punta

```mermaid
flowchart TD
    A["Tarea periódica diaria (huey)<br/>una por fuente habilitada"] --> B["get_adapter(source)<br/>registry en memoria"]
    B --> C["adapter.fetch_candidates(cursor)<br/>lista de RawStartup"]
    C --> D["StartupIngestionService.ingest<br/>dedupe + merge"]
    D --> E{"¿Startup nueva?"}
    E -- no --> F["Se actualiza el registro<br/>y se recalcula el merge"]
    E -- sí --> G["Inspección de su web (huey)<br/>señal de búsquedas abiertas"]
    G --> I["Extracción de contactos<br/>(misma inspección, fase 4)"]
    I --> J["Aparece en la web<br/>status = new, con señal primero"]
    J --> K["Revisión manual:<br/>análisis, contacto, envío desde mi casilla"]
    K --> L["Marco el análisis como enviado<br/>status = contacted"]
```

| Paso | Estado |
|---|---|
| Tarea periódica, runner, `SourceRun` y adaptadores de HN y alta manual | **Implementado (fase 2)** |
| `get_adapter` / registro | **Implementado** |
| Ingesta: dedupe, merge y concurrencia | **Implementado (fase 1)** |
| Señal de búsquedas abiertas | **Implementado (fase 3)** |
| Extracción de contactos | Pendiente (fase 4) |
| Web: listado, ficha, análisis, estados | Pendiente (fase 5) |

### 5.2 Ingesta de una startup (implementado)

```mermaid
sequenceDiagram
    participant Adapter as Adaptador
    participant Ingestion as StartupIngestionService
    participant Web as Sitio de la startup
    participant DB as PostgreSQL

    Adapter->>Ingestion: ingest(source, raw_startup)
    Ingestion->>Ingestion: normalize_domain(website)
    Ingestion->>Web: resolve_final_url (HEAD/GET)
    Web-->>Ingestion: URL final (o None)
    Note over Ingestion: domains = [dominio final, dominio original]<br/>(fuera de la transacción)
    loop hasta MAX_INGESTION_ATTEMPTS
        Ingestion->>DB: BEGIN
        Ingestion->>DB: ¿existe SourceRecord(source, external_id)? (SELECT FOR UPDATE)
        alt ya existe
            Ingestion->>DB: actualiza data/payload, agrega dominios nuevos
        else no existe
            Ingestion->>DB: busca Startup por cualquiera de sus dominios
            opt no hay match
                Ingestion->>DB: crea Startup (marca posible duplicado si coincide el nombre)
            end
            Ingestion->>DB: agrega dominios libres, crea SourceRecord
        end
        Ingestion->>DB: recompute_startup (merge)
        Ingestion->>DB: COMMIT
        Note over Ingestion,DB: si hay IntegrityError: ROLLBACK y se reintenta
    end
    Ingestion-->>Adapter: IngestionResult(startup, created, record_created)
```

Paso a paso:

1. **Dominios (fuera de la transacción).** Se normaliza el `website`. Si no tiene dominio registrable, o si el dominio es de una plataforma (`is_identifying_domain`), la startup se ingresa sin dominio; el `website` igual queda guardado. Un redirect hacia una plataforma tampoco se usa como alias. Después se resuelven los redirects: si la web redirige a otro dominio (`acme.io` → `acme.com`), los dos identifican a la startup y el destino queda como principal. La llamada de red va antes de abrir la transacción para que esta sea corta.
2. **¿Ya conocemos este registro?** Se busca `SourceRecord(source, external_id)` con `SELECT FOR UPDATE`. Si existe, es una re-ingesta: se actualizan `data` y `payload`, se agregan los dominios nuevos y se recalcula el merge. No se crea nada.
3. **¿Ya conocemos la startup?** Se busca una startup que tenga **cualquiera** de los dominios.
   - Si hay una, se usa esa.
   - Si los dominios apuntan a dos startups distintas (por ejemplo, se cargaron `acme.io` y `acme.com` por separado y ahora sabemos que una redirige a la otra), se usa la más antigua y la otra queda marcada `possible_duplicate_of`. **No se fusionan solas.**
4. **Startup nueva.** Si no hubo match, se crea. Si su nombre normalizado coincide con el de otra startup existente, queda marcada como posible duplicado. Esto cubre sobre todo las startups sin web: el nombre solo marca, nunca fusiona, porque dos empresas pueden llamarse igual.
5. **Dominios y registro.** Se agregan los dominios que no tenga otra startup (el primero es el principal) y se crea el `SourceRecord`.
6. **Merge.** `recompute_startup` recalcula todos los campos a partir de todos los registros.
7. **Concurrencia.** Si dos ingestas de la misma startup corren a la vez (dos fuentes o dos workers), ambas pueden no encontrar nada y tratar de crearla. Los constraints únicos (`StartupDomain.domain` y `(source, external_id)`) hacen que una falle con `IntegrityError`. Su transacción se deshace entera, se reintenta, y en el reintento ya encuentra la startup de la otra y se suma como un registro más. Después de `MAX_INGESTION_ATTEMPTS` intentos fallidos lanza `IngestionConflictError`.

### 5.3 Descubrimiento por fuente (implementado, fase 2)

- **Hacker News**: ver §2.6. Una corrida real del último día trajo 205 posts y dio 204 startups (dos posts eran de la misma empresa). Unas 60 quedaron sin dominio porque solo linkean a GitHub. Show HN trae mucho ruido, como esperábamos.
- **HN Who is hiring**: ver §2.7. La primera corrida real (2026-11-19) leyó el hilo de noviembre: **155 avisos con web propia, 154 startups nuevas** (una ya existía por Show HN) en ~1,5 minutos, incluida la resolución de redirects. Revisando la lista a mano, casi todas las webs son correctas. Errores encontrados:
  - `go.gene.com` redirigía a Workday (`myworkdayjobs.com`), que quedó como dominio principal. Se sumaron Workday, iCIMS y Jobvite a las plataformas de búsqueda, y `prune_platform_domains` ahora promueve el alias propio.
  - Algunos nombres salen raros cuando el encabezado no empieza con la empresa (por ejemplo, "SEEKING FREELANCER"). Es poco frecuente y se corrige al revisar.
  - Los avisos con la web en Notion (`acme.notion.site`) quedan con ese subdominio como identidad.
- **Alta manual**: el adaptador ya arma el `RawStartup` (§2.8). El formulario llega en la fase 5 y usa la misma ingesta.
- **Startupxplore: descartada y eliminada.** Sus términos de uso prohíben reproducir su base de datos sin consentimiento escrito. La migración `0003_remove_startupxplore` borra la fuente (y sus registros, si los hubiera) y la saca de los choices de `SourceKey`. El detalle está en [Fuentes descartadas](startup-scout-design.md#fuentes-descartadas), junto con EU-Startups.

### 5.4 Inspección de la web: búsquedas abiertas (implementado, fase 3)

```mermaid
flowchart TD
    A["Startup creada con dominio propio"] --> B["enqueue_website_inspection<br/>status = pending"]
    B --> C["robots.txt de https://dominio/"]
    C -- no permite --> X["status = blocked"]
    C -- permite --> D["GET home (1 request)"]
    D -- error --> Y["status = failed + error"]
    D --> E{"¿Señal en la home?<br/>links, plataformas, mails, frases"}
    E -- sí --> F["done · method = home"]
    E -- no --> G["Fallback: /careers, /jobs,<br/>/join-us, /trabaja-con-nosotros"]
    G --> H{"200, no redirige a la home,<br/>no es el mismo HTML que la home<br/>y tiene palabras de búsqueda"}
    H -- sí --> I["done · method = path_probe"]
    H -- ninguna --> J["done · sin señal"]
```

1. **robots.txt**: se lee el del dominio. Si no existe (404), se permite todo. Si responde 401/403 o un error 5xx, no se permite nada y la inspección queda `blocked`. Si no permite la home, también queda `blocked` y no se pide ninguna página.
2. **Home**: `GET https://<dominio>/`, siguiendo redirects. Si la raíz da 404 y el `website` de la startup es una página del mismo dominio bajo un path (típico de GitHub Pages: `usuario.github.io/proyecto`), se usa esa página como home. Si falla la conexión o responde con error, queda `failed`. Si hay señal, termina acá con **un solo request de página**.
3. **Fallback**: solo si la home no dio señal. Prueba las rutas en orden (salteando las que prohíbe robots.txt) y corta en la primera que cumpla todo esto:
   - responde 200,
   - no termina en la home ni en otro sitio,
   - su texto visible es distinto del de la home (las SPA devuelven el mismo HTML para cualquier ruta),
   - y contiene palabras de búsqueda (`HIRING_PAGE_KEYWORDS`).

   Si un request del fallback falla, se sigue con la ruta siguiente.
4. **Guardado**: estado, fecha, señal y evidencia. Si se inspecciona de nuevo, se actualiza el mismo registro.

**Límites conocidos**: no ejecuta JavaScript, así que en las SPA puras solo el fallback puede encontrar algo (para medirlo: `inspect_websites --stats`, §3.12). Solo prueba `https`. Y es una señal, no una certeza: una página de "Careers" puede no tener búsquedas activas.

**Corrida real (2026-11-19), sobre las startups de HN ya cargadas:**

| Corrida | Inspeccionadas | Con señal | `done` | `blocked` | `failed` |
|---|---|---|---|---|---|
| Primera | 262 | 19 | 232 | 7 | 23 |
| Después de las correcciones | 259 | 14 | 244 | 6 | 9 |

La segunda corrida tardó ~4,5 minutos. Revisar la evidencia de la primera mostró tres problemas, ya corregidos:

- **Dominios de plataformas como identidad**: posts que linkeaban a `plugins.jetbrains.com`, `marketplace.visualstudio.com`, `vercel.com/templates` o `*.bolt.host`, así que se inspeccionaba la home de JetBrains, Microsoft o Vercel (5 falsos positivos). Se sumaron a `NON_IDENTIFYING_DOMAINS` y `SHARED_HOST_DOMAINS`, y `prune_platform_domains` limpió los 4 dominios ya cargados.
- **Rutas de documentación**: `/docs/applications/jobs/` daba señal. Ahora se excluyen las secciones de docs, API, blog y ayuda.
- **GitHub Pages**: la raíz de `usuario.github.io` daba 404 cuando el proyecto vive en `/proyecto`. Los `failed` bajaron de 23 a 9; los que quedan son dominios que no resuelven en DNS y timeouts.

De las 14 señales finales, 11 son búsquedas reales: links a `/careers`, a la página de empleos de YC o a Ashby. Las otras 3 son startups **cuyo producto es una bolsa de trabajo** (su `/jobs` es el producto): es un límite conocido, que se distingue rápido al revisar.

**Sobre las startups de "Who is hiring?"**, que sabemos que están contratando, la inspección de la web encontró la señal en **106 de 151** inspeccionadas (~70 %). Es una medida de cuánto detecta la inspección cuando la búsqueda existe. Con las dos fuentes, el admin muestra **168 startups con señal** de 527, contra 14 antes.

Primera medición de SPA (`inspect_websites --stats`), solo sobre las inspecciones que ya tienen métricas: 13 probables SPA vacías. Las 230 inspecciones anteriores no tienen métricas todavía; se miden con `inspect_websites --all`.


### 5.5 Estados de una startup

```mermaid
stateDiagram-v2
    [*] --> new
    new --> reviewing
    reviewing --> analyzing
    analyzing --> ready_to_contact
    ready_to_contact --> contacted: marco un análisis como enviado
    contacted --> replied
    new --> discarded: descarte manual
    reviewing --> discarded
    analyzing --> discarded
    ready_to_contact --> discarded
    contacted --> discarded
    discarded --> new: descarte revertido
```

Todos los cambios son manuales, salvo el paso a `contacted` al marcar un análisis como enviado. Cada cambio deja un `StatusChange`.

## 6. Tests

Cada app tiene sus tests en `<app>/tests/`, con sus propios fakes:

| Archivo | Cubre |
|---|---|
| `sources/tests/test_registry.py` | Fuentes creadas por las migraciones (HN, HN Who is hiring y manual); toda fuente habilitada tiene adaptador; `get_adapter`, `runs_periodically`, `UnknownSourceError` |
| `sources/tests/test_hacker_news_adapter.py` | Mapeo de Show HN y Launch HN, elección del sitio propio sobre GitHub, filtro por título, cursor con solapamiento, tags desconocidos, errores de la API. Usa `fixtures/` con datos ficticios |
| `sources/tests/test_hacker_news_hiring_adapter.py` | Nombre y encabezado del aviso; elección de la web (coincidencia con el nombre, link en el encabezado, mail de la empresa); avisos descartados (mail gratuito, solo plataforma de búsqueda, sin encabezado, respuestas, borrados, link ajeno); primera corrida con el hilo más nuevo; relectura con solapamiento; cursor; errores de la API |
| `sources/tests/test_manual_adapter.py` | Alta por URL, nombre por defecto, mismo sitio pegado dos veces, URL inválida |
| `sources/tests/test_runner.py` | Corrida exitosa, cursor de la última corrida exitosa, fetch fallido, una startup que falla no corta la corrida, solo las startups creadas pasan al hook de inspección |
| `sources/tests/test_tasks.py` | El descubrimiento diario solo encola fuentes habilitadas y periódicas; la tarea por fuente usa el runner |
| `startups/tests/test_domains.py` | Normalización de dominios (www, subdominios, PaaS, IDN, hosts compartidos, inválidos), plataformas que no identifican y nombres |
| `startups/tests/test_redirects.py` | Redirects con `httpx.MockTransport`: cadena de redirects, fallback a GET, sitio caído, esquema faltante |
| `startups/tests/test_merge.py` | Prioridad por campo, la fuente manual siempre gana, valores vacíos, fuentes desconocidas |
| `startups/tests/test_ingestion.py` | Dedupe entre fuentes, alias por redirect, re-ingesta, merge, posibles duplicados por nombre o por dominios cruzados, web inválida, links a plataformas |
| `startups/tests/test_ingestion_concurrency.py` | Ingestas simultáneas en varios hilos contra Postgres real: una sola startup y ningún error |
| `startups/tests/test_hiring_signal.py` | Cada tipo de señal con HTML ficticio: link en el footer, texto de link, plataformas, sección de empleos de LinkedIn y YC, frase, mail; "Join us on Discord" y la waitlist no cuentan; palabra suelta ("Steve Jobs"); path de otro sitio; rutas de documentación; scripts ignorados; prioridad entre señales |
| `startups/tests/test_website_inspection.py` | La home sola con un request; fallback por ruta; redirect a la home, mismo HTML que la home y página sin palabras no cuentan; robots.txt que bloquea todo o una ruta; robots.txt inexistente; sitio caído; sitio bajo un path (GitHub Pages); startup sin dominio propio; re-inspección |
| `startups/tests/test_domain_cleanup.py` | Un dominio de plataforma se borra junto con su inspección; un host compartido se reemplaza por el subdominio de la startup; los dominios propios no se tocan; el alias propio pasa a principal |
| `startups/tests/test_hiring_status.py` | Señal por aviso reciente, aviso viejo, aviso de otra fuente, señal de la web, las dos; filtro y orden del admin |
| `startups/tests/test_page_metrics.py` | Texto visible, links y contenedores de framework; regla de probable SPA vacía |
| `startups/tests/test_inspection_stats.py` | Conteo de probables SPA vacías y de inspecciones sin métricas; `inspect_websites --stats` no inspecciona |
| `startups/tests/test_inspection_tasks.py` | Encolar marca `pending` y solo para startups con dominio propio; la tarea usa el servicio; el comando `inspect_websites` con y sin `--all` |

Los tests no usan la red. Los de concurrencia usan `transaction=True` y `serialized_rollback=True`, para que la data migration de las fuentes siga disponible para los tests siguientes.
