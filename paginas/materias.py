"""
Página de materias: catálogo y grupos abiertos con salones.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.utils.queries import (
    buscar_materias_con_conteo, grupos_de_materia, cargar_periodos
)


DIAS_CORTO = {
    'LUNES': 'LUN', 'MARTES': 'MAR', 'MIERCOLES': 'MIÉ',
    'JUEVES': 'JUE', 'VIERNES': 'VIE', 'SABADO': 'SÁB', 'DOMINGO': 'DOM'
}
DIAS_ORDEN = ['LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO', 'DOMINGO']


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
    
    materias = buscar_materias_con_conteo(nombre_busqueda)
    
    if not materias:
        st.warning("⚠️ No se encontraron materias con ese criterio")
        return
    
    st.success(f"✅ {len(materias)} materias encontradas")
    
    # ===== SELECCIONAR MATERIA =====
    def formatear_opcion(m):
        """Genera el texto descriptivo de cada materia en el selector."""
        partes = [m['id'], m['descripcion']]
        
        if m.get('semanas_curso'):
            partes.append(f"{m['semanas_curso']} sem")
        
        num = m.get('num_grupos', 0)
        if num == 0:
            partes.append("Sin grupos")
        elif num == 1:
            partes.append("1 grupo")
        else:
            partes.append(f"{num} grupos")
        
        return " · ".join(partes)
    
    opciones = [formatear_opcion(m) for m in materias]
    seleccion = st.selectbox("Selecciona una materia para ver sus grupos", opciones)
    
    # El ID está al inicio antes del primer " · "
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
        horarios_grupo = g.get("horarios") or []
        
        # Ordenar horarios por día y hora
        horarios_ordenados = sorted(
            horarios_grupo,
            key=lambda h: (DIAS_ORDEN.index(h['dia_semana']) if h['dia_semana'] in DIAS_ORDEN else 99, h['hora_inicio'])
        )
        
        # Construir resumen de salones
        salones_usados = set()
        tiene_virtual = False
        
        for h in horarios_ordenados:
            if h.get('es_virtual'):
                tiene_virtual = True
            else:
                salon = h.get('salon_codigo')
                if salon:
                    salones_usados.add(salon)
        
        # Resumen de salones (sin repetir)
        if not salones_usados and tiene_virtual:
            salones_str = "🌐 Virtual"
        elif not salones_usados:
            salones_str = "Sin salón"
        elif len(salones_usados) == 1:
            salones_str = list(salones_usados)[0]
            if tiene_virtual:
                salones_str += " + 🌐 Virtual"
        else:
            salones_str = " · ".join(sorted(salones_usados))
            if tiene_virtual:
                salones_str += " + 🌐"
        
        filas.append({
            "CRN": g["crn"],
            "Periodo": g["periodo_id"],
            "Clave": g.get("clave_periodo") or "",
            "Grupo": g.get("grupo") or "",
            "Maestro": maestro.get("nombre_completo") or "Sin asignar",
            "Salones": salones_str,
            "Status": g.get("status") or "",
            "Inscritos": f"{g.get('inscritos', 0)}/{g.get('capacidad_materia', 0)}",
            "F. Inicio": g.get("fecha_inicio") or "",
            "F. Fin": g.get("fecha_fin") or ""
        })
    
    df = pd.DataFrame(filas)
    
    # Calcular altura exacta para evitar filas vacías
    altura_calc = 38 + (len(df) * 38) + 3
    altura_calc = min(altura_calc, 600)
    
    st.dataframe(df, use_container_width=True, hide_index=True, height=altura_calc)


main()