"""
Página de Reportes con gráficas, filtrable por nivel y programa.
Soporta 4 modos temporales: Todas (activas+futuras), Solo activas hoy,
Solo futuras y Solo archivadas (histórico).
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


def _nivel_desde_clave(clave):
    """Infiere el nivel académico desde el sufijo de clave_periodo."""
    if not clave:
        return None
    c = str(clave).upper()
    r2 = c[-2:] if len(c) >= 2 else ""
    if c in ("B6B", "BB6") or r2 in ("6B", "B6"):
        return "6B"
    if r2 in ("L6", "LS", "LX", "NC", "PT"):
        return r2
    return None


@st.cache_data(ttl=120)
def cargar_archivadas_con_nivel():
    """Trae clases_archivadas y resuelve el nivel_codigo (via carrera→programa o via clave_periodo).
    Devuelve el DF con el MISMO shape que v_clases_con_nivel."""
    client = get_client()

    data = []
    offset = 0
    while True:
        batch = (client.table("clases_archivadas")
                 .select("crn, periodo_id, grupo, clave_periodo, materia_id, maestro_clave, "
                         "carrera_id, inscritos, capacidad_materia, status, fecha_inicio, fecha_fin")
                 .order("crn").order("periodo_id")
                 .range(offset, offset + 999).execute()).data or []
        if not batch:
            break
        data.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    if not data:
        return pd.DataFrame()

    # Resolver nivel: traer todas las carreras + programas relevantes
    carrera_ids = list({c["carrera_id"] for c in data if c.get("carrera_id")})
    programas_map = {}
    if carrera_ids:
        car_res = (client.table("carreras")
                   .select("id, programa_clave, programas(nombre, nivel_codigo, "
                           "niveles_academicos(descripcion_corta))")
                   .in_("id", carrera_ids).execute().data) or []
        for car in car_res:
            prog = car.get("programas") or {}
            niv = (prog.get("niveles_academicos") or {})
            programas_map[car["id"]] = {
                "nivel_codigo": prog.get("nivel_codigo") or "SIN_NIVEL",
                "nivel_descripcion": niv.get("descripcion_corta") or "Sin nivel",
                "programa_clave": car.get("programa_clave"),
                "programa_nombre": prog.get("nombre"),
            }

    for c in data:
        info = programas_map.get(c.get("carrera_id"))
        if info:
            c["nivel_codigo"] = info["nivel_codigo"]
            c["nivel_descripcion"] = info["nivel_descripcion"]
            c["programa_clave"] = info["programa_clave"]
            c["programa_nombre"] = info["programa_nombre"]
        else:
            inferido = _nivel_desde_clave(c.get("clave_periodo"))
            c["nivel_codigo"] = inferido or "SIN_NIVEL"
            c["nivel_descripcion"] = "Sin nivel" if not inferido else "Inferido"
            c["programa_clave"] = None
            c["programa_nombre"] = None

    return pd.DataFrame(data)


@st.cache_data(ttl=120)
def cargar_horarios_archivados_con_nivel():
    """Extrae los horarios de los snapshots JSON de clases_archivadas."""
    client = get_client()

    data = []
    offset = 0
    while True:
        batch = (client.table("clases_archivadas")
                 .select("crn, periodo_id, carrera_id, clave_periodo, materia_id, maestro_clave, "
                         "fecha_inicio, fecha_fin, horarios_snapshot")
                 .order("crn").order("periodo_id")
                 .range(offset, offset + 999).execute()).data or []
        if not batch:
            break
        data.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    if not data:
        return pd.DataFrame()

    carrera_ids = list({c["carrera_id"] for c in data if c.get("carrera_id")})
    programas_map = {}
    if carrera_ids:
        car_res = (client.table("carreras")
                   .select("id, programa_clave, programas(nombre, nivel_codigo, "
                           "niveles_academicos(descripcion_corta))")
                   .in_("id", carrera_ids).execute().data) or []
        for car in car_res:
            prog = car.get("programas") or {}
            niv = (prog.get("niveles_academicos") or {})
            programas_map[car["id"]] = {
                "nivel_codigo": prog.get("nivel_codigo") or "SIN_NIVEL",
                "nivel_descripcion": niv.get("descripcion_corta") or "Sin nivel",
                "programa_clave": car.get("programa_clave"),
                "programa_nombre": prog.get("nombre"),
            }

    filas_expandidas = []
    for c in data:
        snap = c.get("horarios_snapshot") or []
        if not isinstance(snap, list):
            continue
        info = programas_map.get(c.get("carrera_id"))
        if info:
            nivel_codigo = info["nivel_codigo"]
            nivel_descripcion = info["nivel_descripcion"]
            programa_clave = info["programa_clave"]
            programa_nombre = info["programa_nombre"]
        else:
            inferido = _nivel_desde_clave(c.get("clave_periodo"))
            nivel_codigo = inferido or "SIN_NIVEL"
            nivel_descripcion = "Sin nivel" if not inferido else "Inferido"
            programa_clave = None
            programa_nombre = None

        for h in snap:
            if h.get("es_virtual"):
                continue
            try:
                hi = h.get("hora_inicio", "00:00")
                hf = h.get("hora_fin", "00:00")
                hh_i = int(str(hi).split(":")[0]) * 60 + int(str(hi).split(":")[1])
                hh_f = int(str(hf).split(":")[0]) * 60 + int(str(hf).split(":")[1])
                horas = max(0, (hh_f - hh_i) / 60)
            except Exception:
                horas = 0

            filas_expandidas.append({
                "crn": c.get("crn"),
                "periodo_id": c.get("periodo_id"),
                "dia_semana": h.get("dia_semana"),
                "hora_inicio": h.get("hora_inicio"),
                "hora_fin": h.get("hora_fin"),
                "salon_codigo": h.get("salon_codigo"),
                "es_virtual": bool(h.get("es_virtual")),
                "horas": horas,
                "fecha_inicio": c.get("fecha_inicio"),
                "fecha_fin": c.get("fecha_fin"),
                "nivel_codigo": nivel_codigo,
                "nivel_descripcion": nivel_descripcion,
                "programa_clave": programa_clave,
                "programa_nombre": programa_nombre,
                "maestro_clave": c.get("maestro_clave"),
                "materia_id": c.get("materia_id"),
            })
    return pd.DataFrame(filas_expandidas)


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
    df_clases_arch = cargar_archivadas_con_nivel()
    df_horarios_arch = cargar_horarios_archivados_con_nivel()
    maestros_dict = cargar_maestros_dict()


# ============================================
# FILTROS
# ============================================
st.subheader("🎯 Filtros del reporte")

NOMBRES_NIVEL = {
    "B6": "Bachillerato",
    "6B": "Bachillerato",
    "L6": "Licenciatura",
    "LS": "Licenciatura Semestral",
    "LX": "Licenciatura Ejecutiva",
    "NC": "Ciencias de la Salud",
    "PT": "Posgrado / Maestría",
}

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


# Filtro temporal (radio con 4 opciones) + toggle de agrupar
col_estado, col_tog1 = st.columns([2, 1.3])
with col_estado:
    estado_temporal = st.radio(
        "Mostrar:",
        ["todas_activas_futuras", "activas_hoy", "futuras", "archivadas"],
        format_func=lambda k: {
            "todas_activas_futuras": "🌐 Todas (activas + futuras)",
            "activas_hoy":           "🟢 Solo activas hoy",
            "futuras":               "📅 Solo futuras",
            "archivadas":            "📦 Solo archivadas (histórico)",
        }[k],
        horizontal=True,
        key="estado_temporal_reportes",
    )
with col_tog1:
    aplicar_agrup = st.toggle(
        "🔗 Considerar clases agrupadas",
        value=True,
        help="Cuando está activado, las clases divididas cuentan como UNA sola."
    )


# Elegir los df base según el modo
if estado_temporal == "archivadas":
    df_clases_base = df_clases_arch.copy() if not df_clases_arch.empty else pd.DataFrame()
    df_horarios_base = df_horarios_arch.copy() if not df_horarios_arch.empty else pd.DataFrame()
else:
    df_clases_base = df_clases_orig.copy()
    df_horarios_base = df_horarios_orig.copy()


# Aplicar filtro de nivel (Bachillerato normaliza B6→6B)
df_clases_filt = df_clases_base.copy()
df_horarios_filt = df_horarios_base.copy()
titulo_filtro = "Todos los niveles"

if not df_clases_filt.empty:
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


# Filtro por programa (dependiente del nivel)
programa_sel_valor = "📚 Todos los programas"
with col_f2:
    if nivel_sel == "multicarrera":
        st.caption("ℹ️ El filtro por programa no aplica cuando el nivel es **Multicarrera** "
                   "(son clases sin carrera asignada).")
    else:
        if not df_clases_filt.empty:
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
        else:
            st.caption("Sin programas disponibles.")


# Filtro por fecha según estado_temporal (no aplica para 'archivadas')
hoy_iso = date.today().isoformat()
if not df_clases_filt.empty:
    if estado_temporal == "activas_hoy":
        df_clases_filt = df_clases_filt[
            (df_clases_filt['fecha_inicio'].astype(str) <= hoy_iso) &
            (df_clases_filt['fecha_fin'].astype(str) >= hoy_iso)
        ]
        df_horarios_filt = df_horarios_filt[
            (df_horarios_filt['fecha_inicio'].astype(str) <= hoy_iso) &
            (df_horarios_filt['fecha_fin'].astype(str) >= hoy_iso)
        ]
    elif estado_temporal == "futuras":
        df_clases_filt = df_clases_filt[df_clases_filt['fecha_inicio'].astype(str) > hoy_iso]
        df_horarios_filt = df_horarios_filt[df_horarios_filt['fecha_inicio'].astype(str) > hoy_iso]
    elif estado_temporal == "todas_activas_futuras":
        df_clases_filt = df_clases_filt[df_clases_filt['fecha_fin'].astype(str) >= hoy_iso]
        df_horarios_filt = df_horarios_filt[df_horarios_filt['fecha_fin'].astype(str) >= hoy_iso]
    # else: 'archivadas' — no filtramos por fecha

if aplicar_agrup and not df_clases_filt.empty:
    df_clases_filt = aplicar_agrupamiento(df_clases_filt)


st.divider()


# ============================================
# MÉTRICAS GENERALES
# ============================================
etiqueta_modo = {
    "todas_activas_futuras": "🌐 Todas",
    "activas_hoy":           "🟢 Activas hoy",
    "futuras":               "📅 Futuras",
    "archivadas":            "📦 Archivadas",
}[estado_temporal]

st.subheader(f"📈 Resumen: {titulo_filtro} · {etiqueta_modo}")

if df_clases_filt.empty:
    st.warning("⚠️ No hay clases que cumplan con los filtros seleccionados.")
    st.stop()

total_clases = len(df_clases_filt)
total_inscritos = int(df_clases_filt['inscritos'].sum())
total_capacidad = int(df_clases_filt['capacidad_materia'].sum())
porcentaje_llenado = (total_inscritos / total_capacidad * 100) if total_capacidad > 0 else 0
total_horas = round(df_horarios_filt['horas'].sum(), 1) if not df_horarios_filt.empty else 0
maestros_activos = df_clases_filt['maestro_clave'].nunique()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("📝 Clases", total_clases)
with col2:
    st.metric("👥 Inscritos", total_inscritos, help=f"Capacidad total: {total_capacidad}")
with col3:
    st.metric("📊 Llenado", f"{porcentaje_llenado:.1f}%")
with col4:
    st.metric("👨‍🏫 Maestros distintos", maestros_activos)

st.divider()


# ============================================
# REPORTE 1: MAPA DE CALOR DE DEMANDA HORARIA
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
        title=f"Demanda horaria ({titulo_filtro} · {etiqueta_modo})",
        xaxis_title="Día de la semana",
        yaxis_title="Hora",
        height=550,
        yaxis=dict(autorange='reversed')
    )
    st.plotly_chart(fig_calor, use_container_width=True)

    max_val = max((max(fila) for fila in matriz), default=0)
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
# REPORTE 2: TOP SALONES MÁS USADOS
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
        title=f"Salones con mayor uso ({titulo_filtro} · {etiqueta_modo})",
        text='horas', color='horas', color_continuous_scale='Blues'
    )
    fig_salones.update_traces(textposition='outside')
    fig_salones.update_layout(height=500, showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig_salones, use_container_width=True)

st.divider()


# ============================================
# REPORTE 3: TOP MAESTROS (con advertencia >25 hrs)
# ============================================
st.subheader("👨‍🏫 Top 15 maestros con mayor carga docente")

if df_horarios_filt.empty:
    st.info("No hay horarios para este filtro")
else:
    maestro_carga_full = df_horarios_filt.groupby('maestro_clave').agg(horas=('horas', 'sum')).reset_index()
    maestro_carga_full = maestro_carga_full[maestro_carga_full['maestro_clave'].notna()]
    maestro_carga_full['nombre'] = maestro_carga_full['maestro_clave'].map(maestros_dict)
    maestro_carga_full['nombre'] = maestro_carga_full['nombre'].fillna('Maestro #' + maestro_carga_full['maestro_clave'].astype(str))
    maestro_carga_full['horas'] = maestro_carga_full['horas'].round(1)

    maestro_carga = maestro_carga_full.copy()
    maestro_carga['nombre_corto'] = maestro_carga['nombre'].apply(lambda x: x[:35] + '...' if len(str(x)) > 35 else x)
    maestro_carga = maestro_carga.sort_values('horas', ascending=True).tail(15)

    fig_maestros = px.bar(
        maestro_carga, x='horas', y='nombre_corto', orientation='h',
        labels={'horas': 'Horas/semana', 'nombre_corto': 'Maestro'},
        title=f"Maestros con más horas ({titulo_filtro} · {etiqueta_modo})",
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