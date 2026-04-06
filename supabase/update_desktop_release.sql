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
    '5.2.2',
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
