"""
Página para agregar una clase nueva manualmente.
- Conserva lo escrito si cambias de página y regresas (widgets con key).
- Permite crear materia/maestro nuevos al vuelo.
- Muestra el horario del salón para ver qué está libre.
- Bloquea si el salón ya está ocupado a esa hora (choque real).
Nota: el bloqueo por rol (Admin/Moderador) se aplica en el paso del login.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime
import pandas as pd
import streamlit as st

from app.utils.queries import get_client
from app.utils.ui import encabezado
from app.utils.horarios import construir_horario_cuadricula

DIAS = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]
STATUS_OPCIONES = ["A", "R"]
NIVELES_LEGIBLES = {
    "LX": "Licenciatura Ejecutiva", "NC": "Ciencias de la Salud",
    "PT": "Posgrado / Maestría", "L6": "Licenciatura", "LS": "Licenciatura",
    "B6": "Bachillerato", "6B": "Bachillerato",
}


def etiqueta_periodo(periodo_id, descripcion):
    codigos = []
    for clave in str(descripcion or "").split(","):
        clave = clave.strip().upper()
        for cod in NIVELES_LEGIBLES:
            if cod in clave and cod not in codigos:
                codigos.append(cod)
                break
    if not codigos:
        return str(periodo_id)
    return f"{periodo_id} · {NIVELES_LEGIBLES[codigos[0]]} ({', '.join(sorted(codigos))})"


def _texto(v):
    """Devuelve texto seguro de una celda del editor (maneja None y NaN)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _check(v):
    """Devuelve True/False seguro para una casilla (maneja NaN)."""
    return bool(v) and pd.notna(v)


def _valida_hora(txt):
    try:
        h, m = str(txt).strip().split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except Exception:
        return False


def _minutos(txt):
    h, m = str(txt).strip().split(":")
    return int(h) * 60 + int(m)


def _norm(txt):
    h, m = str(txt).strip().split(":")
    return f"{int(h):02d}:{int(m):02d}:00"


encabezado("Agregar clase", "Crea una clase nueva manualmente", "➕")

client = get_client()
usuario_actual = st.session_state.get("usuario", "editor_web")


@st.cache_data(ttl=300)
def cargar_catalogos():
    maestros = client.table("maestros").select("clave, nombre_completo").order("nombre_completo").execute().data
    salones = client.table("salones").select("codigo").order("codigo").execute().data
    materias = client.table("materias").select("id, descripcion, semanas_curso").execute().data
    periodos = client.table("periodos").select("id, descripcion").order("id", desc=True).execute().data
    carreras = client.table("carreras").select("id, nombre_banner, nivel_id").order("nombre_banner").execute().data
    return maestros, salones, materias, periodos, carreras


maestros, salones, materias, periodos, carreras = cargar_catalogos()
maestros_dict = {m["clave"]: m["nombre_completo"] for m in maestros}
materias_dict = {m["id"]: m["descripcion"] for m in materias}
materias_semanas = {m["id"]: m.get("semanas_curso") for m in materias}
salon_codigos = [s["codigo"] for s in salones]
salon_opciones = [""] + salon_codigos
maestro_claves = [None] + [m["clave"] for m in maestros]
materia_ids = [None] + sorted([m["id"] for m in materias], key=lambda i: materias_dict.get(i, "").upper())
carrera_ids = [None] + [c["id"] for c in carreras]
carrera_label = {c["id"]: f"{c['nombre_banner']} · {c['nivel_id']}" for c in carreras}

# Aplicar selección pendiente (cuando se acaba de crear materia/maestro nuevo)
for pend, target in [("_nueva_materia", "ag_materia"), ("_nuevo_maestro", "ag_maestro")]:
    if pend in st.session_state:
        st.session_state[target] = st.session_state.pop(pend)

