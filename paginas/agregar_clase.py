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

from datetime import datetime, date
import pandas as pd
import streamlit as st

from app.utils.queries import get_client
from app.utils.ui import encabezado
from app.utils.horarios import construir_horario_cuadricula

DIAS = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]

# Opciones de horario: cada 30 minutos, de 07:00 a 22:00
HORAS_OPCIONES = []
for _h in range(7, 22):
    HORAS_OPCIONES.append(f"{_h:02d}:00")
    HORAS_OPCIONES.append(f"{_h:02d}:30")
HORAS_OPCIONES.append("22:00")

NIVELES_LEGIBLES = {
    "LX": "Licenciatura Ejecutiva", "NC": "Ciencias de la Salud",
    "PT": "Posgrado / Maestría", "L6": "Licenciatura", "LS": "Licenciatura",
    "B6": "Bachillerato", "6B": "Bachillerato",
}


def etiqueta_periodo(periodo_id, descripcion):
    codigos = []
    hay_desconocidos = False
    for clave in str(descripcion or "").split(","):
        clave = clave.strip().upper()
        if not clave:
            continue
        encontrado = None
        for cod in NIVELES_LEGIBLES:
            if cod in clave:
                encontrado = cod
                break
        if encontrado:
            if encontrado not in codigos:
                codigos.append(encontrado)
        else:
            hay_desconocidos = True

    if not codigos and not hay_desconocidos:
        return str(periodo_id)
    if not codigos and hay_desconocidos:
        return f"{periodo_id} · Otros"
    nombre = NIVELES_LEGIBLES[codigos[0]]
    if hay_desconocidos:
        codigos.append("Otros")
    return f"{periodo_id} · {nombre} ({', '.join(codigos)})"


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



def generar_crn_unico(client, periodo_id):
    """Genera un CRN del 1 al 9999 que no exista en la base.
    Los CRNs reales de Banner son >= 101 y suelen ser de 5 dígitos (100+), así que dejamos
    los primeros 9999 para uso manual."""
    todos_r1 = client.table("clases").select("crn").execute().data or []
    todos_r2 = client.table("clases_archivadas").select("crn").execute().data or []
    todos_usados = set(r["crn"] for r in todos_r1) | set(r["crn"] for r in todos_r2)

    candidato = 1
    while candidato < 10000:
        if candidato not in todos_usados:
            return candidato
        candidato += 1
    return None


def generar_grupo_unico(client, periodo_id):
    """Genera un grupo formato 'NNL' (dos dígitos + una letra) que no exista para el periodo.
    Va probando 01A, 02A, 03A..., 01B, 02B..."""
    r_a = client.table("clases").select("grupo").eq("periodo_id", periodo_id).execute().data or []
    r_b = client.table("clases_archivadas").select("grupo").eq("periodo_id", periodo_id).execute().data or []
    ocupados = set()
    for r in r_a + r_b:
        g = (r.get("grupo") or "").strip().upper()
        if g:
            ocupados.add(g)

    for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for num in range(1, 100):
            candidato = f"{num:02d}{letra}"
            if candidato not in ocupados:
                return candidato
    return None


def calcular_status(fecha_ini, fecha_fin):
    """Devuelve 'A' si hoy cae dentro del rango de fechas, 'R' en otro caso.
    Si no hay fechas, asume 'A'."""
    if not fecha_ini or not fecha_fin:
        return "A"
    hoy = date.today()
    if isinstance(fecha_ini, str):
        try:
            fecha_ini = date.fromisoformat(fecha_ini)
        except Exception:
            return "A"
    if isinstance(fecha_fin, str):
        try:
            fecha_fin = date.fromisoformat(fecha_fin)
        except Exception:
            return "A"
    return "A" if fecha_ini <= hoy <= fecha_fin else "R"


def generar_clave_materia_unica(client):
    """Genera una clave de materia formato 'MAN0000A' (MAN + 4 dígitos + una letra)."""
    existentes = client.table("materias").select("id").like("id", "MAN%").execute().data or []
    ocupados = set(m["id"].upper() for m in existentes if m.get("id"))

    for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for num in range(0, 10000):
            candidato = f"MAN{num:04d}{letra}"
            if candidato not in ocupados:
                return candidato
    return None


