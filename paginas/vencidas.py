"""
Página de clases vencidas (pendientes de archivar).
Muestra las clases cuya fecha_fin ya pasó.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from datetime import date
from app.utils.queries import get_client


def main():
    st.title("📦 Clases Vencidas")
    st.markdown("Clases cuya fecha de fin ya pasó y están pendientes de archivar")
    st.divider()
    
    client = get_client()
    
    # Obtener clases vencidas con detalle
    hoy = date.today().isoformat()
    
    with st.spinner("Cargando clases vencidas..."):
        res = client.table("clases").select(
            "crn, periodo_id, grupo, clave_periodo, status, "
            "fecha_inicio, fecha_fin, inscritos, capacidad_materia, "
            "materias(descripcion), "
            "maestros(nombre_completo), "
            "carreras(nombre_banner, programas(nombre, nivel_codigo))"
        ).lt("fecha_fin", hoy).order("fecha_fin", desc=True).execute()
    
    vencidas = res.data
    
    if not vencidas:
        st.success("✅ ¡Excelente! No hay clases vencidas pendientes de archivar.")
        return
    
    # Métricas
    total = len(vencidas)
    fecha_mas_antigua = min(v['fecha_fin'] for v in vencidas)
    fecha_mas_reciente = max(v['fecha_fin'] for v in vencidas)
    total_estudiantes = sum(v.get('inscritos', 0) for v in vencidas)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📦 Total vencidas", total)
    with col2:
        st.metric("📅 Más antigua", fecha_mas_antigua)
    with col3:
        st.metric("📅 Más reciente", fecha_mas_reciente)
    with col4:
        st.metric("👥 Estudiantes afectados", total_estudiantes)
    
    st.divider()
    
    # Distribución por periodo
    st.subheader("📊 Distribución por periodo")
    por_periodo = {}
    for v in vencidas:
        per = v['periodo_id']
        por_periodo[per] = por_periodo.get(per, 0) + 1
    
    cols = st.columns(len(por_periodo))
    for i, (per, cant) in enumerate(sorted(por_periodo.items())):
        with cols[i]:
            st.metric(f"Periodo {per}", cant)
    
    st.divider()
    
    # Tabla de clases vencidas
    st.subheader("📋 Listado de clases vencidas")
    
    filas = []
    for v in vencidas:
        materia = v.get("materias") or {}
        maestro = v.get("maestros") or {}
        carrera = v.get("carreras") or {}
        programa_info = (carrera.get("programas") or {}) if carrera else {}
        
        filas.append({
            "CRN": v["crn"],
            "Periodo": v["periodo_id"],
            "Clave": v.get("clave_periodo") or "",
            "Grupo": v.get("grupo") or "",
            "Materia": materia.get("descripcion") or "(multi)",
            "Maestro": maestro.get("nombre_completo") or "Sin asignar",
            "Programa": programa_info.get("nombre") or "(multi-carrera)",
            "F. Inicio": v.get("fecha_inicio") or "",
            "F. Fin": v.get("fecha_fin") or "",
            "Inscritos": v.get("inscritos", 0)
        })
    
    df = pd.DataFrame(filas)
    
    altura_calc = 38 + (len(df) * 38) + 3
    altura_calc = min(altura_calc, 600)
    
    st.dataframe(df, use_container_width=True, hide_index=True, height=altura_calc)
    
    # Acción de archivado
    st.divider()
    st.subheader("📦 Archivar clases vencidas")
    
    st.warning(
        "⚠️ **Al archivar, las clases se moverán de la tabla activa a la tabla de archivo. "
        "Sus horarios se borrarán pero quedará un snapshot. Esta acción NO se puede deshacer.**"
    )
    
    st.info(
        "🔒 **Por seguridad, esta acción aún NO está disponible desde la interfaz web.** "
        "Se habilitará en la Fase 7 cuando agreguemos login y permisos de usuario."
    )


main()