# 1. Datos principales
st.subheader("1️⃣ Datos de la clase")
col1, col2, col3 = st.columns(3)
with col1:
    crn = st.number_input("CRN *", min_value=1, step=1, value=None, placeholder="Ej. 25001", key="ag_crn")
    periodo_label = {p["id"]: etiqueta_periodo(p["id"], p.get("descripcion")) for p in periodos}
    periodo_sel = st.selectbox("Periodo *", [p["id"] for p in periodos],
                               format_func=lambda x: periodo_label.get(x, str(x)), key="ag_periodo")
with col2:
    materia_sel = st.selectbox("Materia *", materia_ids, key="ag_materia",
                               format_func=lambda i: "— Elige materia —" if i is None else f"{i} · {materias_dict.get(i, '')}")
    with st.expander("➕ Materia nueva (si no está en la lista)"):
        nm_id = st.text_input("Clave de la materia", key="nm_id").strip().upper()
        nm_desc = st.text_input("Nombre de la materia", key="nm_desc").strip()
        nm_sem = st.number_input("Semanas del curso", min_value=0, value=0, key="nm_sem")
        if st.button("Agregar materia"):
            if not nm_id or not nm_desc:
                st.error("Faltan la clave o el nombre.")
            elif client.table("materias").select("id").eq("id", nm_id).execute().data:
                st.error("Esa clave de materia ya existe.")
            else:
                client.table("materias").insert({"id": nm_id, "descripcion": nm_desc,
                                                 "semanas_curso": int(nm_sem) or None}).execute()
                st.session_state["_nueva_materia"] = nm_id
                st.cache_data.clear()
                st.rerun()
with col3:
    maestro = st.selectbox("Maestro", maestro_claves, key="ag_maestro",
                           format_func=lambda c: "— Sin maestro —" if c is None else maestros_dict.get(c, str(c)))
    with st.expander("➕ Maestro nuevo (si no está en la lista)"):
        mn_clave = st.number_input("Clave/ID del maestro", min_value=1, step=1, value=None, key="mn_clave")
        mn_nombre = st.text_input("Nombre completo", key="mn_nombre").strip()
        if st.button("Agregar maestro"):
            if not mn_clave or not mn_nombre:
                st.error("Faltan la clave o el nombre.")
            elif client.table("maestros").select("clave").eq("clave", int(mn_clave)).execute().data:
                st.error("Esa clave de maestro ya existe.")
            else:
                client.table("maestros").insert({"clave": int(mn_clave), "nombre_completo": mn_nombre,
                                                 "activo": True}).execute()
                st.session_state["_nuevo_maestro"] = int(mn_clave)
                st.cache_data.clear()
                st.rerun()

col4, col5, col6 = st.columns(3)
with col4:
    carrera_sel = st.selectbox("Carrera (define el nivel en reportes)", carrera_ids, key="ag_carrera",
                               format_func=lambda i: "— Sin carrera (multi) —" if i is None else carrera_label.get(i, str(i)))
with col5:
    grupo = st.text_input("Grupo", key="ag_grupo")
    status = st.selectbox("Status", STATUS_OPCIONES, index=0, key="ag_status")
with col6:
    capacidad = st.number_input("Capacidad", min_value=0, value=0, key="ag_cap")
    inscritos = st.number_input("Inscritos", min_value=0, value=0, key="ag_ins")

col_fi, col_ff = st.columns(2)
with col_fi:
    fi = st.date_input("Fecha inicio", value=None, key="ag_fi")
with col_ff:
    ff = st.date_input("Fecha fin", value=None, key="ag_ff")

