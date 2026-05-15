"""
Página de materias: catálogo y grupos abiertos.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.utils.queries import (
    buscar_materias, grupos_de_materia, cargar_periodos
)


st.set_page_config(page_title="Materias · UVM", page_icon="📚", layout="wide")


def main():
    st.title("📚 Materias")
    st.markdown("Catálogo de materias y sus grupos abiertos")
    st.divider()
    
    # ===== BÚSQUEDA =====
    nombre_busqueda = st.text_input(
        "🔍 Buscar materia",
        placeholder="Escribe parte del nombre o ID (ej: BIOLOGY, MATE, PBIO0402B)..."
    )
    
    if not nombre_busqueda.strip() or len(nombre_busqueda.strip()) < 2:
        st.info("👆 Escribe al menos 2 caracteres para buscar materias")
        return
    
    materias = buscar_materias(nombre_busqueda)
    
    if not materias:
        st.warning("⚠️ No se encontraron materias con ese criterio")
        return
    
    st.success(f"✅ {len(materias)} materias encontradas")
    
    # ===== SELECCIONAR MATERIA =====
    opciones = [f"{m['id']} · {m['descripcion']}" for m in materias]
    seleccion = st.selectbox("Selecciona una materia para ver sus grupos", opciones)
    
    materia_id = seleccion.split(" · ")[0]
    materia_obj = next(m for m in materias if m['id'] == materia_id)
    
    st.divider()
    
    # ===== DETALLE DE LA MATERIA =====
    st.header(f"📚 {materia_obj['descripcion']}")
    st.caption(f"ID: {materia_id}")
    
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("🎓 Grado", materia_obj.get('grado_materia') or 'N/A')
    with col_m2:
        st.metric("📅 Semanas", materia_obj.get('semanas_curso') or 'N/A')
    with col_m3:
        st.metric("🔬 Área", materia_obj.get('area_concentracion') or 'N/A')
    
    # Filtro de periodo
    periodos = cargar_periodos()
    opciones_periodo = ["Todos"] + [f"{p['id']}" for p in periodos]
    periodo_sel = st.selectbox("Filtrar por periodo", opciones_periodo, key="periodo_materia")
    periodo_id = int(periodo_sel) if periodo_sel != "Todos" else None
    
    grupos = grupos_de_materia(materia_id, periodo_id)
    
    if not grupos:
        st.info("Esta materia no tiene grupos en el filtro seleccionado")
        return
    
    st.divider()
    
    # ===== MÉTRICAS DE GRUPOS =====
    total_grupos = len(grupos)
    total_inscritos = sum(g.get('inscritos', 0) for g in grupos)
    total_capacidad = sum(g.get('capacidad_materia', 0) for g in grupos)
    porcentaje_lleno = (total_inscritos / total_capacidad * 100) if total_capacidad > 0 else 0
    
    col_g1, col_g2, col_g3, col_g4 = st.columns(4)
    with col_g1:
        st.metric("📋 Total grupos", total_grupos)
    with col_g2:
        st.metric("👥 Inscritos", total_inscritos)
    with col_g3:
        st.metric("🪑 Capacidad", total_capacidad)
    with col_g4:
        st.metric("📊 Lleno", f"{porcentaje_lleno:.1f}%")
    
    st.subheader("📋 Grupos disponibles")
    
    filas = []
    for g in grupos:
        maestro = g.get("maestros") or {}
        filas.append({
            "CRN": g["crn"],
            "Periodo": g["periodo_id"],
            "Clave": g.get("clave_periodo") or "",
            "Grupo": g.get("grupo") or "",
            "Maestro": maestro.get("nombre_completo") or "Sin asignar",
            "Status": g.get("status") or "",
            "Inscritos": f"{g.get('inscritos', 0)}/{g.get('capacidad_materia', 0)}",
            "F. Inicio": g.get("fecha_inicio") or "",
            "F. Fin": g.get("fecha_fin") or ""
        })
    
    df = pd.DataFrame(filas)
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)


if __name__ == "__main__":
    main()