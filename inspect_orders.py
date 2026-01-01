
from app.supabase_client import get_supabase_client
from app.config import get_settings

def debug_orders():
    supabase = get_supabase_client()
    try:
        # Try to get one order to see columns
        response = supabase.table("orders").select("*").limit(1).execute()
        print(f"Columns: {response.data[0].keys() if response.data else 'No data to show columns'}")
        if response.data:
            print(f"Sample data: {response.data[0]}")
        else:
            # If no data, try to insert a dummy order to see what fails
            print("No existing orders found. Attempting a dummy insert...")
            # dummy_order = {
            #     "user_id": "some-uuid", 
            #     "status": "pending",
            #     "total": 0,
            #     "items": [],
            #     "shipping": {}
            # }
            # res = supabase.table("orders").insert(dummy_order).execute()
            # print(f"Dummy insert response: {res}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_orders()