# 2. Horarios
st.subheader("2️⃣ Horarios")
df_h = pd.DataFrame(columns=["Día", "Inicio", "Fin", "Salón", "Virtual"])
h_edit = st.data_editor(
    df_h, num_rows="dynamic", use_container_width=True, key="ag_hor",
    column_config={
        "Día": st.column_config.SelectboxColumn("Día", options=DIAS, required=True),
        "Inicio": st.column_config.TextColumn("Inicio", help="HH:MM, ej. 07:00"),
        "Fin": st.column_config.TextColumn("Fin", help="HH:MM, ej. 08:59"),
        "Salón": st.column_config.SelectboxColumn("Salón", options=salon_opciones),
        "Virtual": st.column_config.CheckboxColumn("Virtual"),
    },
)

# Disponibilidad del salón: ver qué está libre en ese salón en este periodo
with st.expander("🔎 Ver disponibilidad de un salón (para saber qué horarios están libres)"):
    ver_salon = st.selectbox("Salón a revisar", [""] + salon_codigos, key="ag_ver_salon")
    if ver_salon:
        hors = (client.table("horarios")
                .select("dia_semana,hora_inicio,hora_fin,salon_codigo,es_virtual,crn")
                .eq("salon_codigo", ver_salon).eq("periodo_id", periodo_sel).execute().data)
        if not hors:
            st.success(f"🟢 {ver_salon} no tiene clases en {periodo_sel}: está libre toda la semana.")
        else:
            crns = list({h["crn"] for h in hors})
            cls = client.table("clases").select("crn,materia_id").eq("periodo_id", periodo_sel).in_("crn", crns).execute().data
            mat_crn = {c["crn"]: materias_dict.get(c["materia_id"], c["materia_id"] or "") for c in cls}
            for h in hors:
                h["materia_nombre"] = mat_crn.get(h["crn"], "")
            df_grid, _ = construir_horario_cuadricula(hors, etiqueta_extra="salon")
            if df_grid is not None and not df_grid.empty:
                st.caption(f"Horario de {ver_salon} en {periodo_sel}. Las celdas con — están libres.")
                st.dataframe(df_grid, use_container_width=True, hide_index=True, height=38 + len(df_grid) * 38 + 3)

# Vista tradicional de la clase que estás creando
materia_nombre = materias_dict.get(materia_sel, "") if materia_sel else ""
preview = []
for _, row in h_edit.iterrows():
    dia = _texto(row.get("Día"))
    ini = _texto(row.get("Inicio"))
    fin = _texto(row.get("Fin"))
    if dia in DIAS and _valida_hora(ini) and _valida_hora(fin) and _minutos(ini) < _minutos(fin):
        preview.append({"dia_semana": dia, "hora_inicio": _norm(ini), "hora_fin": _norm(fin),
                        "salon_codigo": _texto(row.get("Salón")) or None,
                        "es_virtual": _check(row.get("Virtual")), "materia_nombre": materia_nombre})
if preview:
    st.markdown("**Vista tradicional del horario de esta clase**")
    df_g2, _ = construir_horario_cuadricula(preview, etiqueta_extra="salon")
    if df_g2 is not None and not df_g2.empty:
        st.dataframe(df_g2, use_container_width=True, hide_index=True, height=38 + len(df_g2) * 38 + 3)

