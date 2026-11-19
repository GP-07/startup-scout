# startup-scout

Discovers newly launched startups from a few public sources, keeps a deduplicated history of them,
and gives me a place to review each one, find its founders' public contacts and track my outreach.

Docs (in Spanish):

- [Design and MVP plan](docs/startup-scout-design.md)
- [Architecture: what each part of the code does and how the pipeline works](docs/architecture.md)

## Stack

Python 3.12 · Django 5.2 · PostgreSQL · huey + Redis · Django templates + HTMX (upcoming).

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

Run a source now instead of waiting for the daily 07:00 task:

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
- [ ] Phase 4 — contacts from the startup's own website
- [ ] Phase 5 — web UI

## License

MIT
