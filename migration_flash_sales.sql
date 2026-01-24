-- Add flash_sale_end_time to products table
ALTER TABLE public.products 
ADD COLUMN IF NOT EXISTS flash_sale_end_time timestamp with time zone;
