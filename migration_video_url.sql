-- Migration to add video_url column to products table
ALTER TABLE public.products 
ADD COLUMN IF NOT EXISTS video_url text;
