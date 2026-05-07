"""
Módulo de conexión a Supabase.
Lee las credenciales del archivo .env y devuelve un cliente listo para usar.
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Cargar variables del archivo .env
load_dotenv()

def get_supabase_client() -> Client:
    """Devuelve un cliente de Supabase configurado con las credenciales del .env"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    
    if not url or not key:
        raise ValueError(
            "Faltan SUPABASE_URL o SUPABASE_ANON_KEY en el archivo .env"
        )
    
    return create_client(url, key)


# Prueba rápida si se ejecuta este archivo directamente
if __name__ == "__main__":
    try:
        client = get_supabase_client()
        # Probar la conexión consultando una tabla
        response = client.table("campus").select("*").execute()
        print("✅ Conexión exitosa con Supabase")
        print(f"   Filas en tabla 'campus': {len(response.data)}")
    except Exception as e:
        print(f"❌ Error de conexión: {e}")