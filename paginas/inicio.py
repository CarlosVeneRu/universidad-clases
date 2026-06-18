"""
Página de Inicio: Dashboard con resumen general del sistema.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from app.utils.queries import get_client
from app.utils.ui import encabezado

def main():
    encabezado(
    "Sistema de Gestión de Clases",
    "Universidad del Valle de México · Campus Querétaro",
    "🎓"
)
    
    try:
        client = get_client()
        
        st.subheader("📊 Resumen general")
        
        col1, col2, col3, col4 = st.columns(4)
        
        # Obtener métricas básicas
        clases_total = client.table("clases").select("crn", count="exact").execute().count
        maestros_total = client.table("maestros").select("clave", count="exact").execute().count
        materias_total = client.table("materias").select("id", count="exact").execute().count
        salones_total = client.table("salones").select("codigo", count="exact").execute().count
        
        # Calcular clases agrupadas
        agrupadas = client.table("clases_agrupadas").select("num_partes").execute().data
        num_grupos_agrupables = len(agrupadas)
        clases_en_grupos = sum(g['num_partes'] for g in agrupadas)
        # "Clases reales" = (total - clases que se agrupan) + (grupos como una sola)
        clases_reales = clases_total - clases_en_grupos + num_grupos_agrupables
        
        with col1:
            st.metric(
                "📝 Clases activas",
                clases_total,
                delta=f"{clases_reales} agrupadas",
                delta_color="off",
                help=f"Total de registros: {clases_total}. Si se agrupan las divididas, son {clases_reales} clases reales."
            )
        
        with col2:
            st.metric("👨‍🏫 Maestros", maestros_total)
        
        with col3:
            st.metric("📚 Materias", materias_total)
        
        with col4:
            st.metric("🚪 Salones físicos", salones_total)
        
        st.divider()
        
        col_izq, col_der = st.columns(2)
        
        with col_izq:
            st.subheader("📅 Periodos académicos")
            periodos = client.table("periodos").select("*").order("id").execute()
            for p in periodos.data:
                st.markdown(f"**{p['id']}** · {p['descripcion']}")
        
        with col_der:
            st.subheader("⚠️ Alertas del sistema")
            
            # CHOQUES DE SALONES (clickeable)
            choques_rpc = client.rpc("detectar_choques_salon").execute()
            num_choques = len(set((c['crn_1'], c['crn_2']) for c in choques_rpc.data)) if choques_rpc.data else 0
            
            if num_choques > 0:
                st.warning(f"🚨 {num_choques} choques de salones detectados")
                if st.button("🔍 Ver detalle de choques", key="btn_choques", use_container_width=True):
                    st.switch_page("paginas/choques.py")
            else:
                st.success("✅ Sin choques de salones")
            
            # CLASES VENCIDAS (clickeable)
            pendientes = client.rpc("clases_pendientes_archivar").execute()
            num_vencidas = pendientes.data[0]['total'] if pendientes.data and pendientes.data[0]['total'] > 0 else 0
            
            if num_vencidas > 0:
                st.info(f"📦 {num_vencidas} clases vencidas pendientes de archivar")
                if st.button("📋 Ver clases vencidas", key="btn_vencidas", use_container_width=True):
                    st.switch_page("paginas/vencidas.py")
            else:
                st.success("✅ Sin clases vencidas")
            
            # DATOS INCONSISTENTES
            inconsistentes = client.table("clases").select("crn", count="exact").eq("datos_consistentes", False).execute()
            if inconsistentes.count > 0:
                st.warning(f"⚠️ {inconsistentes.count} clases con datos inconsistentes")
            else:
                st.success("✅ Todos los datos consistentes")
            
            # Info sobre agrupamiento
            if num_grupos_agrupables > 0:
                st.info(
                    f"🔗 **{num_grupos_agrupables} clases** están divididas en **{clases_en_grupos} registros** del sistema. "
                    f"Activa el toggle '🔗 Ver clases agrupadas' en las páginas para consolidarlas."
                )
        
        st.divider()
        
        st.markdown("""
        ### Bienvenido al sistema
        
        Usa el menú lateral izquierdo para navegar entre las secciones.
        """)
    
    except Exception as e:
        st.error(f"❌ Error al conectar con la base de datos: {e}")


main()