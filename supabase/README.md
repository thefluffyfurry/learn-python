# PyQuest Supabase Backend

This folder replaces the old PHP host with a Supabase Edge Function plus Postgres tables while keeping the desktop app API the same.

## What This Uses

- One Edge Function: `pyquest-api`
- Three Postgres tables: `users`, `sessions`, `lesson_progress`
- One bundled lesson catalog file: `supabase/functions/_shared/lessons.json`

The desktop app still talks to these routes:

- `GET /health`
- `GET /lessons`
- `POST /signup`
- `POST /login`
- `GET /profile`
- `POST /submit-lesson`
- `GET /leaderboard`
- `GET /admin/activity` with an admin key header

## Supabase Setup

1. Create a free Supabase project.
2. Install the Supabase CLI on your machine.
3. Sign in with the CLI.
4. Link this repo to your project.
5. Run the SQL in `supabase/migrations/20260404_init_pyquest.sql`.
6. Run the SQL in `supabase/migrations/20260405_add_app_updates.sql`.
7. Run the SQL in `supabase/migrations/20260405_add_activity_logging.sql`.
8. Set the Edge Function secrets:

```powershell
supabase secrets set PYQUEST_SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
supabase secrets set PYQUEST_ADMIN_API_KEY=your-own-admin-key
```

9. Deploy the function:

```powershell
supabase functions deploy pyquest-api
```

The function base URL will be:

```text
https://your-project-ref.supabase.co/functions/v1/pyquest-api
```

## Test The Function

Run:

```powershell
python web_api/check_api.py https://your-project-ref.supabase.co/functions/v1/pyquest-api
```

It should print JSON with `{"status": "ok"}`.

## Desktop App

Start the app against Supabase with:

```powershell
$env:PYQUEST_API_URL='https://your-project-ref.supabase.co/functions/v1/pyquest-api'
python main.py
```

Or replace `HOSTED_API_URL` in `app/settings.py` with your real function URL.

## Admin Activity View

Once deployed, every hosted desktop, console, and website request can report:

- app version
- account username
- stable session name
- IP address
- last seen route

To view it from your computer:

```powershell
$env:PYQUEST_ADMIN_KEY='your-own-admin-key'
python admin_activity.py
```

This prints:

- active clients
- recent logins and signups
- recent activity

## Info I Need From You

When you finish creating the Supabase project, send me:

- the project URL or final function base URL
- whether you want to use the environment variable or hardcode the function URL in `app/settings.py`

I do not need your service role key in chat.
