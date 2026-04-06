alter table public.app_updates
add column if not exists force_update boolean not null default false;
