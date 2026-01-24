-- Create subscriptions table
create table public.subscriptions (
  id uuid default gen_random_uuid() primary key,
  email text not null unique,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Enable RLS
alter table public.subscriptions enable row level security;

-- Allow anyone to insert (public subscription)
create policy "Anyone can insert subscription"
  on public.subscriptions for insert
  with check ( true );

-- Only admins can view subscriptions (assuming admin role exists or handling via service role)
-- For now, we restrict read/update/delete to service role or authenticated users if needed.
-- Let's stick strictly to "Anyone can insert" for the public facing part.
