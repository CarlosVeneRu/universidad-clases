"""
Página de maestros: búsqueda, lista y detalle con horario semanal estilo tradicional.
Incluye descarga del horario en Excel.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date
import streamlit as st
import pandas as pd
from app.utils.ui import encabezado

from app.utils.queries import (
    buscar_maestros, clases_de_maestro, clases_agrupadas_de_maestro,
    maestros_con_clases_activas
)
from app.utils.horarios import (
    DIAS_ORDEN, DIAS_CORTO, hora_a_minutos,
    construir_horario_cuadricula, generar_excel_horario
)


def _nivel_de_clave(clave):
    """De 'BL6', '1LX', etc. saca el código de nivel corto. Si no lo reconoce, 'Otros'."""
    if not clave:
        return "—"
    clave = str(clave).upper()
    for cod in ["LX", "NC", "PT", "L6", "LS", "B6", "6B"]:
        if cod in clave:
            return cod
    return "Otros"


def main():
    encabezado("Maestros", "Carga docente y horarios", "👨‍🏫")

    # Placeholder para el contador (se llena más abajo cuando ya sabemos cuántos hay)
    contador_ph = st.empty()

    # ===== BÚSQUEDA (por nombre o por docente ID) =====
    col1, col2 = st.columns([3, 1])
    with col1:
        nombre_busqueda = st.text_input(
            "🔍 Buscar maestro por nombre o docente ID",
            placeholder="Ej: GONZALEZ, MARIA · o un número: 12345"
        )
    with col2:
        st.write("")
        st.write("")
        if st.button("📋 Ver todos los maestros", use_container_width=True):
            nombre_busqueda = " "

    maestros = buscar_maestros(nombre_busqueda)

    if not maestros:
        if nombre_busqueda.strip():
            st.warning("⚠️ No se encontraron maestros con ese texto")
        else:
            st.info("👆 Escribe un nombre o docente ID para buscar")
        return

    # 🟢 si el maestro tiene al menos una clase que no ha vencido (hoy o futura). 🔴 si no.
    claves_activas = maestros_con_clases_activas()

    # Toggle alineado a la derecha para filtrar solo los 🟢
    _, col_tog_activos = st.columns([3, 1])
    with col_tog_activos:
        solo_activos = st.toggle(
            "🟢 Solo maestros con clases activas",
            value=False,
            help="Muestra únicamente maestros con al menos una clase que no haya vencido."
        )

    if solo_activos:
        maestros = [m for m in maestros if m['clave'] in claves_activas]

    if not maestros:
        st.warning("⚠️ No hay maestros con clases activas que coincidan con la búsqueda.")
        return

    contador_ph.success(f"✅ {len(maestros)} maestros encontrados")

    opciones = [f"{'🟢' if m['clave'] in claves_activas else '🔴'} {m['clave']} · {m['nombre_completo']}"
                for m in maestros]
    seleccion = st.selectbox("Selecciona un maestro para ver detalle", opciones)

    # La opción empieza con emoji + espacio + clave, así que tomamos el último token antes del "·"
    maestro_clave = int(seleccion.split(" · ")[0].split(" ")[-1])
    maestro_obj = next(m for m in maestros if m['clave'] == maestro_clave)

    st.divider()

    # ===== DETALLE DEL MAESTRO =====
    st.header(f"📋 {maestro_obj['nombre_completo']}")
    st.metric("🆔 Docente ID", maestro_clave)

    # Toggle de agrupar (alineado a la derecha)
    _, col_tog = st.columns([3, 1])
    with col_tog:
        ver_agrupado = st.toggle(
            "🔗 Ver clases agrupadas",
            value=True,
            help="Junta automáticamente los grupos divididos (ej: 17A + 17B = una sola clase)"
        )

    # Obtener clases (todas, sin filtrar por periodo)
    if ver_agrupado:
        clases = clases_agrupadas_de_maestro(maestro_clave, None)
    else:
        clases = clases_de_maestro(maestro_clave, None)
        for c in clases:
            c['es_agrupada'] = False
            c['crns'] = [c['crn']]
            c['grupos'] = [c.get('grupo') or '']
            c['num_partes'] = 1

    # Filtrar clases vencidas: solo mostrar las activas o las que aún no terminan.
    hoy = date.today().isoformat()
    clases = [c for c in clases if not c.get('fecha_fin') or str(c['fecha_fin']) >= hoy]

    if not clases:
        st.info("Este maestro no tiene clases activas o próximas.")
        return

    # ===== MÉTRICAS DE CARGA DOCENTE =====
    total_clases = len(clases)
    total_estudiantes = sum(c.get('inscritos', 0) for c in clases)

    # Recolectar todos los horarios del maestro (con info enriquecida)
    todos_horarios = []
    for c in clases:
        materia_nombre = (c.get('materias') or {}).get('descripcion') or '(sin materia)'
        for h in (c.get('horarios') or []):
            h_copia = dict(h)
            h_copia['materia_nombre'] = materia_nombre
            # Que las fechas viajen dentro del horario, para que clases_se_solapan
            # pueda descartar choques de periodos que no se traslapan (ej: feb-jun vs ago-ene)
            h_copia['clases'] = {
                'crn': c.get('crn'),
                'periodo_id': c.get('periodo_id'),
                'fecha_inicio': c.get('fecha_inicio'),
                'fecha_fin': c.get('fecha_fin'),
            }
            todos_horarios.append(h_copia)

    # Calcular horas semanales
    horas_semanales = 0
    for h in todos_horarios:
        try:
            ini = hora_a_minutos(h['hora_inicio'])
            fin = hora_a_minutos(h['hora_fin'])
            horas_semanales += (fin - ini) / 60
        except Exception:
            pass

    # Detectar salones únicos donde imparte
    salones_unicos = set(
        h.get('salon_codigo') for h in todos_horarios
        if h.get('salon_codigo') and not h.get('es_virtual')
    )

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("📝 Clases asignadas", total_clases)
    with col_m2:
        st.metric("👥 Estudiantes totales", total_estudiantes)
    with col_m3:
        st.metric("⏰ Horas semanales", f"{horas_semanales:.1f} hrs")
    with col_m4:
        st.metric("🚪 Salones distintos", len(salones_unicos))

    st.divider()

    # ===== TABLA DE CLASES (LISTADO) =====
    st.subheader("📚 Clases que imparte")

    filas = []
    for c in clases:
        materia = c.get("materias") or {}
        horarios = c.get("horarios") or []

        # Construir resumen de horario
        horario_resumen = []
        for h in horarios:
            dia = h['dia_semana'][:3]
            salon = h.get('salon_codigo') or "🌐VIRTUAL"
            horario_resumen.append(f"{dia} {h['hora_inicio'][:5]}-{h['hora_fin'][:5]} ({salon})")

        if c.get('es_agrupada'):
            crns_str = f"🔗 {', '.join(str(x) for x in c['crns'])}"
            grupos_str = ', '.join(c['grupos'])
        else:
            crns_str = str(c['crns'][0]) if c.get('crns') else str(c.get('crn', ''))
            grupos_str = c['grupos'][0] if c.get('grupos') else c.get('grupo', '')

        filas.append({
            "CRN(s)": crns_str,
            "Periodo": f"{c['periodo_id']} · {_nivel_de_clave(c.get('clave_periodo'))}",
            "Grupo(s)": grupos_str,
            "Materia": materia.get("descripcion") or "(sin materia)",
            "Inscritos": f"{c.get('inscritos', 0)}/{c.get('capacidad_materia', 0)}",
            "Status": c.get("status") or "",
            "Horario": "; ".join(horario_resumen) if horario_resumen else "Sin horario",
            "F. Inicio": c.get("fecha_inicio") or "",
            "F. Fin": c.get("fecha_fin") or ""
        })

    df_detalle = pd.DataFrame(filas)

    altura_calc = 38 + (len(df_detalle) * 38) + 3
    altura_calc = min(altura_calc, 500)

    st.dataframe(df_detalle, use_container_width=True, hide_index=True, height=altura_calc)

    if ver_agrupado:
        agrupadas = sum(1 for c in clases if c.get('es_agrupada'))
        if agrupadas > 0:
            st.caption(f"🔗 {agrupadas} de las {len(clases)} filas son clases agrupadas")

    st.divider()

    # ===== HORARIO SEMANAL TRADICIONAL =====
    st.subheader("📅 Horario semanal (vista tradicional)")
    st.caption("Vista hora por hora. Las celdas con — están libres. ⚠️ marca cuando el maestro tiene 2 clases al mismo tiempo.")

    if not todos_horarios:
        st.info("Este maestro no tiene horarios asignados")
        return

    df_cuadricula, info_choques = construir_horario_cuadricula(todos_horarios, etiqueta_extra="salon")

    if df_cuadricula is not None and not df_cuadricula.empty:
        altura_grid = 38 + (len(df_cuadricula) * 38) + 3

        st.dataframe(
            df_cuadricula,
            use_container_width=True,
            hide_index=True,
            height=altura_grid
        )

        # Alertas si el maestro tiene choques (imparte 2 clases al mismo tiempo)
        if info_choques:
            st.divider()
            st.warning(f"🚨 **Este maestro tiene {len(info_choques)} choques en su horario** (imparte 2 clases al mismo tiempo)")

            for choque in info_choques[:5]:  # Mostrar máximo 5
                c1 = choque['clase_1']
                c2 = choque['clase_2']

                with st.expander(f"⚠️ {choque['dia']} {c1['hora_inicio'][:5]} — Choque"):
                    col_c1, col_c2 = st.columns(2)
                    with col_c1:
                        st.markdown(f"**Materia 1:** {c1.get('materia_nombre', 'N/A')}")
                        st.markdown(f"**Horario:** {c1['hora_inicio'][:5]} - {c1['hora_fin'][:5]}")
                        st.markdown(f"**Salón:** {c1.get('salon_codigo') or '🌐 Virtual'}")
                    with col_c2:
                        st.markdown(f"**Materia 2:** {c2.get('materia_nombre', 'N/A')}")
                        st.markdown(f"**Horario:** {c2['hora_inicio'][:5]} - {c2['hora_fin'][:5]}")
                        st.markdown(f"**Salón:** {c2.get('salon_codigo') or '🌐 Virtual'}")

        # ===== BOTÓN DE DESCARGA EXCEL =====
        st.divider()
        st.subheader("📥 Descargar horario")

        info_resumen = {
            "Maestro": maestro_obj['nombre_completo'],
            "Docente ID": maestro_clave,
            "Clases asignadas": total_clases,
            "Estudiantes totales": total_estudiantes,
            "Horas semanales": f"{horas_semanales:.1f} hrs",
            "Salones distintos": len(salones_unicos)
        }

        # Limpiar el nombre para el archivo (sin acentos ni espacios raros)
        nombre_archivo = maestro_obj['nombre_completo'].replace(' ', '_').replace(',', '')[:50]

        excel_bytes = generar_excel_horario(
            titulo="HORARIO DEL MAESTRO",
            subtitulo=maestro_obj['nombre_completo'],
            info_dict=info_resumen,
            df_detalle=df_detalle,
            df_cuadricula=df_cuadricula
        )

        st.download_button(
            label="📥 Descargar Horario en Excel",
            data=excel_bytes,
            file_name=f"horario_maestro_{nombre_archivo}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
    else:
        st.info("No hay datos suficientes para mostrar la cuadrícula")


main()