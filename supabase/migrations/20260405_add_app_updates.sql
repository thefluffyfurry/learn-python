create table if not exists public.app_updates (
    slug text primary key,
    version text not null,
    download_url text not null,
    asset_name text not null default 'PyQuestAcademy.zip',
    notes text not null default '',
    wipe_local_state boolean not null default false,
    force_update boolean not null default false,
    updated_at timestamptz not null default timezone('utc', now())
);

alter table public.app_updates enable row level security;

revoke all on table public.app_updates from anon, authenticated;
grant all on table public.app_updates to service_role;

insert into public.app_updates (
    slug,
    version,
    download_url,
    asset_name,
    notes,
    wipe_local_state,
    force_update
)
values (
    'desktop',
    '2.1.5',
    'https://keyquuyuamfuvotaruod.supabase.co/storage/v1/object/public/updates/windows/PyQuestAcademy.zip',
    'PyQuestAcademy.zip',
    'Full package refresh from the hosted server.',
    false,
    false
)
on conflict (slug) do update set
    version = excluded.version,
    download_url = excluded.download_url,
    asset_name = excluded.asset_name,
    notes = excluded.notes,
    wipe_local_state = excluded.wipe_local_state,
    force_update = excluded.force_update,
    updated_at = timezone('utc', now());
