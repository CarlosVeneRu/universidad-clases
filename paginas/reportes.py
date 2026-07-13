"""
Página de Reportes con gráficas, filtrable por nivel y programa.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date
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


# ============================================
# FILTROS
# ============================================
st.subheader("🎯 Filtros del reporte")

# Diccionario para mostrar cada código con nombre bonito
NOMBRES_NIVEL = {
    "B6": "Bachillerato",
    "6B": "Bachillerato",
    "L6": "Licenciatura",
    "LS": "Licenciatura Semestral",
    "LX": "Licenciatura Ejecutiva",
    "NC": "Ciencias de la Salud",
    "PT": "Posgrado / Maestría",
}

# ===== Filtro 1: NIVEL (menú desplegable, mismo estilo que en Clases) =====
NIVELES_OPCIONES = [
    ("Todos", "📊 Todos los niveles"),
    ("6B", "🎓 Bachillerato (6B)"),
    ("L6", "🎓 Licenciatura semestral (L6)"),
    ("LS", "🎓 Licenciatura sabatinos (LS)"),
    ("LX", "🎓 Licenciatura Ejecutiva (LX)"),
    ("NC", "🎓 Ciencias de la Salud (NC)"),
    ("PT", "🎓 Posgrado / Maestría (PT)"),
    ("multicarrera", "🔀 Multicarrera (sin carrera asignada)"),
]

col_f1, col_f2 = st.columns(2)

with col_f1:
    nivel_sel = st.selectbox(
        "1️⃣ Nivel académico",
        [k for k, _ in NIVELES_OPCIONES],
        format_func=lambda k: dict(NIVELES_OPCIONES)[k],
        key="filtro_nivel_reportes"
    )

# Aplicar filtro de nivel (Bachillerato normaliza B6→6B)
df_clases_filt = df_clases_orig.copy()
df_horarios_filt = df_horarios_orig.copy()
titulo_filtro = "Todos los niveles"

if nivel_sel == "multicarrera":
    df_clases_filt = df_clases_filt[df_clases_filt['nivel_codigo'] == 'SIN_NIVEL']
    df_horarios_filt = df_horarios_filt[df_horarios_filt['nivel_codigo'] == 'SIN_NIVEL']
    titulo_filtro = "Multicarrera (sin carrera asignada)"
elif nivel_sel == "6B":
    df_clases_filt = df_clases_filt[df_clases_filt['nivel_codigo'].isin(['6B', 'B6'])]
    df_horarios_filt = df_horarios_filt[df_horarios_filt['nivel_codigo'].isin(['6B', 'B6'])]
    titulo_filtro = "Bachillerato (6B)"
elif nivel_sel != "Todos":
    df_clases_filt = df_clases_filt[df_clases_filt['nivel_codigo'] == nivel_sel]
    df_horarios_filt = df_horarios_filt[df_horarios_filt['nivel_codigo'] == nivel_sel]
    titulo_filtro = f"{nivel_sel} · {NOMBRES_NIVEL.get(nivel_sel, 'Otro')}"


# ===== Filtro 2: PROGRAMA (filtrado según el nivel elegido) =====
programa_sel_valor = "📚 Todos los programas"
with col_f2:
    if nivel_sel == "multicarrera":
        st.caption("ℹ️ El filtro por programa no aplica cuando el nivel es **Multicarrera** "
                   "(son clases sin carrera asignada).")
    else:
        # Los programas se derivan del df ya filtrado por nivel
        programas_filt = df_clases_filt[df_clases_filt['programa_clave'].notna()][['programa_clave', 'programa_nombre']].drop_duplicates()
        programas_filt = programas_filt.sort_values('programa_nombre')

        if not programas_filt.empty:
            opciones_programa = ["📚 Todos los programas"] + [
                f"{row['programa_clave']} - {row['programa_nombre']}"
                for _, row in programas_filt.iterrows()
            ]
            label_prog = "2️⃣ Programa"
            if nivel_sel != "Todos":
                label_prog += f" (filtrado por nivel {nivel_sel})"
            programa_sel = st.selectbox(label_prog, opciones_programa, key="filtro_programa_reportes")
            programa_sel_valor = programa_sel

            if not programa_sel.startswith("📚 Todos"):
                programa_clave = programa_sel.split(" - ")[0]
                df_clases_filt = df_clases_filt[df_clases_filt['programa_clave'] == programa_clave]
                df_horarios_filt = df_horarios_filt[df_horarios_filt['programa_clave'] == programa_clave]
                programa_nombre = programa_sel.split(" - ", 1)[1]
                titulo_filtro = programa_nombre
                if nivel_sel != "Todos":
                    titulo_filtro += f" ({nivel_sel})"
        else:
            st.caption("Sin programas disponibles para este nivel.")


# Toggles: clases agrupadas + solo activas o futuras
col_tog1, col_tog2, _ = st.columns([1.3, 1.3, 1.4])
with col_tog1:
    aplicar_agrup = st.toggle(
        "🔗 Considerar clases agrupadas",
        value=True,
        help="Cuando está activado, las clases divididas cuentan como UNA sola."
    )
with col_tog2:
    solo_activas_futuras = st.toggle(
        "🟢 Solo clases activas o futuras",
        value=False,
        help="Excluye clases cuya fecha_fin ya pasó. Muestra solo las que están hoy o empezarán después."
    )

# Filtro por fecha (antes del agrupamiento)
if solo_activas_futuras:
    hoy_iso = date.today().isoformat()
    df_clases_filt = df_clases_filt[df_clases_filt['fecha_fin'].astype(str) >= hoy_iso]
    df_horarios_filt = df_horarios_filt[df_horarios_filt['fecha_fin'].astype(str) >= hoy_iso]

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
# REPORTE 2: MAPA DE CALOR DE DEMANDA HORARIA
# ============================================
st.subheader("🔥 Mapa de calor: demanda por día y hora")
st.caption("Muestra cuántas clases están activas en cada bloque horario. Los colores más intensos = más demanda.")

if df_horarios_filt.empty:
    st.info("No hay horarios para este filtro")
else:
    DIAS_ORDEN = ['LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO']
    DIAS_LABEL = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']

    bloques = list(range(7, 22))

    matriz = []
    for hora in bloques:
        fila = []
        for dia in DIAS_ORDEN:
            horarios_dia = df_horarios_filt[df_horarios_filt['dia_semana'] == dia]
            count = 0
            for _, h in horarios_dia.iterrows():
                try:
                    ini = int(str(h['hora_inicio']).split(':')[0])
                    fin_str = str(h['hora_fin'])
                    fin_h = int(fin_str.split(':')[0])
                    fin_m = int(fin_str.split(':')[1])
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
# REPORTE 4: TOP MAESTROS
# ============================================
st.subheader("👨‍🏫 Top 15 maestros con mayor carga docente")

if df_horarios_filt.empty:
    st.info("No hay horarios para este filtro")
else:
    # Carga de TODOS los maestros (para el gráfico y para detectar sobrecarga)
    maestro_carga_full = df_horarios_filt.groupby('maestro_clave').agg(horas=('horas', 'sum')).reset_index()
    maestro_carga_full = maestro_carga_full[maestro_carga_full['maestro_clave'].notna()]
    maestro_carga_full['nombre'] = maestro_carga_full['maestro_clave'].map(maestros_dict)
    maestro_carga_full['nombre'] = maestro_carga_full['nombre'].fillna('Maestro #' + maestro_carga_full['maestro_clave'].astype(str))
    maestro_carga_full['horas'] = maestro_carga_full['horas'].round(1)

    # Top 15 para el gráfico
    maestro_carga = maestro_carga_full.copy()
    maestro_carga['nombre_corto'] = maestro_carga['nombre'].apply(lambda x: x[:35] + '...' if len(str(x)) > 35 else x)
    maestro_carga = maestro_carga.sort_values('horas', ascending=True).tail(15)

    fig_maestros = px.bar(
        maestro_carga, x='horas', y='nombre_corto', orientation='h',
        labels={'horas': 'Horas/semana', 'nombre_corto': 'Maestro'},
        title=f"Maestros con más horas ({titulo_filtro})",
        text='horas', color='horas', color_continuous_scale='Greens'
    )
    fig_maestros.update_traces(textposition='outside')
    fig_maestros.update_layout(height=500, coloraxis_showscale=False)
    st.plotly_chart(fig_maestros, use_container_width=True)

    # Advertencia: maestros que superan las 25 horas semanales
    sobrecargados = maestro_carga_full[maestro_carga_full['horas'] > 25].sort_values('horas', ascending=False)
    if not sobrecargados.empty:
        st.warning(f"⚠️ **{len(sobrecargados)} maestros superan las 25 horas semanales.** "
                   "Considera revisar su carga docente.")
        with st.expander("Ver lista completa de maestros con más de 25 hrs/semana"):
            df_sobrecargados = sobrecargados[['nombre', 'horas']].rename(
                columns={'nombre': 'Maestro', 'horas': 'Horas/semana'}
            ).reset_index(drop=True)
            st.dataframe(df_sobrecargados, use_container_width=True, hide_index=True)
    else:
        st.success("✅ Ningún maestro supera las 25 horas semanales.")

st.divider()