def generar_clave_maestro_unica(client):
    """Genera una clave de maestro (número). Empieza en 1 y va subiendo.
    Los maestros reales de Banner empiezan en 13,000+ así que 1-9999 son seguros para manuales."""
    existentes = client.table("maestros").select("clave").execute().data or []
    ocupados = set(m["clave"] for m in existentes if m.get("clave") is not None)

    candidato = 1
    while candidato < 10000:
        if candidato not in ocupados:
            return candidato
        candidato += 1
    return None


def calcular_semanas(fecha_ini, fecha_fin):
    """Calcula semanas del curso a partir de las fechas. None si falta alguna."""
    if not fecha_ini or not fecha_fin:
        return None
    from datetime import date as _date
    if isinstance(fecha_ini, str):
        try:
            fecha_ini = _date.fromisoformat(fecha_ini)
        except Exception:
            return None
    if isinstance(fecha_fin, str):
        try:
            fecha_fin = _date.fromisoformat(fecha_fin)
        except Exception:
            return None
    dias = (fecha_fin - fecha_ini).days
    if dias <= 0:
        return None
    return round(dias / 7)


encabezado("Agregar clase", "Crea una clase nueva manualmente", "➕")

client = get_client()
usuario_actual = st.session_state.get("usuario", "editor_web")


@st.cache_data(ttl=300)
def cargar_catalogos():
    maestros = client.table("maestros").select("clave, nombre_completo").order("nombre_completo").execute().data
    salones = client.table("salones").select("codigo").order("codigo").execute().data
    materias = client.table("materias").select("id, descripcion, semanas_curso").execute().data
    periodos = (client.table("periodos_con_estado")
                .select("id, descripcion, estado")
                .eq("estado", "activo")
                .order("id", desc=True).execute().data)
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
    crn = st.number_input("CRN (opcional, si lo dejas vacío se genera solo)", min_value=1, step=1, value=None, placeholder="Ej. 25001", key="ag_crn")
    periodo_label = {p["id"]: etiqueta_periodo(p["id"], p.get("descripcion")) for p in periodos}
    periodo_sel = st.selectbox("Periodo *", [p["id"] for p in periodos],
                               format_func=lambda x: periodo_label.get(x, str(x)), key="ag_periodo")
with col2:
    materia_sel = st.selectbox("Materia *", materia_ids, key="ag_materia",
                               format_func=lambda i: "— Elige materia —" if i is None else f"{i} · {materias_dict.get(i, '')}")
    with st.expander("➕ Materia nueva (si no está en la lista)"):
        st.caption("💡 La clave se genera automáticamente. Solo escribe el nombre.")
        nm_desc = st.text_input("Nombre de la materia", key="nm_desc").strip()
        if st.button("Agregar materia"):
            if not nm_desc:
                st.error("El nombre de la materia es obligatorio.")
            else:
                nueva_clave = generar_clave_materia_unica(client)
                if nueva_clave is None:
                    st.error("No se pudo generar una clave automática.")
                else:
                    # Semanas se calculan de las fechas del formulario principal (si el usuario ya las puso)
                    sem = calcular_semanas(st.session_state.get("ag_fi"), st.session_state.get("ag_ff"))
                    client.table("materias").insert({
                        "id": nueva_clave, "descripcion": nm_desc,
                        "semanas_curso": sem,
                    }).execute()
                    st.session_state["_nueva_materia"] = nueva_clave
                    st.cache_data.clear()
                    st.success(f"✅ Materia '{nm_desc}' creada con clave {nueva_clave}.")
                    st.rerun()
