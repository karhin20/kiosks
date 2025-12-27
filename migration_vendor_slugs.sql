-- Add slug column to vendors table
-- This allows human-readable URLs like /vendors/lampo-platform instead of /vendors/uuid

ALTER TABLE public.vendors 
ADD COLUMN IF NOT EXISTS slug text UNIQUE;

-- Create index for faster slug lookups
CREATE INDEX IF NOT EXISTS idx_vendors_slug ON public.vendors(slug);

-- Function to generate slug from name
CREATE OR REPLACE FUNCTION generate_vendor_slug(vendor_name text)
RETURNS text AS $$
DECLARE
  base_slug text;
  final_slug text;
  counter integer := 0;
BEGIN
  -- Convert to lowercase, replace spaces and special chars with hyphens
  base_slug := lower(regexp_replace(vendor_name, '[^a-zA-Z0-9]+', '-', 'g'));
  -- Remove leading/trailing hyphens
  base_slug := trim(both '-' from base_slug);
  
  final_slug := base_slug;
  
  -- Check for uniqueness and append number if needed
  WHILE EXISTS (SELECT 1 FROM public.vendors WHERE slug = final_slug) LOOP
    counter := counter + 1;
    final_slug := base_slug || '-' || counter;
  END LOOP;
  
  RETURN final_slug;
END;
$$ LANGUAGE plpgsql;

-- Generate slugs for existing vendors
UPDATE public.vendors
SET slug = generate_vendor_slug(name)
WHERE slug IS NULL;

-- Make slug NOT NULL after populating existing records
ALTER TABLE public.vendors 
ALTER COLUMN slug SET NOT NULL;

-- Add trigger to auto-generate slug on insert if not provided
CREATE OR REPLACE FUNCTION auto_generate_vendor_slug()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.slug IS NULL OR NEW.slug = '' THEN
    NEW.slug := generate_vendor_slug(NEW.name);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_auto_generate_vendor_slug
  BEFORE INSERT ON public.vendors
  FOR EACH ROW
  EXECUTE FUNCTION auto_generate_vendor_slug();

-- Add trigger to update slug when name changes (optional)
CREATE OR REPLACE FUNCTION update_vendor_slug_on_name_change()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.name != OLD.name THEN
    -- Only update slug if it was auto-generated (matches the old name pattern)
    IF OLD.slug = generate_vendor_slug(OLD.name) THEN
      NEW.slug := generate_vendor_slug(NEW.name);
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_vendor_slug
  BEFORE UPDATE ON public.vendors
  FOR EACH ROW
  EXECUTE FUNCTION update_vendor_slug_on_name_change();
