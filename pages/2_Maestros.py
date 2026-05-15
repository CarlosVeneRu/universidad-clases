"""
Página de maestros: búsqueda, lista y detalle con horario semanal.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.utils.queries import (
    buscar_maestros, clases_de_maestro, cargar_periodos
)


st.set_page_config(page_title="Maestros · UVM", page_icon="👨‍🏫", layout="wide")


def main():
    st.title("👨‍🏫 Maestros")
    st.markdown("Información docente y carga académica")
    st.divider()
    
    # ===== BÚSQUEDA =====
    col1, col2 = st.columns([3, 1])
    with col1:
        nombre_busqueda = st.text_input(
            "🔍 Buscar maestro por nombre", 
            placeholder="Escribe parte del nombre (ej: GONZALEZ, MARIA)..."
        )
    with col2:
        st.write("")
        st.write("")
        if st.button("📋 Ver todos los maestros", use_container_width=True):
            nombre_busqueda = " "  # Espacio para forzar mostrar todos
    
    # ===== LISTA DE RESULTADOS =====
    maestros = buscar_maestros(nombre_busqueda)
    
    if not maestros:
        if nombre_busqueda.strip():
            st.warning("⚠️ No se encontraron maestros con ese nombre")
        else:
            st.info("👆 Escribe un nombre para buscar maestros")
        return
    
    st.success(f"✅ {len(maestros)} maestros encontrados")
    
    # ===== SELECCIONAR MAESTRO =====
    opciones = [f"{m['clave']} · {m['nombre_completo']}" for m in maestros]
    seleccion = st.selectbox("Selecciona un maestro para ver detalle", opciones)
    
    maestro_clave = int(seleccion.split(" · ")[0])
    maestro_obj = next(m for m in maestros if m['clave'] == maestro_clave)
    
    st.divider()
    
    # ===== DETALLE DEL MAESTRO =====
    st.header(f"📋 {maestro_obj['nombre_completo']}")
    st.caption(f"Clave: {maestro_clave} · {'✅ Activo' if maestro_obj.get('activo') else '❌ Inactivo'}")
    
    # Selector de periodo
    periodos = cargar_periodos()
    opciones_periodo = ["Todos"] + [f"{p['id']}" for p in periodos]
    periodo_sel = st.selectbox("Filtrar por periodo", opciones_periodo)
    periodo_id = int(periodo_sel) if periodo_sel != "Todos" else None
    
    # Obtener clases del maestro
    clases = clases_de_maestro(maestro_clave, periodo_id)
    
    if not clases:
        st.info("Este maestro no tiene clases asignadas en el filtro seleccionado")
        return
    
    # ===== MÉTRICAS DE CARGA DOCENTE =====
    total_clases = len(clases)
    total_estudiantes = sum(c.get('inscritos', 0) for c in clases)
    
    # Calcular horas semanales totales
    horas_semanales = 0
    for c in clases:
        for h in (c.get('horarios') or []):
            try:
                from datetime import time
                hi = h['hora_inicio']
                hf = h['hora_fin']
                if isinstance(hi, str):
                    hi_parts = hi.split(':')
                    hf_parts = hf.split(':')
                    minutos = (int(hf_parts[0]) * 60 + int(hf_parts[1])) - (int(hi_parts[0]) * 60 + int(hi_parts[1]))
                    horas_semanales += minutos / 60
            except Exception:
                pass
    
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("📝 Clases asignadas", total_clases)
    with col_m2:
        st.metric("👥 Estudiantes totales", total_estudiantes)
    with col_m3:
        st.metric("⏰ Horas semanales", f"{horas_semanales:.1f} hrs")
    
    st.divider()
    
    # ===== TABLA DE CLASES =====
    st.subheader("📚 Clases que imparte")
    
    filas = []
    for c in clases:
        materia = c.get("materias") or {}
        horarios = c.get("horarios") or []
        
        # Construir resumen de horario
        horario_resumen = []
        for h in horarios:
            dia = h['dia_semana'][:3]  # LUN, MAR, etc.
            salon = h.get('salon_codigo') or "VIRTUAL"
            horario_resumen.append(f"{dia} {h['hora_inicio'][:5]}-{h['hora_fin'][:5]} ({salon})")
        
        filas.append({
            "CRN": c["crn"],
            "Periodo": c["periodo_id"],
            "Grupo": c.get("grupo") or "",
            "Materia": materia.get("descripcion") or "(sin materia)",
            "Inscritos": f"{c.get('inscritos', 0)}/{c.get('capacidad_materia', 0)}",
            "Status": c.get("status") or "",
            "Horario": "; ".join(horario_resumen) if horario_resumen else "Sin horario",
            "F. Inicio": c.get("fecha_inicio") or "",
            "F. Fin": c.get("fecha_fin") or ""
        })
    
    df = pd.DataFrame(filas)
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)


if __name__ == "__main__":
    main()