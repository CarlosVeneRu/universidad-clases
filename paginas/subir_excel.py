"""
Página para subir un nuevo Excel de Banner, previsualizar y aplicar cambios.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd

from app.loaders.cargar_clases_web import (
    leer_excel_a_dataframe,
    validar_estructura_excel,
    analizar_cambios,
    aplicar_cambios,
)


st.title("📥 Subir Excel de Banner")
st.markdown("Sube un nuevo reporte de Banner y previsualiza los cambios antes de aplicarlos.")
st.divider()


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
    with st.expander(f"🗑️ {len(res['eliminadas'])} clases en base pero no en Excel"):
        st.warning(
            "⚠️ **Estas clases NO se eliminarán automáticamente.** "
            "Por seguridad, solo se muestran para que revises manualmente si deben quitarse."
        )


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
    with col_r2:
        st.metric("✏️ Actualizadas", rep['actualizadas'])
    with col_r3:
        st.metric("🔒 Saltadas (manuales)", rep['actualizadas_saltadas'])
    
    st.caption(f"📅 Horarios actualizados: {rep['horarios_actualizados']}")
    
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
                    usuario="web_admin"
                )
                st.session_state.cambios_aplicados = True
                st.session_state.reporte_aplicacion = reporte
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al aplicar: {e}")