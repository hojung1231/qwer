-- Private, device-authenticated team sharing. No public media bucket.
create schema if not exists bogo_private;
revoke all on schema bogo_private from public;
create table public.bogo_profiles(id uuid primary key references auth.users(id) on delete cascade,name text not null check(length(name) between 1 and 40),phone text not null default '' check(length(phone)<=30),created_at timestamptz not null default now());
create table public.bogo_links(owner uuid not null references public.bogo_profiles(id) on delete cascade,peer uuid not null references public.bogo_profiles(id) on delete cascade,created_at timestamptz not null default now(),primary key(owner,peer),check(owner<>peer));
create index bogo_links_peer on public.bogo_links(peer);
create table public.bogo_invites(token text primary key default(replace(gen_random_uuid()::text,'-','')||replace(gen_random_uuid()::text,'-','')),owner uuid not null references public.bogo_profiles(id) on delete cascade,claimed_by uuid references public.bogo_profiles(id),expires_at timestamptz not null default(now()+interval '1 day'),created_at timestamptz not null default now(),check(length(token)=64));
create index bogo_invites_owner on public.bogo_invites(owner);
create index bogo_invites_claimed on public.bogo_invites(claimed_by);
create table public.bogo_sets(id uuid primary key,sender uuid not null references public.bogo_profiles(id),project_name text not null check(length(project_name) between 1 and 100),sender_name text not null check(length(sender_name) between 1 and 40),photo_count integer not null check(photo_count between 0 and 500),item_count integer not null check(item_count between 1 and 500),ready boolean not null default false,created_at timestamptz not null default now(),unique(id,sender));
create index bogo_sets_sender on public.bogo_sets(sender);
create table public.bogo_deliveries(id uuid primary key default gen_random_uuid(),set_id uuid not null references public.bogo_sets(id) on delete cascade,sender uuid not null references public.bogo_profiles(id),recipient uuid not null references public.bogo_profiles(id),created_at timestamptz not null default now(),read_at timestamptz,unique(set_id,recipient),constraint bogo_delivery_set_sender foreign key(set_id,sender) references public.bogo_sets(id,sender) on delete cascade,check(sender<>recipient));
create index bogo_deliveries_recipient_time on public.bogo_deliveries(recipient,created_at desc);
create index bogo_deliveries_sender on public.bogo_deliveries(sender);
alter table public.bogo_profiles enable row level security;
alter table public.bogo_links enable row level security;
alter table public.bogo_invites enable row level security;
alter table public.bogo_sets enable row level security;
alter table public.bogo_deliveries enable row level security;
revoke all on public.bogo_profiles,public.bogo_links,public.bogo_invites,public.bogo_sets,public.bogo_deliveries from anon,authenticated;
grant select,insert,update on public.bogo_profiles to authenticated;
grant select on public.bogo_links to authenticated;
grant select,insert on public.bogo_invites to authenticated;
grant select,insert(id,sender,project_name,sender_name,photo_count,item_count),update(ready) on public.bogo_sets to authenticated;
grant select,insert(id,set_id,sender,recipient) on public.bogo_deliveries to authenticated;
grant update(read_at) on public.bogo_deliveries to authenticated;
create policy profile_read on public.bogo_profiles for select to authenticated using(id=(select auth.uid()) or exists(select 1 from public.bogo_links l where l.owner=(select auth.uid()) and l.peer=id));
create policy profile_insert on public.bogo_profiles for insert to authenticated with check(id=(select auth.uid()));
create policy profile_update on public.bogo_profiles for update to authenticated using(id=(select auth.uid())) with check(id=(select auth.uid()));
create policy links_read on public.bogo_links for select to authenticated using(owner=(select auth.uid()));
create policy invites_read on public.bogo_invites for select to authenticated using(owner=(select auth.uid()));
create policy invites_create on public.bogo_invites for insert to authenticated with check(owner=(select auth.uid()) and claimed_by is null and expires_at<=now()+interval '7 days');
create policy sets_read on public.bogo_sets for select to authenticated using(sender=(select auth.uid()) or (ready and exists(select 1 from public.bogo_deliveries d where d.set_id=public.bogo_sets.id and d.recipient=(select auth.uid()))));
create policy sets_insert on public.bogo_sets for insert to authenticated with check(sender=(select auth.uid()) and sender_name=(select p.name from public.bogo_profiles p where p.id=(select auth.uid())));
create policy sets_update on public.bogo_sets for update to authenticated using(sender=(select auth.uid())) with check(sender=(select auth.uid()));
create policy deliveries_read on public.bogo_deliveries for select to authenticated using(recipient=(select auth.uid()) or sender=(select auth.uid()));
create policy deliveries_insert on public.bogo_deliveries for insert to authenticated with check(sender=(select auth.uid()) and exists(select 1 from public.bogo_links l where l.owner=(select auth.uid()) and l.peer=public.bogo_deliveries.recipient));
create policy deliveries_mark_read on public.bogo_deliveries for update to authenticated using(recipient=(select auth.uid())) with check(recipient=(select auth.uid()));
-- Claiming a high-entropy, single-use invite needs an atomic cross-owner lookup.
-- The elevated helper is in a non-exposed schema and always authenticates its caller.
create function bogo_private.accept_invite(invite_token text) returns uuid language plpgsql security definer set search_path='' as $$
declare me uuid:=auth.uid(); invitation public.bogo_invites; begin
 if me is null then raise exception 'Authentication required'; end if;
 if not exists(select 1 from public.bogo_profiles where id=me) then raise exception 'Create your profile first'; end if;
 select * into invitation from public.bogo_invites where token=invite_token for update;
 if not found or invitation.expires_at<now() then raise exception 'Invite expired or invalid'; end if;
 if invitation.owner=me then raise exception 'Cannot accept your own invite'; end if;
 if invitation.claimed_by is not null and invitation.claimed_by<>me then raise exception 'Invite already used'; end if;
 insert into public.bogo_links(owner,peer) values(invitation.owner,me),(me,invitation.owner) on conflict do nothing;
 update public.bogo_invites set claimed_by=me where token=invite_token;
 return invitation.owner;
