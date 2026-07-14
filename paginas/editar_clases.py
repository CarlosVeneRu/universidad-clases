"""
Página para editar clases existentes (modificar datos y horarios).
Los cambios se reflejan al instante en todo el sistema (vistas y funciones).
Nota: el bloqueo por rol (Admin/Moderador) se aplica en el paso del login.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, date
import pandas as pd
import streamlit as st

from app.utils.horarios import construir_horario_cuadricula
from app.utils.queries import get_client
from app.utils.ui import encabezado

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
    """Devuelve '202675 · Licenciatura (L6, LS)' o '202685 · Otros' si los códigos son desconocidos."""
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


def _hhmm(valor):
    if not valor:
        return ""
    p = str(valor).split(":")
    return f"{int(p[0]):02d}:{int(p[1]):02d}" if len(p) >= 2 else ""


def _texto(v):
    """Texto seguro de una celda del editor (maneja None y NaN)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _check(v):
    """True/False seguro para una casilla (maneja NaN)."""
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


encabezado("Editar clases", "Modifica los datos y horarios de una clase", "✏️")

client = get_client()
usuario_actual = st.session_state.get("usuario", "editor_web")


@st.cache_data(ttl=300)
def cargar_catalogos():
    maestros = client.table("maestros").select("clave, nombre_completo").order("nombre_completo").execute().data
    salones = client.table("salones").select("codigo").order("codigo").execute().data
    materias = client.table("materias").select("id, descripcion").execute().data
    # Solo periodos con clases activas (los "concluidos" se ocultan aquí porque no hay nada que editar)
    periodos = (client.table("periodos_con_estado")
                .select("id, descripcion, estado")
                .eq("estado", "activo")
                .order("id", desc=True).execute().data)
    return maestros, salones, materias, periodos


maestros, salones, materias, periodos = cargar_catalogos()
maestros_dict = {m["clave"]: m["nombre_completo"] for m in maestros}
materias_dict = {m["id"]: m["descripcion"] for m in materias}
salon_opciones = [""] + [s["codigo"] for s in salones]
maestro_claves = [None] + [m["clave"] for m in maestros]

# 1. Elegir nivel y clase (ya no por periodo — el periodo se deduce de la clase elegida)
st.subheader("1️⃣ Elige la clase")

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

col_n, col_f, col_b = st.columns([1.2, 2, 0.9])
with col_n:
    nivel_sel = st.selectbox(
        "Nivel académico",
        [k for k, _ in NIVELES_OPCIONES],
        format_func=lambda k: dict(NIVELES_OPCIONES)[k],
        key="edit_nivel_sel"
    )
with col_f:
    filtro_input = st.text_input(
        "Filtrar por CRN, materia o grupo (opcional)",
        value=st.session_state.get("edit_filtro_aplicado", ""),
        key="edit_filtro_input",
        help="Escribe lo que buscas y presiona el botón 'Buscar coincidencias' para aplicar."
    )
with col_b:
    st.write("")
    st.write("")
    if st.button("🔎 Buscar coincidencias", use_container_width=True, key="btn_buscar_edit"):
        st.session_state["edit_filtro_aplicado"] = filtro_input.strip()
        st.rerun()

# El filtro que realmente se usa viene de session_state (se actualiza solo al presionar el botón)
filtro = st.session_state.get("edit_filtro_aplicado", "").strip().upper()

# Traer TODAS las clases (paginando hasta 5000) usando la vista con nivel_codigo
todas_clases = []
offset = 0
while offset < 5000:
    lote = (client.table("v_clases_con_nivel")
            .select("crn, periodo_id, grupo, materia_id, clave_periodo, nivel_codigo")
            .order("crn").order("periodo_id")
            .range(offset, offset + 999)
            .execute().data) or []
    if not lote:
        break
    todas_clases.extend(lote)
    if len(lote) < 1000:
        break
    offset += 1000

# Aplicar filtro por nivel (con normalización 6B ↔ B6, y multicarrera == SIN_NIVEL)
if nivel_sel == "multicarrera":
    clases_filtradas = [c for c in todas_clases if c.get("nivel_codigo") == "SIN_NIVEL"]