with col3:
    maestro = st.selectbox("Maestro", maestro_claves, key="ag_maestro",
                           format_func=lambda c: "— Sin maestro —" if c is None else maestros_dict.get(c, str(c)))
    with st.expander("➕ Maestro nuevo (si no está en la lista)"):
        st.caption("💡 La clave se genera automáticamente. Solo escribe el nombre.")
        mn_nombre = st.text_input("Nombre completo", key="mn_nombre").strip()
        if st.button("Agregar maestro"):
            if not mn_nombre:
                st.error("El nombre del maestro es obligatorio.")
            else:
                nueva_clave = generar_clave_maestro_unica(client)
                if nueva_clave is None:
                    st.error("No se pudo generar una clave automática.")
                else:
                    client.table("maestros").insert({
                        "clave": nueva_clave, "nombre_completo": mn_nombre, "activo": True,
                    }).execute()
                    st.session_state["_nuevo_maestro"] = nueva_clave
                    st.cache_data.clear()
                    st.success(f"✅ Maestro '{mn_nombre}' creado con clave {nueva_clave}.")
                    st.rerun()

col4, col5, col6 = st.columns(3)
with col4:
    carrera_sel = st.selectbox("Carrera", carrera_ids, key="ag_carrera",
                               format_func=lambda i: "— Sin carrera (multi) —" if i is None else carrera_label.get(i, str(i)))
with col5:
    grupo = st.text_input("Grupo (opcional, si lo dejas vacío se genera solo)", key="ag_grupo")
with col6:
    st.caption("💡 Status, capacidad e inscritos se establecen automáticamente.")
    # Valores por defecto: status se calcula al insertar según fechas
    capacidad = 0
    inscritos = 0

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
        "Inicio": st.column_config.SelectboxColumn("Inicio", options=HORAS_OPCIONES,
                                                   help="Elige la hora de inicio (cada 30 min)"),
        "Fin": st.column_config.SelectboxColumn("Fin", options=HORAS_OPCIONES,
                                                help="Elige la hora de fin (cada 30 min)"),
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

    # Si no puso CRN, generarlo automáticamente
    if not crn:
        crn = generar_crn_unico(client, periodo_sel)
        if crn is None:
            problemas.append(("No se pudo generar un CRN automático.", "Escribe uno a mano."))
        else:
            st.info(f"CRN generado automáticamente: **{crn}**")

    # Si no puso grupo, generarlo automáticamente
    if not grupo or not str(grupo).strip():
        grupo = generar_grupo_unico(client, periodo_sel)
        if grupo is None:
            problemas.append(("No se pudo generar un grupo automático.", "Escribe uno a mano."))
        else:
            st.info(f"Grupo generado automáticamente: **{grupo}**")

    if materia_sel is None:
        problemas.append(("No elegiste materia.", "Selecciona una materia (o créala con el botón ➕)."))
    if crn and client.table("clases").select("crn").eq("crn", int(crn)).eq("periodo_id", periodo_sel).execute().data:
        problemas.append((f"El CRN {int(crn)} ya existe en el periodo {periodo_sel}.",
                          "Usa la página 'Editar Clases', o cambia el CRN."))
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
                              "Elige las horas del menú desplegable."))
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

    # Calcular status según fechas
    status = calcular_status(fi, ff)

    try:
        ahora = datetime.now().isoformat()
        client.table("clases").insert({
            "crn": int(crn), "periodo_id": periodo_sel, "grupo": grupo or None,
            "materia_id": materia_sel, "maestro_clave": maestro, "carrera_id": carrera_sel,
            "status": status, "capacidad_materia": int(capacidad), "inscritos": int(inscritos),
            "vacantes": int(capacidad) - int(inscritos),
            "fecha_inicio": fi.isoformat() if fi else None,
            "fecha_fin": ff.isoformat() if ff else None,
            "semanas_curso": calcular_semanas(fi, ff) or materias_semanas.get(materia_sel),
            "creado_por": usuario_actual, "creado_en": ahora,
            "modificado_por": usuario_actual, "modificado_en": ahora,
        }).execute()
        if filas:
            client.table("horarios").insert(filas).execute()
        st.success(f"✅ Clase {int(crn)} creada (status: {status}). Ya aparece en todo el sistema.")
    except Exception as e:
        st.error(f"❌ No se pudo crear: {e}")