from functools import lru_cache
from supabase import Client, create_client
from .config import get_settings


@lru_cache
def get_supabase_client() -> Client:
    """
    Returns a singleton Supabase client configured with service role credentials.
    """
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


@lru_cache
def get_supabase_anon_client() -> Client:
    """
    Returns a Supabase client using the anon key for auth flows (password login/signup).
    """
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY or settings.SUPABASE_SERVICE_ROLE_KEY)

