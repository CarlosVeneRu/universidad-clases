"""
Página para exportar los datos del sistema a Excel.
Genera un archivo similar al de Banner con los datos actuales.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import io
import streamlit as st
import pandas as pd
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from app.utils.ui import encabezado

from app.utils.queries import get_client, cargar_periodos


encabezado("Exportar Datos", "Descarga la información en formato Excel", "📤")


# Filtros
st.subheader("🎯 Filtros del export")
periodos = cargar_periodos()
opciones_periodo = ["Todos los periodos"] + [f"{p['id']} - {p['descripcion']}" for p in periodos]
periodo_sel = st.selectbox("Periodo a exportar", opciones_periodo)

periodo_filtro = None
if not periodo_sel.startswith("Todos"):
    periodo_filtro = int(periodo_sel.split(" - ")[0])

st.divider()


def generar_excel():
    """Construye el DataFrame con todas las clases y sus horarios."""
    client = get_client()
    
    # 1. Cargar las clases (con todos sus datos relacionados)
    query = client.table("clases").select(
        "crn, periodo_id, grupo, clave_periodo, status, "
        "fecha_inicio, fecha_fin, inscritos, capacidad_materia, capacidad_escenario, vacantes, "
        "tipo_curso, tipo_horario, metodo, sin_docente, sin_horario, "
        "impartido_id, impartido_descripcion, modulo_id, modulo_descripcion, "
        "semanas_curso, horas_long, "
        "materias(id, descripcion, grado_materia, area_concentracion, semanas_curso, tipos_uso_compatibles), "
        "maestros(clave, nombre_completo), "
        "carreras(clave_hpn, nombre_hpn, clave_banner, nombre_banner, departamento_id, nivel_id, nivel_descripcion), "
        "campus(id, nombre), "
        "periodos(id, anio, ciclo, descripcion)"
    )
    
    if periodo_filtro:
        query = query.eq("periodo_id", periodo_filtro)
    
    # Paginar con ORDER BY estable (evita duplicados y saltos)
    query = query.order("crn").order("periodo_id")
    
    clases_data = []
    offset = 0
    batch_size = 1000
    
    while True:
        batch = query.range(offset, offset + batch_size - 1).execute()
        if not batch.data:
            break
        clases_data.extend(batch.data)
        if len(batch.data) < batch_size:
            break
        offset += batch_size
    
    if not clases_data:
        return None
    
    # 2. Cargar TODOS los horarios de las clases filtradas
    
    # Obtener horarios filtrando por periodo si aplica
    h_query = client.table("horarios").select(
        "crn, periodo_id, dia_semana, hora_inicio, hora_fin, salon_codigo, es_virtual"
    )
    if periodo_filtro:
        h_query = h_query.eq("periodo_id", periodo_filtro)
    
    # Paginar con ORDER BY estable
    h_query = h_query.order("crn").order("periodo_id").order("dia_semana")
    
    horarios_data = []
    offset = 0
    while True:
        batch = h_query.range(offset, offset + 999).execute()
        if not batch.data:
            break
        horarios_data.extend(batch.data)
        if len(batch.data) < 1000:
            break
        offset += 1000
    
    # Indexar horarios por (crn, periodo) y día
    horarios_map = {}
    for h in horarios_data:
        clave = (h['crn'], h['periodo_id'])
        if clave not in horarios_map:
            horarios_map[clave] = {}
        horarios_map[clave][h['dia_semana']] = h
    
    # 3. Construir las filas del DataFrame
    filas = []
    for c in clases_data:
        materia = c.get("materias") or {}
        maestro = c.get("maestros") or {}
        carrera = c.get("carreras") or {}
        campus = c.get("campus") or {}
        periodo = c.get("periodos") or {}
        
        # Construir horarios por día
        horarios_clase = horarios_map.get((c['crn'], c['periodo_id']), {})
        
        def get_horario_dia(dia):
            h = horarios_clase.get(dia)
            if not h:
                return "", ""
            hora = f"{str(h['hora_inicio'])[:5]} - {str(h['hora_fin'])[:5]}"
            salon = "VIRTUAL" if h.get('es_virtual') else (h.get('salon_codigo') or "")
            return hora, salon
        
        h_lun, s_lun = get_horario_dia("LUNES")
        h_mar, s_mar = get_horario_dia("MARTES")
        h_mie, s_mie = get_horario_dia("MIERCOLES")
        h_jue, s_jue = get_horario_dia("JUEVES")
        h_vie, s_vie = get_horario_dia("VIERNES")
        h_sab, s_sab = get_horario_dia("SABADO")
        h_dom, s_dom = get_horario_dia("DOMINGO")
        
        filas.append({
            "Periodo Banner ID": c.get("periodo_id"),
            "Año ID": periodo.get("anio"),
            "Ciclo ID": periodo.get("ciclo"),
            "Clave Periodo ID": c.get("clave_periodo") or "",
            "Crn ID": c.get("crn"),
            "Grupo ID": c.get("grupo") or "",
            "Materia ID": materia.get("id") or "",
            "Materia DESC": materia.get("descripcion") or "",
            "Grado materia": materia.get("grado_materia") or "",
            "A. concentracion": materia.get("area_concentracion") or "",
            "Semanas del curso": c.get("semanas_curso") or materia.get("semanas_curso") or "",
            "Tipo uso materia": materia.get("tipos_uso_compatibles") or "",
            "Docente ID": maestro.get("clave") or "",
            "Docente DESC": maestro.get("nombre_completo") or "",
            "Carrera Hpn ID": carrera.get("clave_hpn") or "",
            "Carrera Hpn DESC": carrera.get("nombre_hpn") or "",
            "Carrera Banner ID": carrera.get("clave_banner") or "",
            "Carrera Banner DESC": carrera.get("nombre_banner") or "",
            "Departamento ID": carrera.get("departamento_id") or "",
            "Nivel ID": carrera.get("nivel_id") or "",
            "Nivel DESC": carrera.get("nivel_descripcion") or "",
            "Campus ID": campus.get("id") or "",
            "Fecha Inicio ID": c.get("fecha_inicio") or "",
            "Fecha Final ID": c.get("fecha_fin") or "",
            "Capacidad": c.get("capacidad_materia") or 0,
            "Capacidad Escenario": c.get("capacidad_escenario") or 0,
            "Inscritos": c.get("inscritos") or 0,
            "Vacantes": c.get("vacantes") or 0,
            "Tipo Curso ID": c.get("tipo_curso") or "",
            "Tipo Horario ID": c.get("tipo_horario") or "",
            "Método ID": c.get("metodo") or "",
            "Status ID": c.get("status") or "",
            "Impartición ID": c.get("impartido_id") or "",
            "Desc Impartición ID": c.get("impartido_descripcion") or "",
            "Modulo ID": c.get("modulo_id") or "",
            "desc modulo Ptms": c.get("modulo_descripcion") or "",
            "Sin Docente ID": 1 if c.get("sin_docente") else 0,
            "Sin Horario ID": 1 if c.get("sin_horario") else 0,
            "Horas Long": c.get("horas_long") or "",
            "Horario Lunes ID": h_lun,
            "Salón Lunes ID": s_lun,
            "Horario Martes ID": h_mar,
            "Salón Martes ID": s_mar,
            "Horario Miercoles ID": h_mie,
            "Salón Miercoles ID": s_mie,
            "Horario Jueves ID": h_jue,
            "Salon Jueves ID": s_jue,
            "Horario Viernes ID": h_vie,
            "Salón Viernes ID": s_vie,
            "Horario Sábado ID": h_sab,
            "Salón Sabado ID": s_sab,
            "Horario Domingo ID": h_dom,
            "Salón Domingo ID": s_dom,
        })
    
    return pd.DataFrame(filas)


def df_a_excel_bytes(df, periodo_str):
    """Convierte DataFrame a bytes de Excel con formato."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Clases"
    
    # Encabezados con estilo
    header_fill = PatternFill(start_color="1A5490", end_color="1A5490", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    for col_idx, col_name in enumerate(df.columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Datos
    for row_idx, row in enumerate(df.values, 2):
        for col_idx, valor in enumerate(row, 1):
            ws.cell(row=row_idx, column=col_idx, value=valor)
    
    # Auto-ajustar anchos (con límite)
    for col_idx in range(1, len(df.columns) + 1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = min(
            max(len(str(df.columns[col_idx-1])) + 2, 15), 35
        )
    
    # Congelar encabezado
    ws.freeze_panes = "A2"
    
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


# Botón de generación
st.subheader("📥 Generar Excel")

st.info(
    "Se generará un archivo Excel con la misma estructura del reporte original de Banner, "
    "pero con los datos actuales del sistema (incluyendo cualquier cambio manual que se haya hecho)."
)

if st.button("🔨 Generar Excel del sistema", type="primary", use_container_width=True):
    with st.spinner("Generando Excel... esto puede tardar unos segundos"):
        df = generar_excel()
        
        if df is None or df.empty:
            st.warning("⚠️ No hay datos para exportar con los filtros seleccionados.")
        else:
            # Mostrar previsualización
            st.success(f"✅ Excel generado con **{len(df)} clases**")
            
            with st.expander("👁️ Previsualizar datos (primeras 20 filas)"):
                st.dataframe(df.head(20), use_container_width=True, hide_index=True)
            
            # Generar archivo
            excel_bytes = df_a_excel_bytes(df, periodo_sel)
            
            fecha_hoy = datetime.now().strftime("%Y%m%d")
            periodo_nombre = "todos" if not periodo_filtro else str(periodo_filtro)
            nombre_archivo = f"Detalle_Mega_Figpos_Sistema_{periodo_nombre}_{fecha_hoy}.xlsx"
            
            st.download_button(
                label=f"📥 Descargar {nombre_archivo}",
                data=excel_bytes,
                file_name=nombre_archivo,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
            
            st.caption(
                f"💡 Este Excel tiene el mismo formato que el reporte de Banner. "
                f"Puedes guardarlo como respaldo o enviarlo al departamento correspondiente."
            )