elif nivel_sel == "6B":
    clases_filtradas = [c for c in todas_clases if c.get("nivel_codigo") in ("6B", "B6")]
elif nivel_sel != "Todos":
    clases_filtradas = [c for c in todas_clases if c.get("nivel_codigo") == nivel_sel]
else:
    clases_filtradas = todas_clases


def etiqueta(c):
    mat = materias_dict.get(c["materia_id"], c["materia_id"] or "—")
    return f"CRN {c['crn']} · {c.get('grupo') or '—'} · {mat} · Periodo {c['periodo_id']}"


opciones = [c for c in clases_filtradas
            if not filtro or filtro in etiqueta(c).upper() or filtro in str(c["crn"])]
opciones.sort(key=lambda c: (materias_dict.get(c["materia_id"], c["materia_id"] or "").upper(), c["crn"]))

if not opciones:
    st.info("No hay clases que coincidan. Cambia el nivel o el filtro.")
    st.stop()

idx = st.selectbox("Clase a editar", range(len(opciones)), format_func=lambda i: etiqueta(opciones[i]))
crn = opciones[idx]["crn"]
periodo_sel = opciones[idx]["periodo_id"]

# 2. Cargar la clase completa + horarios
clase = (client.table("clases").select("*")
         .eq("crn", crn).eq("periodo_id", periodo_sel).single().execute().data)
horarios = (client.table("horarios")
            .select("dia_semana, hora_inicio, hora_fin, salon_codigo, es_virtual")
            .eq("crn", crn).eq("periodo_id", periodo_sel).order("dia_semana").execute().data)

st.divider()

# La sección de edición NO se muestra hasta que el usuario presione "Editar Clase".
# El flag es por-clase (crn+periodo) para que cambiar de clase resetee el modo.
edit_key = f"edit_activo_{crn}_{periodo_sel}"

if not st.session_state.get(edit_key, False):
    st.info(f"📋 Clase seleccionada: **CRN {crn}** · Periodo {periodo_sel} · "
            f"{materias_dict.get(clase['materia_id'], clase['materia_id'])}")
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("✏️ Editar Clase", type="primary", use_container_width=True, key=f"btn_edit_{crn}_{periodo_sel}"):
            st.session_state[edit_key] = True
            st.rerun()
    st.stop()

# Modo edición activo: mostrar todo lo demás
st.subheader("2️⃣ Edita los datos")
col_cap, col_cancel = st.columns([3, 1])
with col_cap:
    st.caption(f"CRN {crn} · Periodo {periodo_sel} · Materia: {materias_dict.get(clase['materia_id'], clase['materia_id'])}")
with col_cancel:
    if st.button("❌ Cancelar edición", key=f"btn_cancel_{crn}_{periodo_sel}"):
        st.session_state[edit_key] = False
        st.rerun()

k = f"{crn}_{periodo_sel}"

col1, col2, col3 = st.columns(3)
with col1:
    grupo = st.text_input("Grupo", value=clase.get("grupo") or "", key=f"grupo_{k}")
    ma = clase.get("maestro_clave")
    maestro = st.selectbox("Maestro", maestro_claves,
                           index=maestro_claves.index(ma) if ma in maestro_claves else 0,
                           format_func=lambda c: "— Sin maestro —" if c is None else maestros_dict.get(c, str(c)),
                           key=f"maestro_{k}")
with col2:
    capacidad = st.number_input("Capacidad", min_value=0, value=int(clase.get("capacidad_materia") or 0), key=f"cap_{k}")
with col3:
    inscritos = st.number_input("Inscritos", min_value=0, value=int(clase.get("inscritos") or 0), key=f"ins_{k}")

col_fi, col_ff = st.columns(2)
with col_fi:
    fi = st.date_input("Fecha inicio",
                       value=pd.to_datetime(clase["fecha_inicio"]).date() if clase.get("fecha_inicio") else None,
                       key=f"fi_{k}")
with col_ff:
    ff = st.date_input("Fecha fin",
                       value=pd.to_datetime(clase["fecha_fin"]).date() if clase.get("fecha_fin") else None,
                       key=f"ff_{k}")

