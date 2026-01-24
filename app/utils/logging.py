from typing import Optional, Any
from supabase import Client

def log_action(
    supabase: Client,
    user: dict,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[Any] = None
):
    """
    Utility function to record an action in the audit_logs table.
    'user' is the dict returned by get_current_user dependency.
    """
    try:
        log_entry = {
            "user_id": user.get("id"),
            "user_name": user.get("name") or user.get("email"),
            "user_role": user.get("role"),
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details
        }
        
        # We don't want to block the main request if logging fails, 
        # but since this is usually called within a route, we use the provided client.
        supabase.table("audit_logs").insert(log_entry).execute()
        
    except Exception as e:
        # Log to server console if DB logging fails
        print(f"FAILED TO WRITE AUDIT LOG: {e}")
