"""
Página de maestros: búsqueda, lista y detalle con horario semanal estilo tradicional.
Incluye descarga del horario en Excel.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.utils.ui import encabezado

from app.utils.queries import (
    buscar_maestros, clases_de_maestro, clases_agrupadas_de_maestro, cargar_periodos
)
from app.utils.horarios import (
    DIAS_ORDEN, DIAS_CORTO, hora_a_minutos,
    construir_horario_cuadricula, generar_excel_horario
)


def main():
    encabezado("Maestros", "Carga docente y horarios", "👨‍🏫")
    
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
            nombre_busqueda = " "
    
    maestros = buscar_maestros(nombre_busqueda)
    
    if not maestros:
        if nombre_busqueda.strip():
            st.warning("⚠️ No se encontraron maestros con ese nombre")
        else:
            st.info("👆 Escribe un nombre para buscar maestros")
        return
    
    st.success(f"✅ {len(maestros)} maestros encontrados")
    
    opciones = [f"{m['clave']} · {m['nombre_completo']}" for m in maestros]
    seleccion = st.selectbox("Selecciona un maestro para ver detalle", opciones)
    
    maestro_clave = int(seleccion.split(" · ")[0])
    maestro_obj = next(m for m in maestros if m['clave'] == maestro_clave)
    
    st.divider()
    
    # ===== DETALLE DEL MAESTRO =====
    st.header(f"📋 {maestro_obj['nombre_completo']}")
    st.caption(f"Clave: {maestro_clave} · {'✅ Activo' if maestro_obj.get('activo') else '❌ Inactivo'}")
    
    # Filtro de periodo + toggle agrupar
    periodos = cargar_periodos()
    
    col_per, col_tog = st.columns([2, 2])
    with col_per:
        opciones_periodo = ["Todos"] + [f"{p['id']}" for p in periodos]
        periodo_sel = st.selectbox("Filtrar por periodo", opciones_periodo)
        periodo_id = int(periodo_sel) if periodo_sel != "Todos" else None
    
    with col_tog:
        st.write("")
        ver_agrupado = st.toggle(
            "🔗 Ver clases agrupadas",
            value=True,
            help="Junta automáticamente los grupos divididos (ej: 17A + 17B = una sola clase)"
        )
    
    # Obtener clases
    if ver_agrupado:
        clases = clases_agrupadas_de_maestro(maestro_clave, periodo_id)
    else:
        clases = clases_de_maestro(maestro_clave, periodo_id)
        for c in clases:
            c['es_agrupada'] = False
            c['crns'] = [c['crn']]
            c['grupos'] = [c.get('grupo') or '']
            c['num_partes'] = 1
    
    if not clases:
        st.info("Este maestro no tiene clases asignadas en el filtro seleccionado")
        return
    
    # ===== MÉTRICAS DE CARGA DOCENTE =====
    total_clases = len(clases)
    total_estudiantes = sum(c.get('inscritos', 0) for c in clases)
    
    # Recolectar todos los horarios del maestro (con info enriquecida)
    todos_horarios = []
    for c in clases:
        materia_nombre = (c.get('materias') or {}).get('descripcion') or '(sin materia)'
        for h in (c.get('horarios') or []):
            h_copia = dict(h)
            h_copia['materia_nombre'] = materia_nombre
            todos_horarios.append(h_copia)
    
    # Calcular horas semanales (sumando todos los horarios)
    horas_semanales = 0
    for h in todos_horarios:
        try:
            ini = hora_a_minutos(h['hora_inicio'])
            fin = hora_a_minutos(h['hora_fin'])
            horas_semanales += (fin - ini) / 60
        except Exception:
            pass
    
    # Detectar salones únicos donde imparte
    salones_unicos = set(
        h.get('salon_codigo') for h in todos_horarios 
        if h.get('salon_codigo') and not h.get('es_virtual')
    )
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("📝 Clases asignadas", total_clases)
    with col_m2:
        st.metric("👥 Estudiantes totales", total_estudiantes)
    with col_m3:
        st.metric("⏰ Horas semanales", f"{horas_semanales:.1f} hrs")
    with col_m4:
        st.metric("🚪 Salones distintos", len(salones_unicos))
    
    st.divider()
    
    # ===== TABLA DE CLASES (LISTADO) =====
    st.subheader("📚 Clases que imparte")
    
    filas = []
    for c in clases:
        materia = c.get("materias") or {}
        horarios = c.get("horarios") or []
        
        # Construir resumen de horario
        horario_resumen = []
        for h in horarios:
            dia = h['dia_semana'][:3]
            salon = h.get('salon_codigo') or "🌐VIRTUAL"
            horario_resumen.append(f"{dia} {h['hora_inicio'][:5]}-{h['hora_fin'][:5]} ({salon})")
        
        if c.get('es_agrupada'):
            crns_str = f"🔗 {', '.join(str(x) for x in c['crns'])}"
            grupos_str = ', '.join(c['grupos'])
        else:
            crns_str = str(c['crns'][0]) if c.get('crns') else str(c.get('crn', ''))
            grupos_str = c['grupos'][0] if c.get('grupos') else c.get('grupo', '')
        
        filas.append({
            "CRN(s)": crns_str,
            "Periodo": c["periodo_id"],
            "Grupo(s)": grupos_str,
            "Materia": materia.get("descripcion") or "(sin materia)",
            "Inscritos": f"{c.get('inscritos', 0)}/{c.get('capacidad_materia', 0)}",
            "Status": c.get("status") or "",
            "Horario": "; ".join(horario_resumen) if horario_resumen else "Sin horario",
            "F. Inicio": c.get("fecha_inicio") or "",
            "F. Fin": c.get("fecha_fin") or ""
        })
    
    df_detalle = pd.DataFrame(filas)
    
    altura_calc = 38 + (len(df_detalle) * 38) + 3
    altura_calc = min(altura_calc, 500)
    
    st.dataframe(df_detalle, use_container_width=True, hide_index=True, height=altura_calc)
    
    if ver_agrupado:
        agrupadas = sum(1 for c in clases if c.get('es_agrupada'))
        if agrupadas > 0:
            st.caption(f"🔗 {agrupadas} de las {len(clases)} filas son clases agrupadas")
    
    st.divider()
    
    # ===== HORARIO SEMANAL TRADICIONAL =====
    st.subheader("📅 Horario semanal (vista tradicional)")
    st.caption("Vista hora por hora. Las celdas con — están libres. ⚠️ marca cuando el maestro tiene 2 clases al mismo tiempo.")
    
    if not todos_horarios:
        st.info("Este maestro no tiene horarios asignados")
        return
    
    df_cuadricula, info_choques = construir_horario_cuadricula(todos_horarios, etiqueta_extra="salon")
    
    if df_cuadricula is not None and not df_cuadricula.empty:
        altura_grid = 38 + (len(df_cuadricula) * 38) + 3
        
        st.dataframe(
            df_cuadricula,
            use_container_width=True,
            hide_index=True,
            height=altura_grid
        )
        
        # Alertas si el maestro tiene choques (imparte 2 clases al mismo tiempo)
        if info_choques:
            st.divider()
            st.warning(f"🚨 **Este maestro tiene {len(info_choques)} choques en su horario** (imparte 2 clases al mismo tiempo)")
            
            for choque in info_choques[:5]:  # Mostrar máximo 5
                c1 = choque['clase_1']
                c2 = choque['clase_2']
                
                with st.expander(f"⚠️ {choque['dia']} {c1['hora_inicio'][:5]} — Choque"):
                    col_c1, col_c2 = st.columns(2)
                    with col_c1:
                        st.markdown(f"**Materia 1:** {c1.get('materia_nombre', 'N/A')}")
                        st.markdown(f"**Horario:** {c1['hora_inicio'][:5]} - {c1['hora_fin'][:5]}")
                        st.markdown(f"**Salón:** {c1.get('salon_codigo') or '🌐 Virtual'}")
                    with col_c2:
                        st.markdown(f"**Materia 2:** {c2.get('materia_nombre', 'N/A')}")
                        st.markdown(f"**Horario:** {c2['hora_inicio'][:5]} - {c2['hora_fin'][:5]}")
                        st.markdown(f"**Salón:** {c2.get('salon_codigo') or '🌐 Virtual'}")
        
        # ===== BOTÓN DE DESCARGA EXCEL =====
        st.divider()
        st.subheader("📥 Descargar horario")
        
        info_resumen = {
            "Maestro": maestro_obj['nombre_completo'],
            "Clave": maestro_clave,
            "Periodo": periodo_sel,
            "Clases asignadas": total_clases,
            "Estudiantes totales": total_estudiantes,
            "Horas semanales": f"{horas_semanales:.1f} hrs",
            "Salones distintos": len(salones_unicos)
        }
        
        # Limpiar el nombre para el archivo (sin acentos ni espacios raros)
        nombre_archivo = maestro_obj['nombre_completo'].replace(' ', '_').replace(',', '')[:50]
        
        excel_bytes = generar_excel_horario(
            titulo="HORARIO DEL MAESTRO",
            subtitulo=maestro_obj['nombre_completo'],
            info_dict=info_resumen,
            df_detalle=df_detalle,
            df_cuadricula=df_cuadricula
        )
        
        st.download_button(
            label="📥 Descargar Horario en Excel",
            data=excel_bytes,
            file_name=f"horario_maestro_{nombre_archivo}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
    else:
        st.info("No hay datos suficientes para mostrar la cuadrícula")


main()