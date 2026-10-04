"""Legacy module — data layer moved to supabase_db.py."""

from app import supabase_db

def is_connected():
    return supabase_db.is_ready()