end; $$;
revoke all on function bogo_private.accept_invite(text) from public;
grant usage on schema bogo_private to authenticated;
grant execute on function bogo_private.accept_invite(text) to authenticated;
create function public.bogo_accept_invite(invite_token text) returns uuid language sql security invoker set search_path='' as $$select bogo_private.accept_invite(invite_token);$$;
revoke all on function public.bogo_accept_invite(text) from public;
grant execute on function public.bogo_accept_invite(text) to authenticated;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types) values('bogo-sets','bogo-sets',false,52428800,array['image/jpeg','image/png','video/mp4','audio/wav','audio/mp4','application/json']);
create policy bogo_media_insert on storage.objects for insert to authenticated with check(bucket_id='bogo-sets' and (storage.foldername(name))[1]=(select auth.uid())::text and exists(select 1 from public.bogo_sets s where s.id::text=(storage.foldername(name))[2] and s.sender=(select auth.uid()) and not s.ready));
create policy bogo_media_read on storage.objects for select to authenticated using(bucket_id='bogo-sets' and ((storage.foldername(name))[1]=(select auth.uid())::text or exists(select 1 from public.bogo_sets s join public.bogo_deliveries d on d.set_id=s.id where s.id::text=(storage.foldername(name))[2] and s.sender::text=(storage.foldername(name))[1] and s.ready and d.recipient=(select auth.uid()))));
create policy bogo_media_cleanup on storage.objects for delete to authenticated using(bucket_id='bogo-sets' and (storage.foldername(name))[1]=(select auth.uid())::text and not exists(select 1 from public.bogo_deliveries d where d.set_id::text=(storage.foldername(name))[2]));

alter publication supabase_realtime add table public.bogo_deliveries;
