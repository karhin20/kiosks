-- Add rating columns to products table
ALTER TABLE public.products 
ADD COLUMN IF NOT EXISTS rating FLOAT DEFAULT 0,
ADD COLUMN IF NOT EXISTS reviews_count INTEGER DEFAULT 0;

-- Function to calculate and update product rating
CREATE OR REPLACE FUNCTION update_product_rating()
RETURNS TRIGGER AS $$
DECLARE
    new_rating FLOAT;
    new_count INTEGER;
BEGIN
    -- Calculate new average and count for the product (using NEW.product_id or OLD.product_id)
    -- We need to handle both INSERT/UPDATE (use NEW) and DELETE (use OLD)
    -- If update, product_id *might* change, but usually not. Safest to update both if they differ.
    
    DECLARE
        target_product_id TEXT;
    BEGIN
        IF (TG_OP = 'DELETE') THEN
            target_product_id := OLD.product_id;
        ELSE
            target_product_id := NEW.product_id;
        END IF;

        SELECT 
            COALESCE(AVG(rating), 0), 
            COUNT(*) 
        INTO 
            new_rating, 
            new_count 
        FROM public.reviews 
        WHERE product_id = target_product_id;

        UPDATE public.products
        SET rating = new_rating, reviews_count = new_count
        WHERE id = target_product_id;
        
        -- If UPDATE and product_id changed (rare), also update old product
        IF (TG_OP = 'UPDATE' AND OLD.product_id != NEW.product_id) THEN
             SELECT 
                COALESCE(AVG(rating), 0), 
                COUNT(*) 
            INTO 
                new_rating, 
                new_count 
            FROM public.reviews 
            WHERE product_id = OLD.product_id;

            UPDATE public.products
            SET rating = new_rating, reviews_count = new_count
            WHERE id = OLD.product_id;
        END IF;
    END;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to run after changes to reviews
DROP TRIGGER IF EXISTS on_review_change ON public.reviews;
CREATE TRIGGER on_review_change
AFTER INSERT OR UPDATE OR DELETE ON public.reviews
FOR EACH ROW EXECUTE FUNCTION update_product_rating();
