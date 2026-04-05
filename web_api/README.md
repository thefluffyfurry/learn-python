# PyQuest Hosted API

This folder is the deployable backend for a standard PHP + MySQL hosting account.

## Hosting model

The desktop app talks to this backend over plain HTTP requests, so use a host that serves normal PHP endpoints to desktop clients.

Recommended approach:

- PHP for the API
- MySQL for accounts, XP, sessions, and leaderboard data
- Static JSON for the lesson catalog

Avoid hosts that inject browser-only anti-bot pages into `/api/*` responses, because the desktop app expects JSON.

## Deploy To A New Host

These steps work on typical shared hosting with Apache, PHP, MySQL, phpMyAdmin, and either `public_html` or `htdocs`.

1. Create a hosting account with PHP and MySQL.
2. Create a new MySQL database and database user in the host control panel.
3. Import `web_api/schema.sql` with phpMyAdmin.
4. Upload the contents of `web_api/api/` to `/public_html/api/` or `/htdocs/api/`.
5. Upload `web_api/data/lessons.json` to `/public_html/data/lessons.json` or `/htdocs/data/lessons.json`.
6. Copy `web_api/api/config.example.php` to `web_api/api/config.php`.
7. Fill in the real database values in `config.php`.
8. Open `https://your-domain.example/api/health`.
9. Run `python web_api/check_api.py https://your-domain.example/api` from this repo.

If deployment is correct, `health` should return JSON with `{"status":"ok"}`.

## Notes

- Do not commit `web_api/api/config.php`. It contains secrets and is ignored by Git.
- Use `https://` for the final API URL if your host provides SSL.
- If `/api/health` shows HTML instead of JSON, the host is not suitable for the desktop app.

## Desktop app

After the new host is working, point the desktop app at it:

```powershell
$env:PYQUEST_API_URL='https://your-domain.example/api'
python main.py
```

Use local development mode by setting:

```powershell
$env:PYQUEST_API_URL='http://127.0.0.1:8123'
python main.py
```

Without `PYQUEST_API_URL`, the desktop app stays in local mode until you replace the placeholder hosted URL in `app/settings.py` or set the environment variable when starting the app.
