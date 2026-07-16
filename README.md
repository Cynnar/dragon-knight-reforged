# Dragon Knight (Reforged)

A modern rewrite of the classic Dragon Knight PHP browser RPG, built with Django.
Multiplayer persistent world, containerized to run behind Nginx Proxy Manager against a
shared MariaDB.

## Folder layout (unified, one folder per container)

**This whole folder is both the git repo and the container's home.** Everything for the
container lives here; runtime data is a gitignored subfolder.

```
/docker/containers/
└── dragon-knight-reforged/        <-- THIS folder = the git repo
    ├── docker-compose.yml         deployment (relative ./data mounts)
    ├── Dockerfile
    ├── entrypoint.sh
    ├── requirements.txt
    ├── manage.py
    ├── .env                       secrets — gitignored, you create this
    ├── .env.example
    ├── config/                    Django project (settings, urls, wsgi, asgi)
    ├── game/                      the game app
    │   ├── models.py  admin.py  views.py  apps.py
    │   ├── migrations/            0001_initial.py (the schema)
    │   ├── management/commands/   seed_game_data.py
    │   └── seed_data/             the 7 content JSON files (loaded by the seed cmd)
    ├── docs/                      framework-neutral reference (tracked)
    │   ├── combat-and-progression.md
    │   └── data-dictionary.md
    └── data/                      RUNTIME data — gitignored, created at deploy
        ├── staticfiles/
        └── media/
```

Because the compose file uses **relative** `./data/...` bind mounts, this folder works
anywhere — you can keep it at `/docker/containers/dragon-knight-reforged/` or move it and
nothing breaks.

### Where the files you downloaded go

All the individual files (models.py, settings.py, the JSON, etc.) are already placed
correctly **inside this archive** — just extract the whole thing and keep the structure.
Two things worth knowing:

- The 7 content JSON files (`monsters.json`, `items.json`, ...) belong to the repo at
  `game/seed_data/` — they're source/seed data, **not** runtime data. They do NOT go in
  `data/`. The seed command reads them from `game/seed_data/`.
- `data/` starts empty. Docker + the app fill `staticfiles/` and `media/` at runtime.
  Nothing you download goes in `data/`.

## Git

This folder is the repo. From inside it:

```bash
git init                      # (you've already done this)
git remote add origin git@github.com:Cynnar/dragon-knight-reforged.git
git add .
git commit -m "Initial Django scaffold, models, Docker deployment"
git branch -M main
git push -u origin main
```

`.env` and `data/` are gitignored, so neither secrets nor runtime files are ever
committed.

## First run

### 1. Create the database and user in `main_db`

```bash
docker exec -it main_db mariadb -uroot -p
```
```sql
CREATE DATABASE dragon_knight CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'dk_user'@'%' IDENTIFIED BY 'a-strong-password';
GRANT ALL PRIVILEGES ON dragon_knight.* TO 'dk_user'@'%';
FLUSH PRIVILEGES;
```

### 2. Docker networks

Already set to match your stack: the app joins your existing `frontend` (so NPM can
proxy to it) and `backend` (so it can reach `main_db`) networks — the same two your
Wiki.js container uses. Nothing to change.

### 3. Configure and launch

```bash
cp .env.example .env
# edit .env: generate SECRET_KEY, set the DATABASE_URL password, set ALLOWED_HOSTS
# Create the runtime data dirs owned by the container's user (uid/gid 1000),
# so collectstatic/media writes succeed:
mkdir -p data/staticfiles data/media
sudo chown -R 1000:1000 data
docker compose up -d --build
```

The entrypoint runs migrations and `collectstatic`, then starts gunicorn on port 8000
(internal). Follow it with `docker compose logs -f`.

### 4. Point Nginx Proxy Manager at it

Add a Proxy Host forwarding your hostname to `dragon-knight-reforged` port `8000`, with
your SSL cert. That hostname must match `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` in `.env`.

### 5. Create your admin login

```bash
docker compose exec dragon-knight-reforged python manage.py createsuperuser
```
Then visit `/admin/` — the modern replacement for the old `admin.php`.

### 6. Load the game content

```bash
docker compose exec dragon-knight-reforged python manage.py seed_game_data
```
Populates 151 monsters, 33 items, 19 spells, 300 per-class level tiers, 32 drops, 8
towns, and the control row from `game/seed_data/`. Idempotent — safe to re-run.

## Config

All environment-specific settings are read from the environment (12-factor) via
`django-environ`; see `.env.example`. Nothing environment-specific is hard-coded in
`config/settings.py`.

## Status

Scaffold, deployment, and the full data layer are done: 11 models, migrations, admin, and
the seed command. The game *logic* (movement, combat, towns, leveling) is next — build it
against `docs/combat-and-progression.md`.
