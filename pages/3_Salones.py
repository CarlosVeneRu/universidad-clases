"""
Página de salones: ocupación, disponibilidad y uso.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.utils.queries import (
    buscar_salones, clases_en_salon, cargar_periodos, cargar_tipos_salon
)


st.set_page_config(page_title="Salones · UVM", page_icon="🚪", layout="wide")


DIAS_ORDEN = ['LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO', 'DOMINGO']


def main():
    st.title("🚪 Salones")
    st.markdown("Información de salones físicos y su ocupación")
    st.divider()
    
    # ===== FILTROS =====
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        codigo_busqueda = st.text_input("🔍 Buscar por código", placeholder="Ej: 11-A001")
    with col2:
        tipos = cargar_tipos_salon()
        tipo_filtro = st.selectbox("🏷️ Tipo de salón", ["Todos"] + tipos)
    with col3:
        st.write("")
        st.write("")
        buscar = st.button("🔍 Buscar", type="primary", use_container_width=True)
    
    # ===== LISTA DE SALONES =====
    salones = buscar_salones(codigo_busqueda, tipo_filtro)
    
    if not salones:
        st.warning("⚠️ No se encontraron salones con esos filtros")
        return
    
    st.caption(f"📊 {len(salones)} salones encontrados")
    
    # ===== SELECCIONAR SALÓN =====
    opciones = [f"{s['codigo']} · {s.get('descripcion', '')} · Capacidad: {s.get('capacidad', 0)}" for s in salones]
    seleccion = st.selectbox("Selecciona un salón para ver su ocupación", opciones)
    
    salon_codigo = seleccion.split(" · ")[0]
    salon_obj = next(s for s in salones if s['codigo'] == salon_codigo)
    
    st.divider()
    
    # ===== DETALLE DEL SALÓN =====
    st.header(f"🚪 {salon_obj['codigo']}")
    
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("📝 Descripción", salon_obj.get('descripcion', 'N/A'))
    with col_m2:
        st.metric("👥 Capacidad", salon_obj.get('capacidad', 0))
    with col_m3:
        st.metric("🏷️ Tipo", salon_obj.get('tipo_uso_descripcion', 'N/A'))
    
    # Filtro de periodo
    periodos = cargar_periodos()
    opciones_periodo = ["Todos"] + [f"{p['id']}" for p in periodos]
    periodo_sel = st.selectbox("Filtrar por periodo", opciones_periodo, key="periodo_salon")
    periodo_id = int(periodo_sel) if periodo_sel != "Todos" else None
    
    # Obtener ocupación
    horarios = clases_en_salon(salon_codigo, periodo_id)
    
    if not horarios:
        st.info("Este salón no tiene clases asignadas en el filtro seleccionado")
        return
    
    # ===== MÉTRICAS DE USO =====
    # Calcular horas de uso por semana
    horas_uso = 0
    for h in horarios:
        try:
            hi = h['hora_inicio'].split(':')
            hf = h['hora_fin'].split(':')
            minutos = (int(hf[0]) * 60 + int(hf[1])) - (int(hi[0]) * 60 + int(hi[1]))
            horas_uso += minutos / 60
        except Exception:
            pass
    
    # Horas disponibles teóricas (lun-sab 7am-10pm = 15hrs x 6 días = 90 hrs)
    horas_disponibles = 90
    porcentaje_uso = (horas_uso / horas_disponibles * 100) if horas_disponibles > 0 else 0
    
    col_u1, col_u2, col_u3 = st.columns(3)
    with col_u1:
        st.metric("📊 Clases asignadas", len(set((h['crn'], h['periodo_id']) for h in horarios)))
    with col_u2:
        st.metric("⏰ Horas/semana", f"{horas_uso:.1f}")
    with col_u3:
        st.metric("📈 % de uso", f"{porcentaje_uso:.1f}%")
    
    # Barra visual de ocupación
    st.progress(min(porcentaje_uso / 100, 1.0), text=f"Ocupación semanal: {porcentaje_uso:.1f}% (de 90 hrs/semana disponibles)")
    
    st.divider()
    
    # ===== HORARIO SEMANAL VISUAL =====
    st.subheader("📅 Ocupación semanal")
    
    # Ordenar horarios por día y hora
    horarios_ordenados = sorted(
        horarios, 
        key=lambda h: (DIAS_ORDEN.index(h['dia_semana']) if h['dia_semana'] in DIAS_ORDEN else 99, h['hora_inicio'])
    )
    
    filas = []
    for h in horarios_ordenados:
        clase_info = h.get('clases') or {}
        materia = (clase_info.get('materias') or {})
        maestro = (clase_info.get('maestros') or {})
        
        filas.append({
            "Día": h['dia_semana'],
            "Hora": f"{h['hora_inicio'][:5]} - {h['hora_fin'][:5]}",
            "CRN": h['crn'],
            "Periodo": h['periodo_id'],
            "Grupo": clase_info.get('grupo') or '',
            "Materia": materia.get('descripcion') or '(multi)',
            "Maestro": maestro.get('nombre_completo') or 'Sin asignar'
        })
    
    df = pd.DataFrame(filas)
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)


if __name__ == "__main__":
    main()