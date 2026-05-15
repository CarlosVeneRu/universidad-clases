"""
Aplicación principal del Sistema de Gestión de Clases UVM.
Punto de entrada de Streamlit.
"""
import sys
from pathlib import Path

# Permitir importar módulos de la carpeta app/
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
from app.utils.supabase_client import get_supabase_client


# Configuración de la página (esto siempre va primero)
st.set_page_config(
    page_title="Sistema de Clases UVM",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_resource
def init_supabase():
    """Inicializa el cliente de Supabase una sola vez."""
    return get_supabase_client()


def main():
    """Página principal del sistema (Dashboard)."""
    
    # Encabezado
    st.title("🎓 Sistema de Gestión de Clases")
    st.markdown("**Universidad del Valle de México · Campus Querétaro**")
    st.divider()
    
    try:
        client = init_supabase()
        
        # ===== SECCIÓN 1: Métricas principales =====
        st.subheader("📊 Resumen general")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            res = client.table("clases").select("crn", count="exact").execute()
            st.metric("📝 Clases activas", res.count)
        
        with col2:
            res = client.table("maestros").select("clave", count="exact").execute()
            st.metric("👨‍🏫 Maestros", res.count)
        
        with col3:
            res = client.table("materias").select("id", count="exact").execute()
            st.metric("📚 Materias", res.count)
        
        with col4:
            res = client.table("salones").select("codigo", count="exact").execute()
            st.metric("🚪 Salones físicos", res.count)
        
        st.divider()
        
        # ===== SECCIÓN 2: Información detallada =====
        col_izq, col_der = st.columns(2)
        
        with col_izq:
            st.subheader("📅 Periodos académicos")
            periodos = client.table("periodos").select("*").order("id").execute()
            for p in periodos.data:
                st.markdown(f"**{p['id']}** · {p['descripcion']}")
        
        with col_der:
            st.subheader("⚠️ Alertas del sistema")
            
            # Choques de salones
            choques = client.rpc("detectar_choques_salon").execute()
            num_choques = len(choques.data) if choques.data else 0
            if num_choques > 0:
                st.warning(f"🚨 {num_choques} choques de salones detectados")
            else:
                st.success("✅ Sin choques de salones")
            
            # Clases pendientes de archivar
            pendientes = client.rpc("clases_pendientes_archivar").execute()
            if pendientes.data and pendientes.data[0]['total'] > 0:
                st.info(f"📦 {pendientes.data[0]['total']} clases vencidas pendientes de archivar")
            else:
                st.success("✅ Sin clases vencidas")
            
            # Datos inconsistentes
            inconsistentes = client.table("clases").select("crn", count="exact").eq("datos_consistentes", False).execute()
            if inconsistentes.count > 0:
                st.warning(f"⚠️ {inconsistentes.count} clases con datos inconsistentes")
            else:
                st.success("✅ Todos los datos consistentes")
        
        st.divider()
        
        # ===== SECCIÓN 3: Bienvenida =====
        st.markdown("""
        ### Bienvenido al sistema
        
        Usa el menú lateral izquierdo para navegar entre las diferentes secciones:
        
        - **🔍 Buscar clases** — Filtrar por maestro, materia, salón o periodo.
        - **👨‍🏫 Maestros** — Información docente y carga académica.
        - **🚪 Salones** — Ocupación y disponibilidad.
        - **📤 Subir Excel** — Carga masiva desde reportes de Banner.
        - **📊 Reportes** — Análisis y exportaciones.
        """)
    
    except Exception as e:
        st.error(f"❌ Error al conectar con la base de datos: {e}")
        st.info("Verifica que el archivo `.env` tenga las claves correctas de Supabase.")


if __name__ == "__main__":
    main()