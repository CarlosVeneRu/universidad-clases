"""
Página de clases vencidas con filtros, gráficas y visualización mejorada.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from app.utils.queries import get_client, cargar_niveles, cargar_programas
from app.utils.ui import encabezado

NIVELES_LEGIBLES = {
    "LX": "Licenciatura Ejecutiva",
    "NC": "Ciencias de la Salud",
    "PT": "Posgrado / Maestría",
    "L6": "Licenciatura",
    "LS": "Licenciatura",
    "B6": "Bachillerato",
    "6B": "Bachillerato",
}

def _codigo_nivel(clave):
    """De una clave de periodo (ej '1LX', 'BL6') saca el código de nivel (LX, L6...)."""
    clave = str(clave).strip().upper()
    for cod in NIVELES_LEGIBLES:
        if cod in clave:
            return cod
    return None

@st.cache_data(ttl=120)
def cargar_clases_agrupadas_dict():
    """Mapea CRN+periodo -> grupo_id, y devuelve info de cada grupo."""
    client = get_client()
    res = client.table("clases_agrupadas").select(
        "grupo_id, crns, periodo_id, inscritos_total, capacidad_total"
    ).execute()
    
    crn_a_grupo = {}
    info_grupos = {}
    
    for g in res.data:
        for crn in g['crns']:
            crn_a_grupo[(crn, g['periodo_id'])] = g['grupo_id']
        info_grupos[g['grupo_id']] = {
            'inscritos_total': g['inscritos_total'],
            'capacidad_total': g['capacidad_total']
        }
    
    return crn_a_grupo, info_grupos


def aplicar_agrupamiento_df(df):
    """
    Toma el DataFrame de vencidas y agrupa las clases que son la misma.
    """
    crn_a_grupo, info_grupos = cargar_clases_agrupadas_dict()
    if not crn_a_grupo:
        return df
    
    df = df.copy()
    df['_grupo_id'] = df.apply(
        lambda row: crn_a_grupo.get((row['CRN'], row['Periodo']), None),
        axis=1
    )
    
    # Las que no están agrupadas: quedan como están
    df_no_agrupadas = df[df['_grupo_id'].isna()].copy()
    
    # Las agrupadas: tomar la primera de cada grupo y usar inscritos_total
    df_agrupadas = df[df['_grupo_id'].notna()].copy()
    df_agrupadas = df_agrupadas.drop_duplicates(subset='_grupo_id', keep='first')
    
    df_agrupadas['Inscritos'] = df_agrupadas['_grupo_id'].map(
        lambda gid: info_grupos.get(gid, {}).get('inscritos_total', 0)
    )
    
    resultado = pd.concat([df_no_agrupadas, df_agrupadas], ignore_index=True)
    resultado = resultado.drop(columns=['_grupo_id'])
    return resultado


def main():
    encabezado(
    "Clases Vencidas",
    "Clases cuya fecha de fin ya pasó y están pendientes de archivar",
    "📦"
)
    
    client = get_client()
    
    # ============================================
    # CARGAR DATOS (con paginación segura)
    # ============================================
    hoy = date.today().isoformat()
    
    with st.spinner("Cargando clases vencidas..."):
        vencidas = []
        offset = 0
        while True:
            batch = client.table("clases").select(
                "crn, periodo_id, grupo, clave_periodo, status, "
                "fecha_inicio, fecha_fin, inscritos, capacidad_materia, "
                "carrera_id, materia_id, maestro_clave, "
                "materias(descripcion), "
                "maestros(nombre_completo), "
                "carreras(nombre_banner, programa_clave, programas(nombre, nivel_codigo))"
            ).lt("fecha_fin", hoy).order("fecha_fin", desc=True).order("crn").range(offset, offset + 999).execute()
            if not batch.data:
                break
            vencidas.extend(batch.data)
            if len(batch.data) < 1000:
                break
            offset += 1000
    
    if not vencidas:
        st.success("✅ ¡Excelente! No hay clases vencidas pendientes de archivar.")
        return
    
    # ============================================
    # PREPARAR DATAFRAME PARA FILTRAR
    # ============================================
    filas = []
    for v in vencidas:
        materia = v.get("materias") or {}
        maestro = v.get("maestros") or {}
        carrera = v.get("carreras") or {}
        programa_info = (carrera.get("programas") or {}) if carrera else {}
        
        fecha_fin = v.get('fecha_fin')
        dias_vencida = 0
        if fecha_fin:
            try:
                dias_vencida = (date.today() - date.fromisoformat(fecha_fin)).days
            except Exception:
                pass
        
        filas.append({
            "CRN": v["crn"],
            "Periodo": v["periodo_id"],
            "Clave": v.get("clave_periodo") or "",
            "Grupo": v.get("grupo") or "",
            "Materia_ID": v.get("materia_id") or "",
            "Materia": materia.get("descripcion") or "(multi)",
            "Maestro_Clave": v.get("maestro_clave"),
            "Maestro": maestro.get("nombre_completo") or "Sin asignar",
            "Carrera_ID": v.get("carrera_id"),
            "Programa_Clave": carrera.get("programa_clave") or "",
            "Programa": programa_info.get("nombre") or "(multi-carrera)",
            "Nivel": programa_info.get("nivel_codigo") or "—",
            "F. Inicio": v.get("fecha_inicio") or "",
            "F. Fin": fecha_fin or "",
            "Dias_Vencida": dias_vencida,
            "Inscritos": v.get("inscritos", 0) or 0,
            "Status": v.get("status") or ""
        })
    
    df = pd.DataFrame(filas)
    
    # Etiqueta de nivel por periodo (para que no se vea solo el número)
    mapa_periodo_nivel = {}
    for per, grupo in df.groupby('Periodo'):
        codigos = sorted({c for c in (_codigo_nivel(k) for k in grupo['Clave']) if c})
        if codigos:
            mapa_periodo_nivel[per] = f"{NIVELES_LEGIBLES[codigos[0]]} ({', '.join(codigos)})"
        else:
            mapa_periodo_nivel[per] = str(per)
    df['Periodo_Nivel'] = df['Periodo'].map(mapa_periodo_nivel)
    
    # ============================================
    # TOGGLE DE CLASES AGRUPADAS
    # ============================================
    col_tog, _ = st.columns([1, 3])
    with col_tog:
        aplicar_agrup = st.toggle(
            "🔗 Considerar clases agrupadas",
            value=True,
            help="Cuando está activado, las clases divididas (mismo CRN administrativo) cuentan como UNA sola. Los inscritos NO se suman dos veces."
        )
    
    if aplicar_agrup:
        df = aplicar_agrupamiento_df(df)
    
    # ============================================
    # FILTROS
    # ============================================
    st.subheader("🎯 Filtros")
    
    col_f1, col_f2 = st.columns(2)
    
    with col_f1:
        # Filtro por periodo
        periodos_disp = sorted(df['Periodo'].unique().tolist())
        opciones_periodo = ["📅 Todos los periodos"] + [str(p) for p in periodos_disp]
        periodo_sel = st.selectbox("📅 Periodo:", opciones_periodo, key="filtro_per_venc")
        
        # Filtro por nivel
        niveles_disp = sorted(df['Nivel'].unique().tolist())
        opciones_nivel = ["🎓 Todos los niveles"] + niveles_disp
        nivel_sel = st.selectbox("🎓 Nivel académico:", opciones_nivel, key="filtro_niv_venc")
    
    with col_f2:
        # Filtro por programa
        programas_disp = sorted([p for p in df['Programa'].unique().tolist() if p != '(multi-carrera)'])
        opciones_programa = ["📚 Todos los programas"] + programas_disp + ["❓ Solo multi-carrera"]
        programa_sel = st.selectbox("📚 Programa:", opciones_programa, key="filtro_prog_venc")
        
        # Búsqueda por texto
        busqueda = st.text_input("🔍 Buscar (maestro, materia o CRN):", "", key="busq_venc")
    
    # Aplicar filtros
    df_filt = df.copy()
    
    if not periodo_sel.startswith("📅 Todos"):
        df_filt = df_filt[df_filt['Periodo'] == int(periodo_sel)]
    
    if not nivel_sel.startswith("🎓 Todos"):
        df_filt = df_filt[df_filt['Nivel'] == nivel_sel]
    
    if not programa_sel.startswith("📚 Todos"):
        if programa_sel.startswith("❓"):
            df_filt = df_filt[df_filt['Programa'] == '(multi-carrera)']
        else:
            df_filt = df_filt[df_filt['Programa'] == programa_sel]
    
    if busqueda.strip():
        busq_lower = busqueda.strip().lower()
        df_filt = df_filt[
            df_filt['Materia'].str.lower().str.contains(busq_lower, na=False) |
            df_filt['Maestro'].str.lower().str.contains(busq_lower, na=False) |
            df_filt['CRN'].astype(str).str.contains(busq_lower, na=False)
        ]
    
    st.divider()
    
    # ============================================
    # MÉTRICAS PRINCIPALES
    # ============================================
    st.subheader(f"📊 Resumen ({len(df_filt)} de {len(df)} clases)")
    
    if df_filt.empty:
        st.warning("⚠️ No hay clases vencidas con los filtros actuales")
        return
    
    total_filt = len(df_filt)
    inscritos_total = int(df_filt['Inscritos'].sum())
    mas_antigua = df_filt['Dias_Vencida'].max() if not df_filt.empty else 0
    promedio_dias = int(df_filt['Dias_Vencida'].mean()) if not df_filt.empty else 0
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("📦 Total vencidas", total_filt)
    with col_m2:
        st.metric("👥 Estudiantes afectados", inscritos_total, help="Suma de inscritos de todas las clases mostradas")
    with col_m3:
        st.metric("⏰ Más antigua", f"{mas_antigua} días", help="Días desde que terminó la clase más antigua")
    with col_m4:
        st.metric("📊 Promedio", f"{promedio_dias} días", help="Días promedio de antigüedad")
    
    st.divider()
    
    # ============================================
    # GRÁFICAS
    # ============================================
    
    # Distribución por periodo y nivel (2 gráficas lado a lado)
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        st.subheader("📅 Por nivel (periodo)")
        dist_periodo = df_filt.groupby('Periodo_Nivel').size().reset_index(name='clases')

        fig_per = px.bar(
            dist_periodo.sort_values('clases', ascending=False),
            x='Periodo_Nivel', y='clases',
            text='clases',
            color='clases',
            color_continuous_scale='Oranges',
            labels={'clases': 'Clases vencidas', 'Periodo_Nivel': 'Nivel'}
        )
        fig_per.update_traces(textposition='outside')
        fig_per.update_layout(
            height=350,
            coloraxis_showscale=False,
            showlegend=False,
            xaxis=dict(type='category', tickangle=0)
        )
        st.plotly_chart(fig_per, use_container_width=True)
    
    with col_g2:
        st.subheader("🎓 Por nivel")
        dist_nivel = df_filt.groupby('Nivel').size().reset_index(name='clases')
        dist_nivel = dist_nivel.sort_values('clases', ascending=False)
        
        fig_niv = px.pie(
            dist_nivel,
            names='Nivel', values='clases',
            hole=0.4
        )
        fig_niv.update_traces(textposition='inside', textinfo='label+value')
        fig_niv.update_layout(height=350, showlegend=True)
        st.plotly_chart(fig_niv, use_container_width=True)
    
    st.divider()
    
    # Top 10 materias con más vencidas
    col_g3, col_g4 = st.columns(2)
    
    with col_g3:
        st.subheader("📚 Top materias con más vencidas")
        dist_materia = df_filt[df_filt['Materia'] != '(multi)'].groupby('Materia').size().reset_index(name='clases')
        dist_materia = dist_materia.sort_values('clases', ascending=True).tail(10)
        
        if not dist_materia.empty:
            dist_materia['nombre_corto'] = dist_materia['Materia'].apply(lambda x: x[:30] + '...' if len(str(x)) > 30 else x)
            
            fig_mat = px.bar(
                dist_materia,
                x='clases', y='nombre_corto',
                orientation='h',
                text='clases',
                color='clases',
                color_continuous_scale='Reds',
                labels={'clases': 'Clases vencidas', 'nombre_corto': ''}
            )
            fig_mat.update_traces(textposition='outside')
            fig_mat.update_layout(height=400, coloraxis_showscale=False)
            st.plotly_chart(fig_mat, use_container_width=True)
        else:
            st.info("Sin datos suficientes")
    
    with col_g4:
        st.subheader("👨‍🏫 Top maestros con más vencidas")
        dist_maestro = df_filt[df_filt['Maestro'] != 'Sin asignar'].groupby('Maestro').size().reset_index(name='clases')
        dist_maestro = dist_maestro.sort_values('clases', ascending=True).tail(10)
        
        if not dist_maestro.empty:
            dist_maestro['nombre_corto'] = dist_maestro['Maestro'].apply(lambda x: x[:30] + '...' if len(str(x)) > 30 else x)
            
            fig_maes = px.bar(
                dist_maestro,
                x='clases', y='nombre_corto',
                orientation='h',
                text='clases',
                color='clases',
                color_continuous_scale='Purples',
                labels={'clases': 'Clases vencidas', 'nombre_corto': ''}
            )
            fig_maes.update_traces(textposition='outside')
            fig_maes.update_layout(height=400, coloraxis_showscale=False)
            st.plotly_chart(fig_maes, use_container_width=True)
        else:
            st.info("Sin datos suficientes")
    
    st.divider()
    
    # Línea de tiempo
    st.subheader("📈 Antigüedad de las clases vencidas")
    st.caption("Distribución de cuántas clases vencieron en cada fecha")
    
    df_timeline = df_filt.copy()
    df_timeline['F. Fin'] = pd.to_datetime(df_timeline['F. Fin'])
    timeline = df_timeline.groupby(df_timeline['F. Fin'].dt.date).size().reset_index(name='clases')
    timeline.columns = ['fecha', 'clases']
    
    fig_time = px.area(
        timeline.sort_values('fecha'),
        x='fecha', y='clases',
        labels={'clases': 'Clases vencidas', 'fecha': 'Fecha de finalización'}
    )
    fig_time.update_traces(line_color='#FF6B6B', fillcolor='rgba(255, 107, 107, 0.3)')
    fig_time.update_layout(height=300)
    st.plotly_chart(fig_time, use_container_width=True)
    
    st.divider()
    
    # ============================================
    # TABLA DETALLADA
    # ============================================
    st.subheader("📋 Listado detallado")
    
    # Opción de ordenamiento
    col_ord1, col_ord2 = st.columns([1, 3])
    with col_ord1:
        ordenar_por = st.selectbox(
            "Ordenar por:",
            ["⏰ Más antiguas primero", "🆕 Más recientes primero", 
             "👥 Más estudiantes", "📋 CRN"],
            key="orden_venc"
        )
    
    df_show = df_filt.copy()
    
    if ordenar_por.startswith("⏰"):
        df_show = df_show.sort_values('Dias_Vencida', ascending=False)
    elif ordenar_por.startswith("🆕"):
        df_show = df_show.sort_values('Dias_Vencida', ascending=True)
    elif ordenar_por.startswith("👥"):
        df_show = df_show.sort_values('Inscritos', ascending=False)
    else:
        df_show = df_show.sort_values('CRN')
    
    # Columnas a mostrar (sin las _ID internas)
    columnas_show = [
        "CRN", "Periodo_Nivel", "Grupo", "Materia", "Maestro",
        "Programa", "Nivel", "F. Fin", "Dias_Vencida", "Inscritos"
    ]
    df_display = df_show[columnas_show].copy()
    df_display.rename(
        columns={"Dias_Vencida": "Días vencida", "Periodo_Nivel": "Periodo / Nivel"},
        inplace=True
    )
    
    altura_calc = 38 + (len(df_display) * 38) + 3
    altura_calc = min(altura_calc, 600)
    
    st.dataframe(df_display, use_container_width=True, hide_index=True, height=altura_calc)
    
    # Botón de descarga
    csv = df_display.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 Descargar tabla en CSV",
        data=csv,
        file_name=f"clases_vencidas_{date.today().isoformat()}.csv",
        mime="text/csv"
    )
    
    st.divider()
    
    # ============================================
    # ACCIÓN DE ARCHIVADO
    # ============================================
    st.subheader("📦 Archivar clases vencidas")
    
    st.warning(
        "⚠️ Al archivar, las clases se moverán de la tabla activa a la tabla de archivo. "
        "Sus horarios se borrarán pero quedará un snapshot. Esta acción NO se puede deshacer."
    )
    
    st.info(
        "🔒 **Por seguridad, esta acción aún NO está disponible desde la interfaz web.** "
        "Se habilitará en la Fase 7 cuando agreguemos login y permisos de usuario."
    )


main()