"""
Página de búsqueda de clases con filtros.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
from app.utils.supabase_client import get_supabase_client


@st.cache_resource
def init_supabase():
    return get_supabase_client()


@st.cache_data(ttl=300)  # cache por 5 minutos
def cargar_listas_filtros():
    """Carga las listas para los selectores (periodos, status, etc.)"""
    client = init_supabase()
    
    periodos = client.table("periodos").select("*").order("id").execute()
    
    return {
        "periodos": periodos.data,
    }


def buscar_clases(filtros):
    """Busca clases aplicando los filtros seleccionados."""
    client = init_supabase()
    
    # Construir la query base con JOINs a las tablas relacionadas
    query = client.table("clases").select(
        "crn, periodo_id, grupo, clave_periodo, status, "
        "fecha_inicio, fecha_fin, inscritos, capacidad_materia, vacantes, "
        "materias(id, descripcion), "
        "maestros(clave, nombre_completo)"
    )
    
    # Aplicar filtros
    if filtros.get("periodo_id"):
        query = query.eq("periodo_id", filtros["periodo_id"])
    
    if filtros.get("status"):
        query = query.eq("status", filtros["status"])
    
    if filtros.get("crn"):
        query = query.eq("crn", filtros["crn"])
    
    # Limitar resultados
    query = query.limit(500)
    
    result = query.execute()
    return result.data


def main():
    st.set_page_config(
        page_title="Buscar Clases · UVM",
        page_icon="🔍",
        layout="wide"
    )
    
    st.title("🔍 Buscar Clases")
    st.markdown("Busca y filtra clases por diferentes criterios")
    st.divider()
    
    # Cargar listas para selectores
    listas = cargar_listas_filtros()
    
    # ===== SECCIÓN DE FILTROS =====
    st.subheader("🎯 Filtros")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # Filtro por periodo
        opciones_periodo = ["Todos"] + [f"{p['id']} - {p['descripcion']}" for p in listas["periodos"]]
        periodo_sel = st.selectbox("Periodo", opciones_periodo)
        periodo_id = None
        if periodo_sel != "Todos":
            periodo_id = int(periodo_sel.split(" - ")[0])
    
    with col2:
        # Filtro por status
        status_sel = st.selectbox("Status", ["Todos", "A (Activa)", "R (Reservada)"])
        status = None
        if status_sel == "A (Activa)":
            status = "A"
        elif status_sel == "R (Reservada)":
            status = "R"
    
    with col3:
        # Buscar por CRN específico
        crn_input = st.text_input("Buscar por CRN", placeholder="Ej: 6971")
        crn_filter = None
        if crn_input.strip().isdigit():
            crn_filter = int(crn_input.strip())
    
    with col4:
        st.write("")  # Espaciador
        st.write("")
        buscar = st.button("🔍 Buscar", type="primary", use_container_width=True)
    
    st.divider()
    
    # ===== EJECUTAR BÚSQUEDA =====
    if buscar or crn_filter or periodo_id or status:
        with st.spinner("Buscando clases..."):
            filtros = {
                "periodo_id": periodo_id,
                "status": status,
                "crn": crn_filter
            }
            
            resultados = buscar_clases(filtros)
            
            if resultados:
                st.success(f"✅ Se encontraron **{len(resultados)}** clases")
                
                # Convertir a DataFrame para mostrar bonito
                filas = []
                for c in resultados:
                    materia = c.get("materias", {})
                    maestro = c.get("maestros", {})
                    
                    filas.append({
                        "CRN": c["crn"],
                        "Periodo": c["periodo_id"],
                        "Clave": c.get("clave_periodo", ""),
                        "Grupo": c.get("grupo", ""),
                        "Materia ID": materia.get("id", "") if materia else "",
                        "Materia": materia.get("descripcion", "") if materia else "(multi)",
                        "Maestro": maestro.get("nombre_completo", "Sin asignar") if maestro else "Sin asignar",
                        "Status": c.get("status", ""),
                        "Inscritos": c.get("inscritos", 0),
                        "Capacidad": c.get("capacidad_materia", 0),
                        "Fecha Inicio": c.get("fecha_inicio", ""),
                        "Fecha Fin": c.get("fecha_fin", "")
                    })
                
                df = pd.DataFrame(filas)
                
                # Mostrar tabla
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Información adicional
                st.caption(f"Mostrando hasta 500 resultados. Refina los filtros para obtener resultados más específicos.")
            else:
                st.warning("⚠️ No se encontraron clases con esos filtros")
    else:
        st.info("👆 Selecciona filtros y haz clic en **Buscar** para ver las clases")


if __name__ == "__main__":
    main()