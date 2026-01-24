-- Add status column to products table
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'status') THEN
        ALTER TABLE products ADD COLUMN status TEXT DEFAULT 'pending';
        -- Update existing products to published
        UPDATE products SET status = 'published';
    END IF;
END $$;

-- Add comment for documentation
COMMENT ON COLUMN products.status IS 'Status of the product: draft, pending, published, rejected';
