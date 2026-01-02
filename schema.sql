-- 1. Create a table for public profiles matching your requirements
create table public.users (
  id uuid references auth.users not null primary key,
  email text,
  full_name text,
  phone text, -- Added phone
  user_type text default 'customer', -- 'admin' or 'customer'
  favorites text[] default array[]::text[], -- Array of product IDs to keep favorites
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 2. Set up Row Level Security (RLS)
alter table public.users enable row level security;

create policy "Public profiles are viewable by everyone."
  on public.users for select
  using ( true );

create policy "Users can insert their own profile."
  on public.users for insert
  with check ( auth.uid() = id );

create policy "Users can update own profile."
  on public.users for update
  using ( auth.uid() = id );

-- 3. Create a reusable function to handle new user signup
create or replace function public.handle_new_user() 
returns trigger as $$
begin
  insert into public.users (id, email, full_name, phone, user_type)
  values (
    new.id, 
    new.email, 
    new.raw_user_meta_data->>'name',
    new.raw_user_meta_data->>'phone', -- Extract phone from metadata
    coalesce(new.raw_user_meta_data->>'role', 'customer')
  );
  return new;
end;
$$ language plpgsql security definer;

-- 4. Create a trigger that fires every time a new user signs up via Auth
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- 5. Link Orders to Users (Foreign Key)
ALTER TABLE public.orders
ADD CONSTRAINT fk_orders_user
FOREIGN KEY (user_id)
REFERENCES public.users (id)
ON DELETE SET NULL;

-- 6. Add images column to products table
ALTER TABLE public.products 
ADD COLUMN IF NOT EXISTS images text[] DEFAULT array[]::text[];

-- 7. Add phone column to users table (Migration helper)
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS phone text;

-- 8. Add address column to users table (Migration helper)
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS address jsonb DEFAULT NULL;

-- 9. Add product metadata columns (Migration helper)
ALTER TABLE public.products 
ADD COLUMN IF NOT EXISTS is_flash_sale boolean DEFAULT false,
ADD COLUMN IF NOT EXISTS sales_count integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS is_featured boolean DEFAULT false,
ADD COLUMN IF NOT EXISTS video_url text,
ADD COLUMN IF NOT EXISTS created_at timestamp with time zone DEFAULT timezone('utc'::text, now());