st.markdown("**Horarios** (agrega, cambia o quita renglones)")
st.caption("💡 Para borrar un renglón: márcalo con la casilla de la izquierda y presiona el 🗑️ que aparece arriba a la derecha. "
           "Para elegir día/hora/salón: **doble click** sobre la celda.")
df_h = pd.DataFrame([{"Día": h["dia_semana"], "Inicio": _hhmm(h["hora_inicio"]), "Fin": _hhmm(h["hora_fin"]),
                      "Salón": h.get("salon_codigo") or "", "Virtual": bool(h.get("es_virtual"))} for h in horarios])
if df_h.empty:
    df_h = pd.DataFrame(columns=["Día", "Inicio", "Fin", "Salón", "Virtual"])

# Preservar horas raras existentes (ej. 18:59) para que no se pierdan al editar.
# Se agregan a las opciones estándar de 30 en 30 min.
_horas_extra = set()
for h in horarios:
    for _key in ("hora_inicio", "hora_fin"):
        _v = _hhmm(h.get(_key))
        if _v and _v not in HORAS_OPCIONES:
            _horas_extra.add(_v)
_opciones_horas = sorted(set(HORAS_OPCIONES) | _horas_extra)

h_edit = st.data_editor(
    df_h, num_rows="dynamic", use_container_width=True, key=f"hor_{k}",
    column_config={
        "Día": st.column_config.SelectboxColumn("Día", options=DIAS, required=True),
        "Inicio": st.column_config.SelectboxColumn("Inicio ⌄", options=_opciones_horas,
                                                    help="Doble click para abrir el menú de horas (cada 30 min)"),
        "Fin": st.column_config.SelectboxColumn("Fin ⌄", options=_opciones_horas,
                                                 help="Doble click para abrir el menú de horas (cada 30 min)"),
        "Salón": st.column_config.SelectboxColumn("Salón", options=salon_opciones),
        "Virtual": st.column_config.CheckboxColumn("Virtual"),
    },
)

# Ver disponibilidad del salón: por RANGO DE FECHAS (no por periodo administrativo),
# porque un salón físico solo puede estar en un lugar a la vez.
with st.expander("🔎 Ver disponibilidad de un salón (para saber qué horarios están libres)"):
    ver_salon = st.selectbox("Salón a revisar", salon_opciones, key="ed_ver_salon")
    if ver_salon:
        if not fi or not ff:
            st.warning("⚠️ Primero pon las fechas de inicio y fin arriba para saber qué está ocupado en esas fechas.")
        else:
            hors_disp = client.rpc("disponibilidad_de_salon", {
                "p_salon": ver_salon,
                "p_fecha_ini": fi.isoformat(),
                "p_fecha_fin": ff.isoformat(),
            }).execute().data or []
            if not hors_disp:
                st.success(f"🟢 {ver_salon} está libre entre {fi.isoformat()} y {ff.isoformat()}.")
            else:
                df_disp, _ = construir_horario_cuadricula(hors_disp, etiqueta_extra="salon")
                if df_disp is not None and not df_disp.empty:
                    st.caption(f"Horario ocupado de {ver_salon} entre {fi.isoformat()} y {ff.isoformat()}. "
                               f"Las celdas con — están libres. (Incluye clases de cualquier periodo cuyas fechas se traslapen.)")
                    st.dataframe(df_disp, use_container_width=True, hide_index=True,
                                 height=38 + len(df_disp) * 38 + 3)

# Vista tradicional (cuadrícula) del horario que estás editando
st.markdown("**Vista tradicional del horario**")
materia_nombre = materias_dict.get(clase["materia_id"], clase["materia_id"] or "")
preview = []
for _, row in h_edit.iterrows():
    dia = _texto(row.get("Día"))
    ini = _texto(row.get("Inicio"))
    fin = _texto(row.get("Fin"))
    if dia in DIAS and _valida_hora(ini) and _valida_hora(fin) and _minutos(ini) < _minutos(fin):
        preview.append({
            "dia_semana": dia, "hora_inicio": _norm(ini), "hora_fin": _norm(fin),
            "salon_codigo": _texto(row.get("Salón")) or None,
            "es_virtual": _check(row.get("Virtual")),
            "materia_nombre": materia_nombre,
        })

