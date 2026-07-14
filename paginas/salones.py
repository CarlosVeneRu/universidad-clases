"""
Página de salones: ocupación, disponibilidad y uso.
Filtro por RANGO DE FECHAS (más intuitivo que 'periodo').
Con detección correcta de choques y descarga a Excel.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date, timedelta
import streamlit as st
import pandas as pd
from app.utils.ui import encabezado

from app.utils.queries import (
    buscar_salones_por_rango, clases_en_salon_por_rango, cargar_tipos_salon
)
from app.utils.horarios import (
    DIAS_ORDEN, DIAS_CORTO, hora_a_minutos, minutos_a_hora,
    clases_se_solapan, construir_horario_cuadricula, generar_excel_horario
)


def hora_a_minutos(hora_str):
    partes = str(hora_str).split(':')
    return int(partes[0]) * 60 + int(partes[1])


def minutos_a_hora(minutos):
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def clases_se_solapan(h1, h2):
    """Devuelve True solo si dos clases REALMENTE se solapan en tiempo."""
    ini1 = hora_a_minutos(h1['hora_inicio'])
    fin1 = hora_a_minutos(h1['hora_fin'])
    ini2 = hora_a_minutos(h2['hora_inicio'])
    fin2 = hora_a_minutos(h2['hora_fin'])
    return ini1 < fin2 and ini2 < fin1


def _nivel_de_clave(clave):
    """De 'BL6', '1LX', etc. saca el código de nivel corto. Si no lo reconoce, 'Otros'."""
    if not clave:
        return "—"
    clave = str(clave).upper()
    for cod in ["LX", "NC", "PT", "L6", "LS", "B6", "6B"]:
        if cod in clave:
            return cod
    return "Otros"


def _fmt_fecha(f):
    """Devuelve una fecha como 'dd/mm/yyyy' o '—' si viene vacía."""
    if not f:
        return "—"
    try:
        return pd.to_datetime(f).strftime("%d/%m/%Y")
    except Exception:
        return str(f)


def main():
    encabezado("Salones", "Uso y disponibilidad de las aulas", "🚪")

    # =====================================================================
    # FILTROS: código, tipo, y RANGO DE FECHAS
    # =====================================================================
    hoy = date.today()
    fi_default = hoy
    ff_default = hoy + timedelta(days=30)

    col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 1.4, 1.4, 1.3, 0.9])
    with col1:
        codigo_busqueda = st.text_input("🔍 Buscar por código", placeholder="Ej: 11-A001")
    with col2:
        tipos = cargar_tipos_salon()
        tipo_filtro = st.selectbox("🏷️ Tipo de salón", ["Todos"] + tipos)
    with col3:
        fecha_ini = st.date_input("📅 Fecha inicio", value=fi_default, key="sal_fi")
    with col4:
        fecha_fin = st.date_input("📅 Fecha fin", value=ff_default, key="sal_ff")
    with col5:
        capacidad_min = st.number_input(
            "👥 Capacidad mín.", min_value=0, step=1, value=0,
            help="Solo muestra salones con capacidad ≥ a este número. Deja en 0 para ver todos."
        )
    with col6:
        st.write("")
        st.write("")
        buscar = st.button("🔍 Buscar", type="primary", use_container_width=True)

    if fecha_ini and fecha_fin and fecha_ini > fecha_fin:
        st.error("⚠️ La fecha de inicio no puede ser posterior a la fecha de fin.")
        return

    st.caption(
        f"📅 Uso calculado para el rango: **{_fmt_fecha(fecha_ini)} a {_fmt_fecha(fecha_fin)}**. "
        "Incluye todas las clases cuyas fechas se traslapan con este rango, sin importar de qué periodo sean."
    )

    salones = buscar_salones_por_rango(codigo_busqueda, tipo_filtro, fecha_ini, fecha_fin)

    if capacidad_min > 0:
        salones = [s for s in salones if (s.get('capacidad') or 0) >= capacidad_min]

    if not salones:
        st.warning("⚠️ No se encontraron salones con esos filtros")
        return

    # =====================================================================
    # SELECTOR DEL SALÓN (queda justo debajo de los filtros)
    # =====================================================================
    def formato_salon(s):
        porcentaje = s['porcentaje_uso']
        if porcentaje == 0:
            emoji = "⚪"
        elif porcentaje < 30:
            emoji = "🟢"
        elif porcentaje < 70:
            emoji = "🟡"
        else:
            emoji = "🔴"
        return f"{emoji} {s['codigo']} · Cap: {s.get('capacidad', 0)} · Uso: {porcentaje:.1f}%"

    salones_ordenados = sorted(salones, key=lambda s: s['codigo'])
    opciones = [formato_salon(s) for s in salones_ordenados]
    seleccion = st.selectbox("Selecciona un salón para ver su ocupación", opciones)

    salon_codigo = seleccion.split(" · ")[0].split(" ", 1)[1]
    salon_obj = next(s for s in salones_ordenados if s['codigo'] == salon_codigo)

    # =====================================================================
    # RESUMEN GLOBAL (después del selector)
    # =====================================================================
    total_salones = len(salones)
    salones_libres = sum(1 for s in salones if s['porcentaje_uso'] == 0)
    salones_alto_uso = sum(1 for s in salones if s['porcentaje_uso'] >= 70)
    promedio_uso = sum(s['porcentaje_uso'] for s in salones) / total_salones if total_salones > 0 else 0

    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    with col_r1:
        st.metric("🚪 Salones encontrados", total_salones)
    with col_r2:
        st.metric("🟢 Sin uso", salones_libres)
    with col_r3:
        st.metric("🔴 Uso alto (≥70%)", salones_alto_uso)
    with col_r4:
        st.metric("📊 Uso promedio", f"{promedio_uso:.1f}%")

    st.divider()

    # =====================================================================
    # GATE: mostrar detalle solo si el usuario presiona el botón
    # =====================================================================
    detalle_key = f"detalle_salon_activo_{salon_codigo}"
    if not st.session_state.get(detalle_key, False):
        st.info(f"🚪 Salón seleccionado: **{salon_obj['codigo']}** · "
                f"{salon_obj.get('descripcion', 'N/A')} · "
                f"Capacidad {salon_obj.get('capacidad', 0)} · "
                f"Tipo: {salon_obj.get('tipo_uso_descripcion', 'N/A')}")
        col_btn, _ = st.columns([1, 3])
        with col_btn:
            if st.button("🔎 Ver detalle del salón", type="primary",
                         use_container_width=True, key=f"btn_ver_{salon_codigo}"):
                st.session_state[detalle_key] = True
                st.rerun()
        return  # No mostrar el resto hasta que active el botón

    # =====================================================================
    # DETALLE DEL SALÓN SELECCIONADO
    # =====================================================================
    col_titulo, col_ocultar = st.columns([3, 1])
    with col_titulo:
        st.header(f"🚪 {salon_obj['codigo']}")
    with col_ocultar:
        st.write("")
        st.write("")
        if st.button("❌ Ocultar detalle", key=f"btn_ocultar_{salon_codigo}"):
            st.session_state[detalle_key] = False
            st.rerun()

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("📝 Descripción", salon_obj.get('descripcion', 'N/A'))
    with col_m2:
        st.metric("👥 Capacidad", salon_obj.get('capacidad', 0))
    with col_m3:
        st.metric("🏷️ Tipo", salon_obj.get('tipo_uso_descripcion', 'N/A'))

    horarios = clases_en_salon_por_rango(salon_codigo, fecha_ini, fecha_fin)

    if not horarios:
        st.info(f"Este salón no tiene clases entre {_fmt_fecha(fecha_ini)} y {_fmt_fecha(fecha_fin)}.")
        return

    # Métricas del salón seleccionado
    clases_distintas = len(set((h['crn'], h['periodo_id']) for h in horarios))
    horas_uso = 0
    for h in horarios:
        try:
            ini = hora_a_minutos(h['hora_inicio'])
            fin = hora_a_minutos(h['hora_fin'])
            horas_uso += (fin - ini) / 60
        except Exception:
            pass

    horas_disponibles = 90
    porcentaje_uso = min((horas_uso / horas_disponibles * 100), 100) if horas_disponibles > 0 else 0

    col_u1, col_u2, col_u3 = st.columns(3)
    with col_u1:
        st.metric("📊 Clases asignadas", clases_distintas)
    with col_u2:
        st.metric("⏰ Horas/semana", f"{horas_uso:.1f}")
    with col_u3:
        st.metric("📈 % de uso", f"{porcentaje_uso:.1f}%")

    st.progress(min(porcentaje_uso / 100, 1.0),
                text=f"Ocupación semanal: {porcentaje_uso:.1f}% (de 90 hrs/semana disponibles)")

    st.divider()

    # =====================================================================
    # OCUPACIÓN DETALLADA (con fechas de cada clase)
    # =====================================================================
    st.subheader("📋 Ocupación detallada")
    st.caption(f"Clases activas en el rango {_fmt_fecha(fecha_ini)} a {_fmt_fecha(fecha_fin)}.")

    horarios_ordenados = sorted(
        horarios,
        key=lambda h: (DIAS_ORDEN.index(h['dia_semana']) if h['dia_semana'] in DIAS_ORDEN else 99, h['hora_inicio'])
    )

    filas = []
    for h in horarios_ordenados:
        clase_info = h.get('clases') or {}
        materia = (clase_info.get('materias') or {})
        maestro = (clase_info.get('maestros') or {})

        filas.append({
            "Día": h['dia_semana'],
            "Hora": f"{h['hora_inicio'][:5]} - {h['hora_fin'][:5]}",
            "CRN": h['crn'],
            "Periodo": f"{h['periodo_id']} · {_nivel_de_clave(clase_info.get('clave_periodo'))}",
            "Grupo": clase_info.get('grupo') or '',
            "Materia": materia.get('descripcion') or '(multi)',
            "Maestro": maestro.get('nombre_completo') or 'Sin asignar',
            "Fecha inicio": _fmt_fecha(clase_info.get('fecha_inicio')),
            "Fecha fin": _fmt_fecha(clase_info.get('fecha_fin')),
        })

    df_detalle = pd.DataFrame(filas)
    st.dataframe(df_detalle, use_container_width=True, hide_index=True, height=300)

    st.divider()

    # =====================================================================
    # HORARIO SEMANAL (VISTA TRADICIONAL)
    # =====================================================================
    st.subheader("📅 Horario semanal (vista tradicional)")
    st.caption(
        f"Vista hora por hora del rango {_fmt_fecha(fecha_ini)} a {_fmt_fecha(fecha_fin)}. "
        "Las celdas con — están libres. ⚠️ marca choques reales. "
        "Ver arriba en 'Ocupación detallada' las fechas exactas de cada clase."
    )

    df_cuadricula, info_choques = construir_horario_cuadricula(horarios, etiqueta_extra="materia")

    if df_cuadricula is not None and not df_cuadricula.empty:
        num_filas = len(df_cuadricula)
        altura_calculada = 38 + (num_filas * 38) + 3

        st.dataframe(
            df_cuadricula,
            use_container_width=True,
            hide_index=True,
            height=altura_calculada
        )

        if info_choques:
            st.divider()
            st.warning(f"🚨 **Se detectaron {len(info_choques)} choques REALES en este salón**")

            for choque in info_choques:
                c1 = choque['clase_1']
                c2 = choque['clase_2']

                clase1_info = c1.get('clases') or {}
                clase2_info = c2.get('clases') or {}
                materia1 = (clase1_info.get('materias') or {}).get('descripcion', '(multi)')
                materia2 = (clase2_info.get('materias') or {}).get('descripcion', '(multi)')
                maestro1 = (clase1_info.get('maestros') or {}).get('nombre_completo', 'Sin asignar')
                maestro2 = (clase2_info.get('maestros') or {}).get('nombre_completo', 'Sin asignar')

                with st.expander(f"⚠️ {choque['dia']}: CRN {c1['crn']} vs CRN {c2['crn']}"):
                    col_c1, col_c2 = st.columns(2)
                    with col_c1:
                        st.markdown(f"**CRN {c1['crn']}** (Periodo {c1['periodo_id']})")
                        st.markdown(f"📚 Materia: {materia1}")
                        st.markdown(f"👨‍🏫 Maestro: {maestro1}")
                        st.markdown(f"⏰ Horario: {c1['hora_inicio'][:5]} - {c1['hora_fin'][:5]}")
                        st.markdown(f"📅 Fechas: {_fmt_fecha(clase1_info.get('fecha_inicio'))} a "
                                    f"{_fmt_fecha(clase1_info.get('fecha_fin'))}")
                    with col_c2:
                        st.markdown(f"**CRN {c2['crn']}** (Periodo {c2['periodo_id']})")
                        st.markdown(f"📚 Materia: {materia2}")
                        st.markdown(f"👨‍🏫 Maestro: {maestro2}")
                        st.markdown(f"⏰ Horario: {c2['hora_inicio'][:5]} - {c2['hora_fin'][:5]}")
                        st.markdown(f"📅 Fechas: {_fmt_fecha(clase2_info.get('fecha_inicio'))} a "
                                    f"{_fmt_fecha(clase2_info.get('fecha_fin'))}")

                    if maestro1 == maestro2 and maestro1 != 'Sin asignar':
                        st.info("💡 Ambas clases tienen el **mismo maestro** — podría ser una clase espejo.")
                    elif materia1 == materia2:
                        st.info("💡 Ambas son la **misma materia** — podría ser un grupo dividido.")
                    else:
                        st.error("🔴 **Choque real**: dos clases distintas pidiendo el mismo salón al mismo tiempo.")

        # Botón de descarga Excel
        st.divider()
        st.subheader("📥 Descargar horario")

        info_resumen = {
            "Código": salon_obj['codigo'],
            "Descripción": salon_obj.get('descripcion', 'N/A'),
            "Capacidad": salon_obj.get('capacidad', 0),
            "Tipo": salon_obj.get('tipo_uso_descripcion', 'N/A'),
            "Rango consultado": f"{_fmt_fecha(fecha_ini)} a {_fmt_fecha(fecha_fin)}",
            "Horas/semana": f"{horas_uso:.1f}",
            "% de uso": f"{porcentaje_uso:.1f}%"
        }

        excel_bytes = generar_excel_horario(
            titulo="HORARIO DEL SALÓN",
            subtitulo=salon_codigo,
            info_dict=info_resumen,
            df_detalle=df_detalle,
            df_cuadricula=df_cuadricula
        )

        st.download_button(
            label="📥 Descargar Horario en Excel",
            data=excel_bytes,
            file_name=f"horario_salon_{salon_codigo}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
    else:
        st.info("No hay datos suficientes para mostrar la cuadrícula")


main()