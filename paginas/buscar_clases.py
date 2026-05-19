"""
Página de búsqueda avanzada de clases.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.utils.queries import (
    get_client, cargar_periodos, buscar_maestros, buscar_materias
)


def buscar_clases_avanzado(filtros):
    """Busca clases con todos los filtros aplicados."""
    client = get_client()
    
    query = client.table("clases").select(
        "crn, periodo_id, grupo, clave_periodo, status, "
        "fecha_inicio, fecha_fin, inscritos, capacidad_materia, vacantes, "
        "tipo_curso, sin_docente, sin_horario, "
        "materias(id, descripcion), "
        "maestros(clave, nombre_completo)"
    )
    
    if filtros.get("periodo_id"):
        query = query.eq("periodo_id", filtros["periodo_id"])
    
    if filtros.get("clave_periodo"):
        query = query.eq("clave_periodo", filtros["clave_periodo"])
    
    if filtros.get("status"):
        query = query.eq("status", filtros["status"])
    
    if filtros.get("crn"):
        query = query.eq("crn", filtros["crn"])
    
    if filtros.get("maestro_clave"):
        query = query.eq("maestro_clave", filtros["maestro_clave"])
    
    if filtros.get("materia_id"):
        query = query.eq("materia_id", filtros["materia_id"])
    
    if filtros.get("solo_sin_docente"):
        query = query.eq("sin_docente", True)
    
    if filtros.get("solo_sin_horario"):
        query = query.eq("sin_horario", True)
    
    query = query.limit(1000)
    
    return query.execute().data


def main():
    st.title("🔍 Buscar Clases")
    st.markdown("Búsqueda avanzada con múltiples filtros")
    st.divider()
    
    # Cargar opciones
    periodos = cargar_periodos()
    
    # ===== FILTROS PRINCIPALES =====
    st.subheader("🎯 Filtros principales")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Periodo
        opciones_periodo = ["Todos"] + [f"{p['id']}" for p in periodos]
        periodo_sel = st.selectbox("📅 Periodo", opciones_periodo)
        periodo_id = int(periodo_sel) if periodo_sel != "Todos" else None
        
        # Mostrar las claves de ese periodo
        clave_periodo = None
        if periodo_id:
            periodo_obj = next((p for p in periodos if p['id'] == periodo_id), None)
            if periodo_obj and periodo_obj.get('descripcion'):
                claves_disponibles = ["Todas"] + periodo_obj['descripcion'].split(',')
                clave_sel = st.selectbox("🏷️ Clave del periodo", claves_disponibles)
                if clave_sel != "Todas":
                    clave_periodo = clave_sel.strip()
    
    with col2:
        # Status
        status_sel = st.selectbox("📊 Status", ["Todos", "A (Activa)", "R (Reservada)"])
        status = None
        if status_sel.startswith("A"):
            status = "A"
        elif status_sel.startswith("R"):
            status = "R"
        
        # CRN específico
        crn_input = st.text_input("🔢 CRN específico", placeholder="Ej: 6971")
        crn_filter = int(crn_input.strip()) if crn_input.strip().isdigit() else None
    
    with col3:
        # Búsqueda por maestro
        maestro_busqueda = st.text_input("👨‍🏫 Buscar maestro", placeholder="Nombre del maestro")
        maestro_clave = None
        if maestro_busqueda.strip() and len(maestro_busqueda.strip()) >= 3:
            maestros_encontrados = buscar_maestros(maestro_busqueda)
            if maestros_encontrados:
                opciones_maestro = ["Cualquiera"] + [f"{m['clave']} - {m['nombre_completo']}" for m in maestros_encontrados]
                maestro_sel = st.selectbox(f"Seleccionar ({len(maestros_encontrados)} encontrados)", opciones_maestro)
                if maestro_sel != "Cualquiera":
                    maestro_clave = int(maestro_sel.split(" - ")[0])
        
        # Búsqueda por materia
        materia_busqueda = st.text_input("📚 Buscar materia", placeholder="Nombre o ID de materia")
        materia_id = None
        if materia_busqueda.strip() and len(materia_busqueda.strip()) >= 3:
            materias_encontradas = buscar_materias(materia_busqueda)
            if materias_encontradas:
                opciones_materia = ["Cualquiera"] + [f"{m['id']} - {m['descripcion']}" for m in materias_encontradas]
                materia_sel = st.selectbox(f"Seleccionar ({len(materias_encontradas)} encontradas)", opciones_materia)
                if materia_sel != "Cualquiera":
                    materia_id = materia_sel.split(" - ")[0]
    
    # Filtros avanzados (expandible)
    with st.expander("🔧 Filtros avanzados"):
        col_a, col_b = st.columns(2)
        with col_a:
            solo_sin_docente = st.checkbox("Solo clases sin docente asignado")
        with col_b:
            solo_sin_horario = st.checkbox("Solo clases sin horario asignado")
    
    st.divider()
    
    # Botón de búsqueda
    col_btn1, col_btn2 = st.columns([1, 5])
    with col_btn1:
        buscar = st.button("🔍 Buscar", type="primary", use_container_width=True)
    with col_btn2:
        if st.button("🔄 Limpiar filtros", use_container_width=False):
            st.rerun()
    
    # ===== EJECUTAR BÚSQUEDA =====
    if buscar:
        with st.spinner("Buscando..."):
            filtros = {
                "periodo_id": periodo_id,
                "clave_periodo": clave_periodo,
                "status": status,
                "crn": crn_filter,
                "maestro_clave": maestro_clave,
                "materia_id": materia_id,
                "solo_sin_docente": solo_sin_docente,
                "solo_sin_horario": solo_sin_horario
            }
            
            resultados = buscar_clases_avanzado(filtros)
            
            if resultados:
                # Métricas rápidas
                total = len(resultados)
                con_inscritos = sum(1 for r in resultados if r.get('inscritos', 0) > 0)
                total_inscritos = sum(r.get('inscritos', 0) for r in resultados)
                
                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    st.metric("📝 Clases encontradas", total)
                with col_m2:
                    st.metric("✅ Con inscritos", con_inscritos)
                with col_m3:
                    st.metric("👥 Total estudiantes", total_inscritos)
                
                st.divider()
                
                # Tabla de resultados
                filas = []
                for c in resultados:
                    materia = c.get("materias") or {}
                    maestro = c.get("maestros") or {}
                    
                    filas.append({
                        "CRN": c["crn"],
                        "Periodo": c["periodo_id"],
                        "Clave": c.get("clave_periodo") or "",
                        "Grupo": c.get("grupo") or "",
                        "Materia": materia.get("descripcion") or "(multi)",
                        "Maestro": maestro.get("nombre_completo") or "Sin asignar",
                        "Status": c.get("status") or "",
                        "Inscritos/Cap": f"{c.get('inscritos', 0)}/{c.get('capacidad_materia', 0)}",
                        "F. Inicio": c.get("fecha_inicio") or "",
                        "F. Fin": c.get("fecha_fin") or ""
                    })
                
                df = pd.DataFrame(filas)
                st.dataframe(df, use_container_width=True, hide_index=True, height=500)
                
                st.caption(f"Mostrando hasta 1000 resultados. Refina los filtros para resultados más específicos.")
            else:
                st.warning("⚠️ No se encontraron clases con esos filtros")
    else:
        st.info("👆 Selecciona filtros y haz clic en **Buscar** para ver las clases")


main()