if preview:
    df_grid, _ = construir_horario_cuadricula(preview, etiqueta_extra="salon")
    if df_grid is not None and not df_grid.empty:
        st.dataframe(df_grid, use_container_width=True, hide_index=True,
                     height=38 + len(df_grid) * 38 + 3)
else:
    st.caption("Sin horarios válidos que mostrar todavía.")

# 3. Guardar
st.divider()
if st.button("💾 Guardar cambios", type="primary"):
    errores, filas = [], []
    for _, row in h_edit.iterrows():
        dia = _texto(row.get("Día"))
        ini = _texto(row.get("Inicio"))
        fin = _texto(row.get("Fin"))
        if not dia and not ini and not fin:
            continue
        if dia not in DIAS:
            errores.append(f"Día inválido: {dia}")
        elif not _valida_hora(ini) or not _valida_hora(fin):
            errores.append(f"Hora inválida en {dia}: '{ini}' - '{fin}'")
        elif _minutos(ini) >= _minutos(fin):
            errores.append(f"En {dia}, el inicio debe ser menor que el fin.")
        else:
            filas.append({"crn": crn, "periodo_id": periodo_sel, "dia_semana": dia,
                          "hora_inicio": _norm(ini), "hora_fin": _norm(fin),
                          "salon_codigo": _texto(row.get("Salón")) or None,
                          "es_virtual": _check(row.get("Virtual"))})

    # Validación: al menos un horario válido es obligatorio
    if not filas:
        errores.append("Falta agregar al menos un horario. La clase debe tener mínimo un renglón "
                       "con día, hora de inicio y hora de fin.")

    if errores:
        for e in errores:
            st.error(f"❌ {e}")
        st.stop()

    # Revisar que el salón no esté ya ocupado (sin contar esta misma clase)
    choques = []
    for f in filas:
        if f["salon_codigo"] and not f["es_virtual"]:
            ocupado = client.rpc("choques_de_horario", {
                "p_salon": f["salon_codigo"], "p_dia": f["dia_semana"],
                "p_ini": f["hora_inicio"], "p_fin": f["hora_fin"],
                "p_periodo": periodo_sel,
                "p_fecha_ini": fi.isoformat() if fi else None,
                "p_fecha_fin": ff.isoformat() if ff else None,
                "p_excluir_crn": crn,
            }).execute().data
            for o in (ocupado or []):
                choques.append((f, o))

    if choques:
        st.error("🚨 No se guardó: ese salón ya está ocupado a esa hora (habría choque):")
        for f, o in choques:
            st.markdown(f"- **{f['dia_semana']} {f['hora_inicio'][:5]}–{f['hora_fin'][:5]}** en "
                        f"**{f['salon_codigo']}** ya lo usa **CRN {o['crn']} · {o['materia']}** "
                        f"({o['hora_inicio'][:5]}–{o['hora_fin'][:5]})")
        st.info("Cambia el salón o la hora y vuelve a guardar.")
        st.stop()

    # El status se calcula solo según las fechas: 'A' si hoy cae dentro, 'R' si no.
    hoy = date.today()
    status_auto = "A"
    if fi and ff:
        status_auto = "A" if fi <= hoy <= ff else "R"

    try:
        client.table("clases").update({
            "grupo": grupo or None, "maestro_clave": maestro, "status": status_auto,
            "capacidad_materia": int(capacidad), "inscritos": int(inscritos),
            "vacantes": int(capacidad) - int(inscritos),
            "fecha_inicio": fi.isoformat() if fi else None,
            "fecha_fin": ff.isoformat() if ff else None,
            "modificado_por": usuario_actual,
            "modificado_en": datetime.now().isoformat(),
        }).eq("crn", crn).eq("periodo_id", periodo_sel).execute()

        client.table("horarios").delete().eq("crn", crn).eq("periodo_id", periodo_sel).execute()
        if filas:
            client.table("horarios").insert(filas).execute()

        st.success("✅ Cambios guardados. Ya están reflejados en todo el sistema.")
        st.cache_data.clear()
    except Exception as e:
        st.error(f"❌ No se pudo guardar: {e}")