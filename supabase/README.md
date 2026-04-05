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

## Supabase Setup

1. Create a free Supabase project.
2. Install the Supabase CLI on your machine.
3. Sign in with the CLI.
4. Link this repo to your project.
5. Run the SQL in `supabase/migrations/20260404_init_pyquest.sql`.
6. Set the Edge Function secret:

```powershell
supabase secrets set PYQUEST_SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

7. Deploy the function:

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

## Info I Need From You

When you finish creating the Supabase project, send me:

- the project URL or final function base URL
- whether you want to use the environment variable or hardcode the function URL in `app/settings.py`

I do not need your service role key in chat.
