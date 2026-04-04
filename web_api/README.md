# PyQuest Hosted API

This folder is the deployable backend for `http://pyquest-academy.free.nf/`.

## Hosting model

`free.nf` hosting does not run Python web apps. Use:

- PHP for the API
- MySQL for accounts, XP, sessions, and leaderboard data
- Static JSON for the lesson catalog

## Deploy

1. Copy the contents of `web_api/api/` into your site's `/htdocs/api/` folder.
2. Copy `web_api/data/lessons.json` into `/htdocs/data/lessons.json`.
3. Copy `web_api/api/config.example.php` to `/htdocs/api/config.php`.
4. Fill in the MySQL values from your hosting control panel.
5. Run the SQL in `web_api/schema.sql` in phpMyAdmin.
6. Open `http://pyquest-academy.free.nf/api/health`.

If deployment is correct, `health` should return JSON with `{"status":"ok"}`.

## Desktop app

Use the hosted API by setting:

```powershell
$env:PYQUEST_API_URL='http://pyquest-academy.free.nf/api'
python main.py
```

Without `PYQUEST_API_URL`, the desktop app stays in local development mode and starts the local Python server.
