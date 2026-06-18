"""
Página de Reportes con gráficas, filtrable por nivel, programa y periodo.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from app.utils.queries import get_client
from app.utils.ui import encabezado

encabezado(
    "Reportes y análisis",
    "Visualizaciones para entender el panorama general",
    "📊"
)


# ============================================
# CARGAR DATOS BASE (con caché)
# ============================================
@st.cache_data(ttl=120)
def cargar_clases_con_nivel():
    client = get_client()
    data = []
    offset = 0
    while True:
        # IMPORTANTE: ORDER BY estable para que la paginación NO duplique ni salte filas
        batch = client.table("v_clases_con_nivel").select("*").order("crn").order("periodo_id").range(offset, offset + 999).execute()
        if not batch.data:
            break
        data.extend(batch.data)
        if len(batch.data) < 1000:
            break
        offset += 1000
    return pd.DataFrame(data)


@st.cache_data(ttl=120)
def cargar_horarios_con_nivel():
    client = get_client()
    data = []
    offset = 0
    while True:
        # IMPORTANTE: ORDER BY estable para que la paginación NO duplique ni salte filas
        batch = client.table("v_horarios_con_nivel").select("*").eq("es_virtual", False).order("crn").order("periodo_id").order("dia_semana").range(offset, offset + 999).execute()
        if not batch.data:
            break
        data.extend(batch.data)
        if len(batch.data) < 1000:
            break
        offset += 1000
    return pd.DataFrame(data)


@st.cache_data(ttl=120)
def cargar_maestros_dict():
    client = get_client()
    res = client.table("maestros").select("clave, nombre_completo").limit(2000).execute()
    return {m['clave']: m['nombre_completo'] for m in res.data}


@st.cache_data(ttl=120)
def cargar_materias_dict():
    client = get_client()
    res = client.table("materias").select("id, descripcion").limit(2000).execute()
    return {m['id']: m['descripcion'] for m in res.data}


@st.cache_data(ttl=120)
def cargar_salones_dict():
    """Devuelve dict: codigo -> info del salón (tipo_uso, capacidad, etc.)"""
    client = get_client()
    res = client.table("salones").select("codigo, descripcion, capacidad, tipo_uso_descripcion").limit(500).execute()
    return {s['codigo']: s for s in res.data}


@st.cache_data(ttl=120)
def cargar_periodos():
    client = get_client()
    res = client.table("periodos").select("id, descripcion").order("id", desc=True).execute()
    return res.data


@st.cache_data(ttl=120)
def cargar_clases_agrupadas_dict():
    """Mapea CRN+periodo -> grupo_id, y devuelve info de cada grupo."""
    client = get_client()
    res = client.table("clases_agrupadas").select("grupo_id, crns, periodo_id, inscritos_total, capacidad_total").execute()
    
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


def aplicar_agrupamiento(df_clases):
    crn_a_grupo, info_grupos = cargar_clases_agrupadas_dict()
    if not crn_a_grupo:
        return df_clases
    
    df = df_clases.copy()
    df['_grupo_id'] = df.apply(
        lambda row: crn_a_grupo.get((row['crn'], row['periodo_id']), None),
        axis=1
    )
    
    df_no_agrupadas = df[df['_grupo_id'].isna()].copy()
    df_agrupadas = df[df['_grupo_id'].notna()].copy()
    df_agrupadas = df_agrupadas.drop_duplicates(subset='_grupo_id', keep='first')
    
    df_agrupadas['inscritos'] = df_agrupadas['_grupo_id'].map(
        lambda gid: info_grupos.get(gid, {}).get('inscritos_total', 0)
    )
    df_agrupadas['capacidad_materia'] = df_agrupadas['_grupo_id'].map(
        lambda gid: info_grupos.get(gid, {}).get('capacidad_total', 0)
    )
    
    resultado = pd.concat([df_no_agrupadas, df_agrupadas], ignore_index=True)
    resultado = resultado.drop(columns=['_grupo_id'])
    return resultado


# ============================================
# CARGAR TODO
# ============================================
with st.spinner("Cargando datos..."):
    df_clases_orig = cargar_clases_con_nivel()
    df_horarios_orig = cargar_horarios_con_nivel()
    maestros_dict = cargar_maestros_dict()
    materias_dict = cargar_materias_dict()
    salones_dict = cargar_salones_dict()
    periodos = cargar_periodos()


# ============================================
# FILTROS
# ============================================
st.subheader("🎯 Filtros del reporte")

# Filtro 1: NIVEL
niveles_disponibles = sorted(df_clases_orig['nivel_codigo'].dropna().unique().tolist())
niveles_disponibles = [n for n in niveles_disponibles if n != 'SIN_NIVEL']
opciones_nivel = ["📊 Todos los niveles"] + [f"{n}" for n in niveles_disponibles] + ["❓ Sin nivel asignado"]

nivel_sel = st.radio(
    "1️⃣ Nivel académico:",
    opciones_nivel,
    horizontal=True,
    key="filtro_nivel_reportes"
)

# Aplicar filtro de nivel
df_clases_filt = df_clases_orig.copy()
df_horarios_filt = df_horarios_orig.copy()
nivel_actual = None
titulo_filtro = "Todos los niveles"

if nivel_sel.startswith("❓"):
    df_clases_filt = df_clases_filt[df_clases_filt['nivel_codigo'] == 'SIN_NIVEL']
    df_horarios_filt = df_horarios_filt[df_horarios_filt['nivel_codigo'] == 'SIN_NIVEL']
    titulo_filtro = "Clases sin nivel asignado"
    nivel_actual = 'SIN_NIVEL'
elif not nivel_sel.startswith("📊"):
    df_clases_filt = df_clases_filt[df_clases_filt['nivel_codigo'] == nivel_sel]
    df_horarios_filt = df_horarios_filt[df_horarios_filt['nivel_codigo'] == nivel_sel]
    nivel_desc = df_clases_filt['nivel_descripcion'].iloc[0] if not df_clases_filt.empty else nivel_sel
    titulo_filtro = f"{nivel_sel} - {nivel_desc}"
    nivel_actual = nivel_sel


# Filtros 2 y 3: PROGRAMA + PERIODO en columnas
col_f1, col_f2 = st.columns(2)

with col_f1:
    if nivel_actual != 'SIN_NIVEL':
        programas_filt = df_clases_filt[df_clases_filt['programa_clave'].notna()][['programa_clave', 'programa_nombre']].drop_duplicates()
        programas_filt = programas_filt.sort_values('programa_nombre')
        
        if not programas_filt.empty:
            opciones_programa = ["📚 Todos los programas"] + [
                f"{row['programa_clave']} - {row['programa_nombre']}"
                for _, row in programas_filt.iterrows()
            ]
            programa_sel = st.selectbox("2️⃣ Programa:", opciones_programa, key="filtro_programa_reportes")
            
            if not programa_sel.startswith("📚 Todos"):
                programa_clave = programa_sel.split(" - ")[0]
                df_clases_filt = df_clases_filt[df_clases_filt['programa_clave'] == programa_clave]
                df_horarios_filt = df_horarios_filt[df_horarios_filt['programa_clave'] == programa_clave]
                programa_nombre = programa_sel.split(" - ", 1)[1]
                titulo_filtro = f"{programa_nombre}"
                if nivel_actual:
                    titulo_filtro += f" ({nivel_actual})"

with col_f2:
    opciones_periodo = ["📅 Todos los periodos"] + [f"{p['id']} - {p['descripcion']}" for p in periodos]
    periodo_sel = st.selectbox("3️⃣ Periodo:", opciones_periodo, key="filtro_periodo_reportes")
    
    if not periodo_sel.startswith("📅 Todos"):
        periodo_id = int(periodo_sel.split(" - ")[0])
        df_clases_filt = df_clases_filt[df_clases_filt['periodo_id'] == periodo_id]
        df_horarios_filt = df_horarios_filt[df_horarios_filt['periodo_id'] == periodo_id]
        titulo_filtro += f" · Periodo {periodo_id}"


# Toggle clases agrupadas
col_tog_r, _ = st.columns([1, 3])
with col_tog_r:
    aplicar_agrup = st.toggle(
        "🔗 Considerar clases agrupadas",
        value=True,
        help="Cuando está activado, las clases divididas cuentan como UNA sola."
    )

if aplicar_agrup:
    df_clases_filt = aplicar_agrupamiento(df_clases_filt)


st.divider()


# ============================================
# MÉTRICAS GENERALES
# ============================================
st.subheader(f"📈 Resumen: {titulo_filtro}")

total_clases = len(df_clases_filt)
total_inscritos = int(df_clases_filt['inscritos'].sum())
total_capacidad = int(df_clases_filt['capacidad_materia'].sum())
porcentaje_llenado = (total_inscritos / total_capacidad * 100) if total_capacidad > 0 else 0
total_horas = round(df_horarios_filt['horas'].sum(), 1)
maestros_activos = df_clases_filt['maestro_clave'].nunique()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("📝 Clases", total_clases)
with col2:
    st.metric("👥 Inscritos", total_inscritos, help=f"Capacidad total: {total_capacidad}")
with col3:
    st.metric("📊 Llenado", f"{porcentaje_llenado:.1f}%")
with col4:
    st.metric("👨‍🏫 Maestros activos", maestros_activos)

st.divider()


# ============================================
# REPORTE 1: DISTRIBUCIÓN POR NIVEL (solo cuando "Todos")
# ============================================
if nivel_sel.startswith("📊 Todos"):
    st.subheader("📊 Distribución de clases por nivel")
    
    df_para_dist = df_clases_filt
    dist_nivel = df_para_dist.groupby(['nivel_codigo', 'nivel_descripcion']).size().reset_index(name='clases')
    dist_nivel = dist_nivel.sort_values('clases', ascending=False)
    dist_nivel['etiqueta'] = dist_nivel['nivel_codigo'] + ' - ' + dist_nivel['nivel_descripcion']
    
    fig_dist = px.pie(
        dist_nivel, names='etiqueta', values='clases', hole=0.5,
        title="Clases por nivel académico"
    )
    fig_dist.update_traces(textposition='inside', textinfo='percent+label')
    fig_dist.update_layout(height=450)
    st.plotly_chart(fig_dist, use_container_width=True)
    st.divider()


# ============================================
# REPORTE 2 (NUEVO): MAPA DE CALOR DE DEMANDA HORARIA
# ============================================
st.subheader("🔥 Mapa de calor: demanda por día y hora")
st.caption("Muestra cuántas clases están activas en cada bloque horario. Los colores más intensos = más demanda.")

if df_horarios_filt.empty:
    st.info("No hay horarios para este filtro")
else:
    DIAS_ORDEN = ['LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO']
    DIAS_LABEL = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']
    
    # Crear bloques de 1 hora de 7am a 10pm
    bloques = list(range(7, 22))
    
    # Para cada (día, bloque), contar cuántas clases están activas
    matriz = []
    for hora in bloques:
        fila = []
        for dia in DIAS_ORDEN:
            # Contar horarios que cubren esta hora en este día
            horarios_dia = df_horarios_filt[df_horarios_filt['dia_semana'] == dia]
            count = 0
            for _, h in horarios_dia.iterrows():
                try:
                    ini = int(str(h['hora_inicio']).split(':')[0])
                    fin_str = str(h['hora_fin'])
                    fin_h = int(fin_str.split(':')[0])
                    fin_m = int(fin_str.split(':')[1])
                    # Si termina en :59, redondear arriba
                    fin = fin_h + (1 if fin_m >= 30 else 0)
                    if ini <= hora < fin:
                        count += 1
                except Exception:
                    pass
            fila.append(count)
        matriz.append(fila)
    
    fig_calor = go.Figure(data=go.Heatmap(
        z=matriz,
        x=DIAS_LABEL,
        y=[f"{h:02d}:00" for h in bloques],
        colorscale='YlOrRd',
        text=matriz,
        texttemplate="%{text}",
        textfont={"size": 11},
        colorbar=dict(title="Clases<br>activas")
    ))
    fig_calor.update_layout(
        title=f"Demanda horaria ({titulo_filtro})",
        xaxis_title="Día de la semana",
        yaxis_title="Hora",
        height=550,
        yaxis=dict(autorange='reversed')
    )
    st.plotly_chart(fig_calor, use_container_width=True)
    
    # Encontrar el bloque más cargado
    max_val = max(max(fila) for fila in matriz)
    if max_val > 0:
        for i, hora in enumerate(bloques):
            for j, dia in enumerate(DIAS_LABEL):
                if matriz[i][j] == max_val:
                    st.caption(f"📌 **Hora pico:** {dia} a las {hora:02d}:00 con {max_val} clases simultáneas")
                    break
            else:
                continue
            break

st.divider()


# ============================================
# REPORTE 3: TOP SALONES MÁS USADOS
# ============================================
st.subheader("🚪 Top 15 salones más utilizados")

if df_horarios_filt.empty:
    st.info("No hay horarios físicos para este filtro")
else:
    salon_uso = df_horarios_filt.groupby('salon_codigo').agg(
        horas=('horas', 'sum'),
    ).reset_index()
    salon_uso = salon_uso[salon_uso['salon_codigo'].notna()]
    salon_uso = salon_uso.sort_values('horas', ascending=True).tail(15)
    salon_uso['horas'] = salon_uso['horas'].round(1)
    
    fig_salones = px.bar(
        salon_uso, x='horas', y='salon_codigo', orientation='h',
        labels={'horas': 'Horas/semana', 'salon_codigo': 'Salón'},
        title=f"Salones con mayor uso ({titulo_filtro})",
        text='horas', color='horas', color_continuous_scale='Blues'
    )
    fig_salones.update_traces(textposition='outside')
    fig_salones.update_layout(height=500, showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig_salones, use_container_width=True)

st.divider()


# ============================================
# REPORTE 4 (NUEVO): EFICIENCIA POR TIPO DE SALÓN
# (Solo se muestra cuando NO hay filtros aplicados)
# ============================================

# Detectar si hay algún filtro activo
sin_filtros_prog = True
try:
    sin_filtros_prog = programa_sel.startswith("📚 Todos")
except NameError:
    sin_filtros_prog = True

sin_filtros = (
    nivel_sel.startswith("📊 Todos") and
    periodo_sel.startswith("📅 Todos") and
    sin_filtros_prog
)

if not sin_filtros:
    st.info(
        "ℹ️ El reporte de **Eficiencia por tipo de salón** se oculta cuando hay filtros aplicados, "
        "porque los salones son transversales (cualquier nivel/programa puede usarlos). "
        "Limpia los filtros para verlo."
    )
else:
    st.subheader("⚖️ Eficiencia por tipo de salón")
    st.caption("Análisis dentro de cada tipo: ¿cuáles salones están sobrecargados y cuáles subutilizados? Solo se comparan salones del mismo tipo.")
    
    # Calcular el uso de TODOS los salones
    todos_horarios = df_horarios_orig.copy()
    uso_total = todos_horarios.groupby('salon_codigo').agg(horas=('horas', 'sum')).reset_index()
    
    uso_total['tipo'] = uso_total['salon_codigo'].map(lambda c: (salones_dict.get(c, {}) or {}).get('tipo_uso_descripcion'))
    uso_total['capacidad'] = uso_total['salon_codigo'].map(lambda c: (salones_dict.get(c, {}) or {}).get('capacidad', 0))
    uso_total = uso_total[uso_total['tipo'].notna()]
    uso_total['porcentaje'] = (uso_total['horas'] / 90 * 100).clip(upper=100)
    
    stats_tipo = uso_total.groupby('tipo').agg(
        cantidad_salones=('salon_codigo', 'count'),
        promedio_pct=('porcentaje', 'mean'),
        max_pct=('porcentaje', 'max'),
        min_pct=('porcentaje', 'min')
    ).reset_index()
    stats_tipo = stats_tipo.sort_values('cantidad_salones', ascending=False)
    
    tipos_con_varios = stats_tipo[stats_tipo['cantidad_salones'] >= 2]['tipo'].tolist()
    opciones_tipo = ["📊 Ver resumen de todos los tipos"] + tipos_con_varios
    
    tipo_sel = st.selectbox(
        "Selecciona un tipo de salón para analizarlo a detalle:",
        opciones_tipo,
        help="Solo se muestran tipos con 2 o más salones."
    )
    
    if tipo_sel.startswith("📊 Ver resumen"):
        stats_show = stats_tipo[stats_tipo['cantidad_salones'] >= 2].copy()
        stats_show['promedio_pct'] = stats_show['promedio_pct'].round(1)
        stats_show['max_pct'] = stats_show['max_pct'].round(1)
        stats_show['min_pct'] = stats_show['min_pct'].round(1)
        
        fig_tipos = px.bar(
            stats_show.sort_values('promedio_pct', ascending=True),
            x='promedio_pct', y='tipo', orientation='h',
            labels={'promedio_pct': '% promedio de uso', 'tipo': 'Tipo de salón'},
            title="Uso promedio por tipo de salón",
            text='promedio_pct', color='promedio_pct',
            color_continuous_scale='RdYlGn_r',
            hover_data=['cantidad_salones', 'max_pct', 'min_pct']
        )
        fig_tipos.update_traces(textposition='outside', texttemplate='%{text}%')
        fig_tipos.update_layout(height=600, coloraxis_showscale=False)
        st.plotly_chart(fig_tipos, use_container_width=True)
    else:
        salones_tipo = uso_total[uso_total['tipo'] == tipo_sel].copy()
        salones_tipo = salones_tipo.sort_values('porcentaje', ascending=False)
        salones_tipo['porcentaje'] = salones_tipo['porcentaje'].round(1)
        
        promedio = salones_tipo['porcentaje'].mean()
        sobrecargados = salones_tipo[salones_tipo['porcentaje'] >= 70]
        subutilizados = salones_tipo[salones_tipo['porcentaje'] < 20]
        
        col_e1, col_e2, col_e3, col_e4 = st.columns(4)
        with col_e1:
            st.metric("🚪 Salones de este tipo", len(salones_tipo))
        with col_e2:
            st.metric("📊 Uso promedio", f"{promedio:.1f}%")
        with col_e3:
            st.metric("🔴 Sobrecargados (≥70%)", len(sobrecargados))
        with col_e4:
            st.metric("🟢 Subutilizados (<20%)", len(subutilizados))
        
        salones_tipo['estado'] = salones_tipo['porcentaje'].apply(
            lambda p: '🔴 Sobrecargado' if p >= 70 else ('🟡 Uso medio' if p >= 20 else '🟢 Subutilizado')
        )
        
        fig_detalle = px.bar(
            salones_tipo.sort_values('porcentaje', ascending=True),
            x='porcentaje', y='salon_codigo', orientation='h',
            labels={'porcentaje': '% uso semanal', 'salon_codigo': 'Salón'},
            title=f"Uso de cada salón tipo: {tipo_sel}",
            text='porcentaje', color='estado',
            color_discrete_map={
                '🔴 Sobrecargado': '#E53935',
                '🟡 Uso medio': '#FDD835',
                '🟢 Subutilizado': '#43A047'
            }
        )
        fig_detalle.update_traces(textposition='outside', texttemplate='%{text}%')
        fig_detalle.update_layout(height=max(400, 50 * len(salones_tipo) + 100))
        st.plotly_chart(fig_detalle, use_container_width=True)
        
        if len(subutilizados) > 0 and len(sobrecargados) > 0:
            st.warning(
                f"💡 **Oportunidad detectada:** Hay {len(sobrecargados)} salones tipo '{tipo_sel}' "
                f"sobrecargados y {len(subutilizados)} con poco uso. Considera redistribuir clases."
            )

st.divider()


# ============================================
# REPORTE 5: TOP MAESTROS
# ============================================
st.subheader("👨‍🏫 Top 15 maestros con mayor carga docente")

if df_horarios_filt.empty:
    st.info("No hay horarios para este filtro")
else:
    maestro_carga = df_horarios_filt.groupby('maestro_clave').agg(horas=('horas', 'sum')).reset_index()
    maestro_carga = maestro_carga[maestro_carga['maestro_clave'].notna()]
    maestro_carga['nombre'] = maestro_carga['maestro_clave'].map(maestros_dict)
    maestro_carga['nombre'] = maestro_carga['nombre'].fillna('Maestro #' + maestro_carga['maestro_clave'].astype(str))
    maestro_carga['nombre_corto'] = maestro_carga['nombre'].apply(lambda x: x[:35] + '...' if len(str(x)) > 35 else x)
    maestro_carga = maestro_carga.sort_values('horas', ascending=True).tail(15)
    maestro_carga['horas'] = maestro_carga['horas'].round(1)
    
    fig_maestros = px.bar(
        maestro_carga, x='horas', y='nombre_corto', orientation='h',
        labels={'horas': 'Horas/semana', 'nombre_corto': 'Maestro'},
        title=f"Maestros con más horas ({titulo_filtro})",
        text='horas', color='horas', color_continuous_scale='Greens'
    )
    fig_maestros.update_traces(textposition='outside')
    fig_maestros.update_layout(height=500, coloraxis_showscale=False)
    st.plotly_chart(fig_maestros, use_container_width=True)

st.divider()


# ============================================
# REPORTE 6: TOP MATERIAS
# ============================================
st.subheader("📚 Top 15 materias con más alumnos inscritos")

if df_clases_filt.empty:
    st.info("No hay clases para este filtro")
else:
    # Primero mapeamos cada materia_id a su nombre
    df_mat = df_clases_filt.copy()
    df_mat['nombre'] = df_mat['materia_id'].map(materias_dict).fillna(df_mat['materia_id'])
    
    # Agrupamos por NOMBRE (no por ID) para fusionar variantes de la misma materia
    materia_demanda = df_mat.groupby('nombre').agg(
        inscritos=('inscritos', 'sum'),
        ids_distintos=('materia_id', 'nunique')
    ).reset_index()
    
    materia_demanda = materia_demanda[materia_demanda['nombre'].notna()]
    materia_demanda['nombre_corto'] = materia_demanda['nombre'].apply(
        lambda x: x[:30] + '...' if len(str(x)) > 30 else x
    )
    
    # Si hay variantes, marcarlas con un símbolo
    materia_demanda['nombre_corto'] = materia_demanda.apply(
        lambda row: f"{row['nombre_corto']} ⚡" if row['ids_distintos'] > 1 else row['nombre_corto'],
        axis=1
    )
    
    materia_demanda = materia_demanda.sort_values('inscritos', ascending=True).tail(15)
    
    fig_materias = px.bar(
        materia_demanda, x='inscritos', y='nombre_corto', orientation='h',
        labels={'inscritos': 'Alumnos inscritos', 'nombre_corto': 'Materia'},
        title=f"Materias con más inscritos ({titulo_filtro})",
        text='inscritos', color='inscritos', color_continuous_scale='Oranges'
    )
    fig_materias.update_traces(textposition='outside')
    fig_materias.update_layout(height=500, coloraxis_showscale=False)
    st.plotly_chart(fig_materias, use_container_width=True)
    
    # Aviso sobre el símbolo ⚡
    if (materia_demanda['ids_distintos'] > 1).any():
        st.caption(
            "⚡ = materia que existe con varias claves diferentes en Banner (ej: versión 7 sem y 20 sem). "
            "El conteo suma todas las variantes."
        )

st.divider()


# ============================================
# REPORTE 7: DISTRIBUCIÓN DE LLENADO
# ============================================
st.subheader("📊 Distribución del % de llenado de clases")

if df_clases_filt.empty:
    st.info("No hay clases para este filtro")
else:
    df_llenado = df_clases_filt.copy()
    df_llenado = df_llenado[df_llenado['capacidad_materia'] > 0]
    df_llenado['porcentaje'] = (df_llenado['inscritos'] / df_llenado['capacidad_materia'] * 100).round(0)
    df_llenado['porcentaje'] = df_llenado['porcentaje'].clip(upper=100)
    
    def categoria_llenado(p):
        if p == 0: return '0% (vacía)'
        elif p < 25: return '1-24% (muy bajo)'
        elif p < 50: return '25-49% (bajo)'
        elif p < 75: return '50-74% (medio)'
        elif p < 100: return '75-99% (alto)'
        else: return '100% (lleno)'
    
    df_llenado['categoria'] = df_llenado['porcentaje'].apply(categoria_llenado)
    orden_categorias = ['0% (vacía)', '1-24% (muy bajo)', '25-49% (bajo)', 
                        '50-74% (medio)', '75-99% (alto)', '100% (lleno)']
    
    dist_llenado = df_llenado.groupby('categoria').size().reset_index(name='clases')
    dist_llenado['categoria'] = pd.Categorical(dist_llenado['categoria'], categories=orden_categorias, ordered=True)
    dist_llenado = dist_llenado.sort_values('categoria')
    colores = ['#9E9E9E', '#FFCDD2', '#FFE0B2', '#FFF9C4', '#C8E6C9', '#81C784']
    
    fig_llenado = go.Figure(data=[
        go.Bar(x=dist_llenado['categoria'].astype(str), y=dist_llenado['clases'],
               text=dist_llenado['clases'], textposition='outside', marker_color=colores)
    ])
    fig_llenado.update_layout(
        title=f"¿Qué tan llenas están las clases? ({titulo_filtro})",
        xaxis_title="Nivel de llenado", yaxis_title="Número de clases", height=450
    )
    st.plotly_chart(fig_llenado, use_container_width=True)

st.divider()


# ============================================
# REPORTE 8 (NUEVO): COMPARATIVA LADO A LADO
# ============================================
st.subheader("🆚 Comparativa lado a lado")
st.caption("Compara dos niveles o programas para ver diferencias clave.")

col_c1, col_c2 = st.columns(2)

# Construir opciones únicas para comparar
opciones_comparar = ["— Selecciona —"]
for n in niveles_disponibles:
    opciones_comparar.append(f"🎓 Nivel: {n}")

# Agregar programas
programas_todos = df_clases_orig[df_clases_orig['programa_clave'].notna()][['programa_clave', 'programa_nombre']].drop_duplicates()
programas_todos = programas_todos.sort_values('programa_nombre')
for _, row in programas_todos.iterrows():
    opciones_comparar.append(f"📘 Programa: {row['programa_clave']} - {row['programa_nombre']}")


def filtrar_para_comparar(seleccion, df_clases_base, df_horarios_base):
    """Filtra los DataFrames según una selección de comparativa."""
    if seleccion.startswith("🎓 Nivel: "):
        nivel = seleccion.replace("🎓 Nivel: ", "")
        df_c = df_clases_base[df_clases_base['nivel_codigo'] == nivel].copy()
        df_h = df_horarios_base[df_horarios_base['nivel_codigo'] == nivel].copy()
        return df_c, df_h, nivel
    elif seleccion.startswith("📘 Programa: "):
        clave = seleccion.replace("📘 Programa: ", "").split(" - ")[0]
        df_c = df_clases_base[df_clases_base['programa_clave'] == clave].copy()
        df_h = df_horarios_base[df_horarios_base['programa_clave'] == clave].copy()
        nombre = seleccion.replace("📘 Programa: ", "").split(" - ", 1)[1] if " - " in seleccion else clave
        return df_c, df_h, nombre
    return None, None, None


def calcular_stats(df_c, df_h):
    """Calcula métricas clave de un grupo."""
    if df_c is None or df_c.empty:
        return None
    return {
        'clases': len(df_c),
        'inscritos': int(df_c['inscritos'].sum()),
        'capacidad': int(df_c['capacidad_materia'].sum()),
        'maestros': df_c['maestro_clave'].nunique(),
        'materias': df_c['materia_id'].nunique(),
        'horas_semana': round(df_h['horas'].sum(), 1) if df_h is not None else 0,
        'salones_distintos': df_h['salon_codigo'].nunique() if df_h is not None else 0
    }


with col_c1:
    sel_a = st.selectbox("Opción A:", opciones_comparar, key="comp_a")

with col_c2:
    sel_b = st.selectbox("Opción B:", opciones_comparar, key="comp_b")


if sel_a != "— Selecciona —" and sel_b != "— Selecciona —" and sel_a != sel_b:
    # Para la comparativa usar siempre los DataFrames originales con agrupamiento
    df_c_base = aplicar_agrupamiento(df_clases_orig) if aplicar_agrup else df_clases_orig
    
    df_a_c, df_a_h, label_a = filtrar_para_comparar(sel_a, df_c_base, df_horarios_orig)
    df_b_c, df_b_h, label_b = filtrar_para_comparar(sel_b, df_c_base, df_horarios_orig)
    
    stats_a = calcular_stats(df_a_c, df_a_h)
    stats_b = calcular_stats(df_b_c, df_b_h)
    
    if stats_a and stats_b:
        # Tabla comparativa
        comp_data = {
            'Métrica': ['📝 Clases', '👥 Inscritos', '🪑 Capacidad', '📊 % Llenado',
                       '👨‍🏫 Maestros', '📚 Materias', '⏰ Hrs/semana', '🚪 Salones distintos'],
            label_a: [
                stats_a['clases'],
                stats_a['inscritos'],
                stats_a['capacidad'],
                f"{(stats_a['inscritos']/stats_a['capacidad']*100):.1f}%" if stats_a['capacidad'] > 0 else "—",
                stats_a['maestros'],
                stats_a['materias'],
                stats_a['horas_semana'],
                stats_a['salones_distintos']
            ],
            label_b: [
                stats_b['clases'],
                stats_b['inscritos'],
                stats_b['capacidad'],
                f"{(stats_b['inscritos']/stats_b['capacidad']*100):.1f}%" if stats_b['capacidad'] > 0 else "—",
                stats_b['maestros'],
                stats_b['materias'],
                stats_b['horas_semana'],
                stats_b['salones_distintos']
            ]
        }
        
        df_comp = pd.DataFrame(comp_data)
        st.dataframe(df_comp, use_container_width=True, hide_index=True, height=320)
        
        # Gráfica comparativa de barras
        categorias = ['Clases', 'Inscritos', 'Maestros', 'Materias']
        valores_a = [stats_a['clases'], stats_a['inscritos'], stats_a['maestros'], stats_a['materias']]
        valores_b = [stats_b['clases'], stats_b['inscritos'], stats_b['maestros'], stats_b['materias']]
        
        fig_comp = go.Figure(data=[
            go.Bar(name=label_a[:25], x=categorias, y=valores_a, marker_color='#1976D2'),
            go.Bar(name=label_b[:25], x=categorias, y=valores_b, marker_color='#E64A19')
        ])
        fig_comp.update_layout(
            barmode='group',
            title="Comparación visual",
            height=400
        )
        st.plotly_chart(fig_comp, use_container_width=True)
    else:
        st.warning("Una de las opciones no tiene datos")
elif sel_a == sel_b and sel_a != "— Selecciona —":
    st.info("👆 Selecciona dos opciones DIFERENTES para comparar")
else:
    st.info("👆 Selecciona dos opciones para comparar")


st.divider()


# ============================================
# REPORTE 9: CHOQUES POR NIVEL (solo cuando "Todos")
# ============================================
if nivel_sel.startswith("📊 Todos"):
    st.subheader("🚨 Choques por nivel académico")
    
    client = get_client()
    choques_raw = client.rpc("detectar_choques_salon").execute().data or []
    
    if not choques_raw:
        st.success("✅ No hay choques de salones en el sistema")
    else:
        pares_unicos = set()
        for c in choques_raw:
            pares_unicos.add((c['crn_1'], c['crn_2'], c['periodo']))
        
        choques_por_nivel = {}
        for crn1, crn2, per in pares_unicos:
            clase_data = df_clases_orig[(df_clases_orig['crn'] == crn1) & (df_clases_orig['periodo_id'] == per)]
            if not clase_data.empty:
                nivel = clase_data['nivel_codigo'].iloc[0]
                if nivel == 'SIN_NIVEL':
                    nivel = 'Sin nivel'
                choques_por_nivel[nivel] = choques_por_nivel.get(nivel, 0) + 1
        
        if choques_por_nivel:
            df_choques = pd.DataFrame([{'nivel': k, 'choques': v} for k, v in choques_por_nivel.items()])
            df_choques = df_choques.sort_values('choques', ascending=False)
            
            fig_choques = px.bar(
                df_choques, x='nivel', y='choques', text='choques',
                labels={'nivel': 'Nivel académico', 'choques': 'Cantidad de choques'},
                title="Choques de salón por nivel",
                color='choques', color_continuous_scale='Reds'
            )
            fig_choques.update_traces(textposition='outside')
            fig_choques.update_layout(height=400, coloraxis_showscale=False)
            st.plotly_chart(fig_choques, use_container_width=True)
            
            st.caption(f"Total de choques únicos: {sum(choques_por_nivel.values())}")