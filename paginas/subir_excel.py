"""
Página para subir un nuevo Excel de Banner, previsualizar y aplicar cambios.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date
import streamlit as st
import pandas as pd

from app.utils.ui import encabezado
from app.loaders.cargar_clases_web import (
    leer_excel_a_dataframe,
    validar_estructura_excel,
    analizar_cambios,
    aplicar_cambios,
)


encabezado("Subir Excel", "Carga un archivo de Banner para actualizar el sistema", "📥")


# ============================================
# PASO 1: SUBIDA DEL ARCHIVO
# ============================================
st.subheader("1️⃣ Selecciona el archivo Excel")

archivo = st.file_uploader(
    "Arrastra el archivo o haz clic para seleccionarlo",
    type=["xlsx"],
    help="Debe ser un archivo en formato Excel (.xlsx) con la estructura del reporte Detalle_Mega_Figpos de Banner."
)

if archivo is None:
    st.info("👆 Sube un archivo Excel para empezar")
    st.stop()


col1, col2 = st.columns(2)
with col1:
    st.metric("📄 Archivo", archivo.name)
with col2:
    tamano_kb = len(archivo.getvalue()) / 1024
    st.metric("📏 Tamaño", f"{tamano_kb:.1f} KB")


# ============================================
# PASO 2: VALIDACIÓN
# ============================================
st.divider()
st.subheader("2️⃣ Validación de estructura")

try:
    df = leer_excel_a_dataframe(archivo.getvalue())
except Exception as e:
    st.error(f"❌ Error al leer el Excel: {e}")
    st.stop()

faltantes = validar_estructura_excel(df)

if faltantes:
    st.error("❌ Faltan columnas obligatorias:")
    for c in faltantes:
        st.markdown(f"   - `{c}`")
    st.stop()

st.success(f"✅ Estructura válida: {len(df)} filas y {len(df.columns)} columnas")


# ============================================
# PASO 3: ANALIZAR
# ============================================
st.divider()
st.subheader("3️⃣ Análisis de cambios")

# Estado de sesión
if 'analisis_resultado' not in st.session_state:
    st.session_state.analisis_resultado = None
    st.session_state.archivo_nombre = None
    st.session_state.cambios_aplicados = False
    st.session_state.reporte_aplicacion = None

# Resetear si cambió el archivo
if st.session_state.archivo_nombre != archivo.name:
    st.session_state.analisis_resultado = None
    st.session_state.archivo_nombre = archivo.name
    st.session_state.cambios_aplicados = False
    st.session_state.reporte_aplicacion = None

col_btn1, col_btn2 = st.columns([1, 3])
with col_btn1:
    if st.button("🔍 Analizar cambios", type="primary", use_container_width=True):
        with st.spinner("Analizando diferencias..."):
            try:
                resultado = analizar_cambios(df)
                st.session_state.analisis_resultado = resultado
                st.session_state.cambios_aplicados = False
                st.session_state.reporte_aplicacion = None
            except Exception as e:
                st.error(f"❌ Error durante el análisis: {e}")
                st.stop()

if st.session_state.analisis_resultado is None:
    st.info("👆 Haz clic en **Analizar cambios** para ver qué pasaría al cargar este Excel")
    st.stop()


# ============================================
# REPORTE DE CAMBIOS
# ============================================
res = st.session_state.analisis_resultado

st.divider()
st.subheader("📊 Reporte de cambios")

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric("➕ Nuevas", len(res['nuevas']))
with col_m2:
    st.metric("✏️ Actualizadas", len(res['actualizadas']))
with col_m3:
    st.metric("🗑️ En base pero no en Excel", len(res['eliminadas']))
with col_m4:
    st.metric("✅ Sin cambios", res['iguales'])


# Alertas
if res['con_cambios_manuales']:
    st.warning(
        f"⚠️ Hay **{len(res['con_cambios_manuales'])} clases con ediciones manuales** "
        f"que pueden ser sobrescritas. Tienes opciones más abajo para decidir."
    )

total_excel = res['total_excel']
total_actual = res['total_actual']
delta_neto = total_excel - total_actual

st.info(
    f"📈 **Resumen:** Base actual: **{total_actual} clases**. "
    f"Excel: **{total_excel} clases**. Después de aplicar: **{total_excel}** "
    f"({'+' if delta_neto >= 0 else ''}{delta_neto})."
)


# ============================================
# DETALLE EXPANDIBLES
# ============================================
if res['nuevas']:
    with st.expander(f"➕ {len(res['nuevas'])} clases NUEVAS"):
        muestra = res['nuevas'][:50]
        filas = []
        for crn, periodo_id in muestra:
            datos = res['clases_excel_raw'].get((crn, periodo_id), {})
            filas.append({
                "CRN": crn, "Periodo": periodo_id,
                "Grupo": datos.get('grupo') or '',
                "Materia": datos.get('materia_id') or '',
                "Inscritos": datos.get('inscritos', 0)
            })
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
        if len(res['nuevas']) > 50:
            st.caption(f"... y {len(res['nuevas']) - 50} más")

# Contador de clases del Excel que se ignoran por ya estar en el archivo
_ignoradas_arch = res.get('nuevas_ya_archivadas', [])
if _ignoradas_arch:
    st.info(
        f"📦 **{len(_ignoradas_arch)} clases del Excel ya están en el archivo** "
        "(fueron procesadas y archivadas anteriormente). Se ignoran automáticamente para no duplicarlas."
    )

if res['actualizadas']:
    with st.expander(f"✏️ {len(res['actualizadas'])} clases ACTUALIZADAS"):
        for c in res['actualizadas'][:20]:
            flag = " 🚨 (cambio manual)" if c['tiene_cambio_manual'] else ""
            st.markdown(f"**CRN {c['crn']} · Periodo {c['periodo_id']} · Grupo {c['grupo']}{flag}**")
            diffs = []
            for campo, vals in c['diferencias'].items():
                diffs.append({
                    "Campo": campo,
                    "Antes": str(vals['antes']) if vals['antes'] is not None else '(vacío)',
                    "Después": str(vals['despues']) if vals['despues'] is not None else '(vacío)'
                })
            st.dataframe(pd.DataFrame(diffs), use_container_width=True, hide_index=True)
            st.markdown("---")
        if len(res['actualizadas']) > 20:
            st.caption(f"... y {len(res['actualizadas']) - 20} más")

if res['eliminadas']:
    # Detectar si es carga PARCIAL: los periodos de las eliminadas son distintos
    # a los que trae el Excel. Si es así, no tiene caso mostrar el bloque de "eliminadas"
    # porque son de otros periodos válidos que no deben tocarse.
    periodos_excel = {periodo for (crn, periodo) in (res.get('clases_excel_raw') or {}).keys()}
    periodos_eliminadas = {periodo for (crn, periodo) in res['eliminadas']}
    eliminadas_del_mismo_periodo = periodos_eliminadas & periodos_excel
    es_carga_parcial = len(eliminadas_del_mismo_periodo) == 0

    if es_carga_parcial:
        st.info(
            f"ℹ️ Hay **{len(res['eliminadas'])} clases** en la base de otros periodos "
            f"(no vienen en este Excel). Como el Excel es una **carga parcial** "
            f"(solo trae el periodo {', '.join(str(p) for p in sorted(periodos_excel))}), "
            "esas clases se mantienen intactas."
        )
    else:
        with st.expander(f"🗑️ {len(res['eliminadas'])} clases en base pero no en Excel"):
            st.warning(
                "⚠️ **Estas clases NO se eliminarán automáticamente.** "
                "Por seguridad, solo se muestran para que revises manualmente si deben quitarse."
            )
            n_mismo = sum(1 for (crn, p) in res['eliminadas'] if p in periodos_excel)
            if n_mismo > 0:
                st.caption(f"⚠️ De las {len(res['eliminadas'])}, **{n_mismo}** son del mismo periodo "
                           "que trae el Excel — probablemente debas revisarlas.")


# ============================================
# PASO 4: APLICAR
# ============================================
st.divider()
st.subheader("4️⃣ Aplicar cambios")

# Si ya se aplicaron, mostrar el reporte y NO permitir hacerlo otra vez
if st.session_state.cambios_aplicados and st.session_state.reporte_aplicacion:
    rep = st.session_state.reporte_aplicacion
    st.success("✅ **Cambios aplicados correctamente**")

    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        st.metric("✅ Nuevas insertadas", rep['nuevas_insertadas'])
        if rep.get('nuevas_ignoradas_archivadas', 0) > 0:
            st.caption(f"📦 {rep['nuevas_ignoradas_archivadas']} ignoradas por ya estar en el archivo.")
    with col_r2:
        st.metric("✏️ Actualizadas", rep['actualizadas'])
    with col_r3:
        st.metric("🔒 Saltadas (manuales)", rep['actualizadas_saltadas'])

    if rep.get('auto_archivadas', 0) > 0:
        st.info(f"📦 **{rep['auto_archivadas']} clases vencidas se archivaron automáticamente** "
                "tras la carga (cron interno).")

    st.caption(f"📅 Horarios actualizados: {rep['horarios_actualizados']}")

    st.caption(
        f"🗂️ Catálogos sincronizados — "
        f"Periodos: {rep.get('periodos_sincronizados', 0)} · "
        f"Maestros: {rep.get('maestros_sincronizados', 0)} · "
        f"Materias: {rep.get('materias_sincronizados', 0)}"
    )

    if rep['errores']:
        with st.expander(f"⚠️ Se registraron {len(rep['errores'])} errores"):
            for err in rep['errores'][:20]:
                st.markdown(f"   - {err}")
            if len(rep['errores']) > 20:
                st.caption(f"... y {len(rep['errores']) - 20} más")

    st.info(
        "💡 Para subir otro archivo, recarga la página o sube uno nuevo arriba. "
        "Recuerda que los datos actualizados ya están reflejados en todas las páginas del sistema."
    )
    st.stop()

# Sin cambios que aplicar
total_a_aplicar = len(res['nuevas']) + len(res['actualizadas'])
if total_a_aplicar == 0:
    st.success("✅ No hay cambios por aplicar. La base ya está sincronizada con el Excel.")
    st.stop()


# Opción para cambios manuales (si existen)
respetar_manuales = True
if res['con_cambios_manuales']:
    st.markdown("**¿Qué hacer con las clases que tienen ediciones manuales?**")

    opcion_manual = st.radio(
        "Selecciona una opción:",
        [
            f"🔒 Respetar los {len(res['con_cambios_manuales'])} cambios manuales (recomendado)",
            "⚠️ Sobrescribir todo, incluyendo los cambios manuales"
        ],
        key="opcion_manuales"
    )

    respetar_manuales = opcion_manual.startswith("🔒")


# Resumen final antes de aplicar
st.markdown("**Vas a aplicar los siguientes cambios:**")

cambios_resumen = []
if res['nuevas']:
    cambios_resumen.append(f"✅ Insertar **{len(res['nuevas'])} clases nuevas**")

if res['actualizadas']:
    if respetar_manuales and res['con_cambios_manuales']:
        actualizables = len(res['actualizadas']) - len(res['con_cambios_manuales'])
        cambios_resumen.append(
            f"✏️ Actualizar **{actualizables} clases** (saltando {len(res['con_cambios_manuales'])} con cambios manuales)"
        )
    else:
        cambios_resumen.append(f"✏️ Actualizar **{len(res['actualizadas'])} clases**")

for c in cambios_resumen:
    st.markdown(f"   {c}")

st.warning(
    "⚠️ **Esta acción modificará la base de datos.** Los cambios SÍ se aplicarán de inmediato. "
    "Asegúrate de revisar los detalles antes de continuar."
)


# ¿Hay CRN del Excel que están en archivadas?
_arch_list = res.get("en_excel_y_archivadas") or []
restaurar_archivadas = False
if _arch_list:
    info = res.get("info_archivadas") or {}

    # Contar cuántas de las archivadas están vencidas vs no vencidas
    hoy_iso = date.today().isoformat()
    vencidas = 0
    no_vencidas = 0
    for crn_r, per_r in _arch_list:
        d = info.get((crn_r, per_r), {})
        ff = str(d.get("fecha_fin") or "9999-12-31")
        if ff < hoy_iso:
            vencidas += 1
        else:
            no_vencidas += 1

    if no_vencidas == 0:
        # Todas están vencidas: NO tiene sentido restaurarlas (se re-archivarían de inmediato)
        st.info(
            f"📦 **{len(_arch_list)} clases del Excel están archivadas** y las **{vencidas}** ya "
            "cumplieron su fecha de fin. Se saltan automáticamente (la opción de restaurar "
            "no aparece porque volverían a archivarse de inmediato)."
        )
    else:
        st.warning(
            f"📦 **{len(_arch_list)} clases del Excel están archivadas actualmente** "
            f"({no_vencidas} aún no han vencido, {vencidas} sí). "
            "Si NO restauras, esas clases se saltan y siguen archivadas. "
            "Si SÍ restauras, se BORRAN del archivo y se cargan de nuevo con los datos del Excel."
        )

    with st.expander("Ver CRN archivadas que trae el Excel"):
        filas_ar = []
        for crn_r, per_r in _arch_list[:200]:
            d = info.get((crn_r, per_r), {})
            ff = str(d.get("fecha_fin") or "")
            filas_ar.append({
                "CRN": crn_r, "Periodo": per_r,
                "Materia": d.get("materia_id", ""),
                "Fecha fin": ff,
                "Estado": "❌ Vencida" if ff and ff < hoy_iso else "🟢 No vencida",
                "Archivada por": d.get("archivado_por", ""),
                "Archivada en": (d.get("archivado_en") or "")[:10],
            })
        st.dataframe(filas_ar, use_container_width=True, hide_index=True)
        if len(_arch_list) > 200:
            st.caption(f"Mostrando 200 de {len(_arch_list)}.")

    # El checkbox de restaurar solo aparece si hay al menos una archivada NO vencida
    if no_vencidas > 0:
        restaurar_archivadas = st.checkbox(
            f"♻️ Restaurar las {no_vencidas} clases archivadas NO vencidas usando los datos del Excel",
            key="check_restaurar_arch"
        )

# Confirmación con checkbox
confirmacion = st.checkbox(
    "Confirmo que quiero aplicar estos cambios a la base de datos",
    key="check_confirmar"
)

col_apl1, col_apl2 = st.columns([1, 3])
with col_apl1:
    if st.button(
        "🚀 Aplicar cambios",
        type="primary",
        disabled=not confirmacion,
        use_container_width=True
    ):
        with st.spinner("Aplicando cambios... no cierres esta ventana"):
            try:
                reporte = aplicar_cambios(
                    res,
                    respetar_cambios_manuales=respetar_manuales,
                    restaurar_archivadas=restaurar_archivadas,
                    usuario="web_admin"
                )
                st.session_state.cambios_aplicados = True
                st.session_state.reporte_aplicacion = reporte
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al aplicar: {e}")