# 3. Crear
st.divider()
if st.button("➕ Crear clase", type="primary"):
    problemas = []  # (qué está mal, cómo arreglarlo)

    if not crn:
        problemas.append(("Falta el CRN.", "Escribe el número de CRN."))
    if materia_sel is None:
        problemas.append(("No elegiste materia.", "Selecciona una materia (o créala con el botón ➕)."))
    if crn and client.table("clases").select("crn").eq("crn", int(crn)).eq("periodo_id", periodo_sel).execute().data:
        problemas.append((f"El CRN {int(crn)} ya existe en el periodo {periodo_sel}.",
                          "Usa la página 'Editar Clases', o cambia el CRN."))
    if int(inscritos) > int(capacidad):
        problemas.append((f"Hay más inscritos ({int(inscritos)}) que capacidad ({int(capacidad)}).",
                          "Baja los inscritos o sube la capacidad."))
    if fi and ff and ff < fi:
        problemas.append(("La fecha de fin es anterior a la de inicio.",
                          "Corrige las fechas: la de fin debe ser igual o posterior a la de inicio."))

    filas = []
    for n, (_, row) in enumerate(h_edit.iterrows(), start=1):
        dia = _texto(row.get("Día"))
        ini = _texto(row.get("Inicio"))
        fin = _texto(row.get("Fin"))
        if not dia and not ini and not fin:
            continue
        if dia not in DIAS:
            problemas.append((f"Renglón {n} de horarios: falta el día.", "Elige un día de la lista."))
        elif not _valida_hora(ini) or not _valida_hora(fin):
            problemas.append((f"Renglón {n} de horarios: hora mal escrita ('{ini}' - '{fin}').",
                              "Usa el formato HH:MM, ej. 09:00 y 10:00."))
        elif _minutos(ini) >= _minutos(fin):
            problemas.append((f"Renglón {n} ({dia}): el inicio no es menor que el fin.",
                              "Pon la hora de inicio antes que la de fin."))
        else:
            filas.append({"crn": int(crn), "periodo_id": periodo_sel, "dia_semana": dia,
                          "hora_inicio": _norm(ini), "hora_fin": _norm(fin),
                          "salon_codigo": _texto(row.get("Salón")) or None,
                          "es_virtual": _check(row.get("Virtual"))})

    if problemas:
        st.error("No se puede crear todavía. Revisa esto:")
        for que, como in problemas:
            st.markdown(f"- **{que}** → {como}")
        st.stop()

    # Revisar que el salón no esté ya ocupado a esa hora (choque real)
    choques = []
    for f in filas:
        if f["salon_codigo"] and not f["es_virtual"]:
            ocupado = client.rpc("choques_de_horario", {
                "p_salon": f["salon_codigo"], "p_dia": f["dia_semana"],
                "p_ini": f["hora_inicio"], "p_fin": f["hora_fin"],
                "p_periodo": periodo_sel,
                "p_fecha_ini": fi.isoformat() if fi else None,
                "p_fecha_fin": ff.isoformat() if ff else None,
                "p_excluir_crn": None,
            }).execute().data
            for o in (ocupado or []):
                choques.append((f, o))

    if choques:
        st.error("🚨 No se creó: ese salón ya está ocupado a esa hora (habría choque):")
        choques.sort(key=lambda par: (par[0]["dia_semana"], par[1]["hora_inicio"]))
        for f, o in choques:
            st.markdown(f"- **{f['dia_semana']} {f['hora_inicio'][:5]}–{f['hora_fin'][:5]}** en "
                        f"**{f['salon_codigo']}** ya lo usa **CRN {o['crn']} · {o['materia']}** "
                        f"({o['hora_inicio'][:5]}–{o['hora_fin'][:5]})")
        st.info("Cambia el salón o la hora en la tabla de horarios y vuelve a intentar.")
        st.stop()

    try:
        ahora = datetime.now().isoformat()
        client.table("clases").insert({
            "crn": int(crn), "periodo_id": periodo_sel, "grupo": grupo or None,
            "materia_id": materia_sel, "maestro_clave": maestro, "carrera_id": carrera_sel,
            "status": status, "capacidad_materia": int(capacidad), "inscritos": int(inscritos),
            "vacantes": int(capacidad) - int(inscritos),
            "fecha_inicio": fi.isoformat() if fi else None,
            "fecha_fin": ff.isoformat() if ff else None,
            "semanas_curso": materias_semanas.get(materia_sel),
            "creado_por": usuario_actual, "creado_en": ahora,
            "modificado_por": usuario_actual, "modificado_en": ahora,
        }).execute()
        if filas:
            client.table("horarios").insert(filas).execute()
        st.success(f"✅ Clase {int(crn)} creada. Ya aparece en todo el sistema.")
    except Exception as e:
        st.error(f"❌ No se pudo crear: {e}")