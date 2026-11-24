# startup-scout

Discovers newly launched startups from a few public sources, keeps a deduplicated history of them,
and gives me a place to review each one, find its founders' public contacts and track my outreach.

Docs (in Spanish):

- [Design and MVP plan](docs/startup-scout-design.md)
- [Architecture: what each part of the code does and how the pipeline works](docs/architecture.md)

## Stack

Python 3.12 · Django 5.2 · PostgreSQL · huey + Redis · Django templates + HTMX.

## Sources (MVP)

| Source | Access |
|---|---|
| Hacker News (Show HN / Launch HN) | Public Algolia API |
| Hacker News "Ask HN: Who is hiring?" (companies hiring) | Public Algolia API |
| Manual | Paste a URL in the web UI |

A startup exists once, whatever the number of sources that mention it: identity is the
normalized registrable domain (Public Suffix List aware, redirects kept as aliases), and the
startup's fields are recomputed from every source record using a per-source priority.

## Running locally

```bash
cp .env.example .env
docker compose up --build
```

The app listens on http://localhost:8000. Postgres and Redis are exposed on ports 5433 and 6380
so they don't clash with local services.

Every page needs a session (it is a single-user app). Create your user once and log in with it:

```bash
docker compose run --rm web python manage.py createsuperuser
```

Sources run once a day from 07:00 (Madrid time). The worker checks every hour, so a run missed
while the computer was asleep happens at the next check. To run a source right now:

```bash
docker compose run --rm web python manage.py run_source hacker_news
docker compose run --rm web python manage.py run_source hacker_news_hiring
```

Inspect the websites of the startups already loaded (new ones are inspected automatically):

```bash
docker compose run --rm web python manage.py inspect_websites
```

List the inspections without a hiring signal whose home looks like an empty single-page-app
shell, to check them by hand (inspections made before these metrics existed need `--all` first):

```bash
docker compose run --rm web python manage.py inspect_websites --stats
```

Check which startups publish active openings today, on their website or their Ashby,
Greenhouse or Lever board (new startups are checked automatically, and every week again):

```bash
docker compose run --rm web python manage.py verify_openings
```

Only the software roles looked for are kept, and only if they require no language besides
English and Spanish (from their title and description) and are not only in countries where an
EU citizen needs a visa (the UK always; elsewhere outside the EU when the description says no visa
is sponsored); the rest is discarded when verifying.
After changing those keywords in `startups/constants.py`, discard the stored openings that no
longer match (no requests; openings discarded before come back with `verify_openings --all`):

```bash
docker compose run --rm web python manage.py prune_openings
```

Detect the country each startup is established in, from the evidence already stored (website
address, declared headquarters, where its openings are, country-code domain). It runs after every
openings check too; locations corrected by hand are kept:

```bash
docker compose run --rm web python manage.py detect_locations
```

Blacklist a site that is not a startup, such as a job board the rules could not detect (also from
the startup's page): its startup is discarded and never inspected again:

```bash
docker compose run --rm web python manage.py blacklist_domain https://www.frameworkheroes.com
```

If you add platforms to the identity rules, clean up the domains already stored first:

```bash
docker compose run --rm web python manage.py prune_platform_domains
```

## Tests and lint

```bash
docker compose run --rm web pytest
docker compose run --rm web ruff check .
```

## Status

- [x] Phase 0 — project setup, docker compose, CI
- [x] Phase 1 — domain model, source registry, ingestion with deduplication and merge
- [x] Phase 2 — source adapters (Hacker News, manual), runner, daily huey task
- [x] Phase 3 — hiring signal (careers / jobs section on the startup's website)
- [x] Phase 3b — "Who is hiring?" source, hiring signal from recent posts, single-page-app metrics
- [x] Phase 4 — contacts from the startup's own website and Hacker News authors
- [x] Phase 5 — web UI: list, detail, contacts, analyses, statuses, manual entry, duplicates, runs
- [x] Phase 5b — active openings verified on the website or job board; clean list and filters
- [x] Phase 5c — headquarters country and time difference from Madrid, with a filter
- [x] Phase 5d — only the software roles looked for, without other languages; the rest is
  discarded

## License

MIT

Place data (countries, US states, cities and their time zones) comes from
[GeoNames](https://www.geonames.org/) through the `geonamescache` package, under the
[Creative Commons Attribution 4.0 License](https://creativecommons.org/licenses/by/4.0/).
