"""
Página de búsqueda avanzada de clases.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.utils.queries import (
    get_client, cargar_periodos, buscar_maestros, buscar_materias,
    cargar_niveles, cargar_programas
)

def agrupar_resultados(resultados):
    """
    Toma los resultados de la búsqueda y agrupa las clases que probablemente son 'la misma'.
    Criterio: misma materia + maestro + periodo + grupo_base (quitando última letra).
    """
    import re
    
    # 1. Agrupar por (materia_id, maestro_clave, periodo_id, grupo_base)
    grupos = {}
    individuales = []
    
    for c in resultados:
        materia = c.get("materias") or {}
        maestro_obj = c.get("maestros") or {}
        materia_id = materia.get("id")
        maestro_clave = maestro_obj.get("clave")
        periodo_id = c.get("periodo_id")
        grupo = c.get("grupo") or ""
        
        # Solo agrupar si tiene materia, maestro, periodo y grupo terminando en letra
        if not (materia_id and maestro_clave and periodo_id and re.search(r'[A-Z]$', grupo)):
            individuales.append(c)
            continue
        
        # Quitar la última letra del grupo (17A -> 17)
        grupo_base = re.sub(r'[A-Z]$', '', grupo)
        clave = (materia_id, maestro_clave, periodo_id, grupo_base)
        
        if clave not in grupos:
            grupos[clave] = []
        grupos[clave].append(c)
    
    # 2. Construir los resultados agrupados
    resultados_final = []
    
    for clave, clases_del_grupo in grupos.items():
        if len(clases_del_grupo) == 1:
            # Solo una clase, no es agrupable
            c = clases_del_grupo[0]
            c['es_agrupada'] = False
            c['crns'] = [c['crn']]
            c['grupos_lista'] = [c.get('grupo') or '']
            resultados_final.append(c)
        else:
            # Múltiples clases que se agrupan
            primera = clases_del_grupo[0]
            crns = sorted([c['crn'] for c in clases_del_grupo])
            grupos_lista = sorted([c.get('grupo') or '' for c in clases_del_grupo])
            
            inscritos_total = sum(c.get('inscritos', 0) for c in clases_del_grupo)
            capacidad_total = sum(c.get('capacidad_materia', 0) for c in clases_del_grupo)
            
            agrupada = dict(primera)
            agrupada['es_agrupada'] = True
            agrupada['crns'] = crns
            agrupada['grupos_lista'] = grupos_lista
            agrupada['inscritos'] = inscritos_total
            agrupada['capacidad_materia'] = capacidad_total
            agrupada['num_partes'] = len(clases_del_grupo)
            resultados_final.append(agrupada)
    
    # 3. Agregar las clases individuales (las que no se pudieron agrupar)
    for c in individuales:
        c['es_agrupada'] = False
        c['crns'] = [c['crn']]
        c['grupos_lista'] = [c.get('grupo') or '']
        resultados_final.append(c)
    
    return resultados_final

def buscar_clases_avanzado(filtros):
    """Busca clases con todos los filtros aplicados."""
    client = get_client()
    
    query = client.table("clases").select(
        "crn, periodo_id, grupo, clave_periodo, status, "
        "fecha_inicio, fecha_fin, inscritos, capacidad_materia, vacantes, "
        "tipo_curso, sin_docente, sin_horario, "
        "materias(id, descripcion), "
        "maestros(clave, nombre_completo), "
        "carreras(nombre_banner, programa_clave, programas(nombre, nivel_codigo))"
    )
    
    if filtros.get("periodo_id"):
        query = query.eq("periodo_id", filtros["periodo_id"])
    
    if filtros.get("clave_periodo"):
        query = query.eq("clave_periodo", filtros["clave_periodo"])
    
    if filtros.get("status"):
        query = query.eq("status", filtros["status"])
    
    if filtros.get("crn"):
        query = query.eq("crn", filtros["crn"])
    
    if filtros.get("maestro_clave"):
        query = query.eq("maestro_clave", filtros["maestro_clave"])
    
    if filtros.get("materia_id"):
        query = query.eq("materia_id", filtros["materia_id"])
    
    if filtros.get("solo_sin_docente"):
        query = query.eq("sin_docente", True)
    
    if filtros.get("solo_sin_horario"):
        query = query.eq("sin_horario", True)
    
    if filtros.get("carrera_id"):
        query = query.eq("carrera_id", filtros["carrera_id"])
    
    query = query.limit(1000)
    
    return query.execute().data


def main():
    st.title("🔍 Buscar Clases")
    st.markdown("Búsqueda avanzada con múltiples filtros")
    st.divider()
    
    # Cargar opciones
    periodos = cargar_periodos()
    
    # ===== FILTROS PRINCIPALES =====
    st.subheader("🎯 Filtros principales")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Periodo
        opciones_periodo = ["Todos"] + [f"{p['id']}" for p in periodos]
        periodo_sel = st.selectbox("📅 Periodo", opciones_periodo)
        periodo_id = int(periodo_sel) if periodo_sel != "Todos" else None
        
        # Mostrar las claves de ese periodo
        clave_periodo = None
        if periodo_id:
            periodo_obj = next((p for p in periodos if p['id'] == periodo_id), None)
            if periodo_obj and periodo_obj.get('descripcion'):
                claves_disponibles = ["Todas"] + periodo_obj['descripcion'].split(',')
                clave_sel = st.selectbox("🏷️ Clave del periodo", claves_disponibles)
                if clave_sel != "Todas":
                    clave_periodo = clave_sel.strip()
    
    with col2:
        # Status
        status_sel = st.selectbox("📊 Status", ["Todos", "A (Activa)", "R (Reservada)"])
        status = None
        if status_sel.startswith("A"):
            status = "A"
        elif status_sel.startswith("R"):
            status = "R"
        
        # CRN específico
        crn_input = st.text_input("🔢 CRN específico", placeholder="Ej: 6971")
        crn_filter = int(crn_input.strip()) if crn_input.strip().isdigit() else None
    
    with col3:
        # Búsqueda por maestro
        maestro_busqueda = st.text_input("👨‍🏫 Buscar maestro", placeholder="Nombre del maestro")
        maestro_clave = None
        if maestro_busqueda.strip() and len(maestro_busqueda.strip()) >= 3:
            maestros_encontrados = buscar_maestros(maestro_busqueda)
            if maestros_encontrados:
                opciones_maestro = ["Cualquiera"] + [f"{m['clave']} - {m['nombre_completo']}" for m in maestros_encontrados]
                maestro_sel = st.selectbox(f"Seleccionar ({len(maestros_encontrados)} encontrados)", opciones_maestro)
                if maestro_sel != "Cualquiera":
                    maestro_clave = int(maestro_sel.split(" - ")[0])
        
        # Búsqueda por materia
        materia_busqueda = st.text_input("📚 Buscar materia", placeholder="Nombre o ID de materia")
        materia_id = None
        if materia_busqueda.strip() and len(materia_busqueda.strip()) >= 3:
            materias_encontradas = buscar_materias(materia_busqueda)
            if materias_encontradas:
                opciones_materia = ["Cualquiera"] + [f"{m['id']} - {m['descripcion']}" for m in materias_encontradas]
                materia_sel = st.selectbox(f"Seleccionar ({len(materias_encontradas)} encontradas)", opciones_materia)
                if materia_sel != "Cualquiera":
                    materia_id = materia_sel.split(" - ")[0]
    
    # Filtros avanzados (expandible)
    with st.expander("🔧 Filtros avanzados"):
        col_a, col_b = st.columns(2)
        with col_a:
            solo_sin_docente = st.checkbox("Solo clases sin docente asignado")
        with col_b:
            solo_sin_horario = st.checkbox("Solo clases sin horario asignado")
    
    # Toggle para agrupar clases
    col_tog1, col_tog2 = st.columns([1, 3])
    with col_tog1:
        ver_agrupado = st.toggle(
            "🔗 Ver clases agrupadas",
            value=False,
            help="Junta automáticamente los grupos divididos (ej: 17A + 17B = una sola clase)"
        )
    with st.expander("🎓 Filtrar por nivel/programa académico"):
        col_n1, col_n2 = st.columns(2)
        
        with col_n1:
            niveles = cargar_niveles()
            opciones_nivel = ["Todos"] + [f"{n['codigo']} - {n['descripcion_corta']}" for n in niveles]
            nivel_sel = st.selectbox("Nivel académico", opciones_nivel)
            nivel_filtro = None
            if nivel_sel != "Todos":
                nivel_filtro = nivel_sel.split(" - ")[0]
        
        with col_n2:
            # Programas filtrados por nivel
            if nivel_filtro:
                programas = cargar_programas(nivel_filtro)
            else:
                programas = cargar_programas()
            
            opciones_programa = ["Todos"] + [f"{p['clave']} - {p['nombre']}" for p in programas]
            programa_sel = st.selectbox("Programa", opciones_programa)
            programa_filtro = None
            if programa_sel != "Todos":
                programa_filtro = programa_sel.split(" - ")[0]
        
        # Si hay programa seleccionado, buscar las carreras vinculadas
        carrera_id_filtro = None
        if programa_filtro:
            client = get_client()
            carreras_res = client.table("carreras").select("id").eq("programa_clave", programa_filtro).execute()
            if carreras_res.data:
                ids = [c['id'] for c in carreras_res.data]
                if len(ids) == 1:
                    carrera_id_filtro = ids[0]
                else:
                    st.caption(f"ℹ️ El programa tiene {len(ids)} versiones en Banner; filtra por la primera.")
                    carrera_id_filtro = ids[0]
    
    st.divider()
    
    # Botón de búsqueda
    col_btn1, col_btn2 = st.columns([1, 5])
    with col_btn1:
        buscar = st.button("🔍 Buscar", type="primary", use_container_width=True)
    with col_btn2:
        if st.button("🔄 Limpiar filtros", use_container_width=False):
            st.rerun()
    
    # ===== EJECUTAR BÚSQUEDA =====
    if buscar:
        with st.spinner("Buscando..."):
            filtros = {
                "periodo_id": periodo_id,
                "clave_periodo": clave_periodo,
                "status": status,
                "crn": crn_filter,
                "maestro_clave": maestro_clave,
                "materia_id": materia_id,
                "solo_sin_docente": solo_sin_docente,
                "solo_sin_horario": solo_sin_horario,
                "carrera_id": carrera_id_filtro
            }
            
            resultados = buscar_clases_avanzado(filtros)
            
            if resultados:
                # Aplicar agrupamiento si está activado
                if ver_agrupado:
                    resultados_mostrar = agrupar_resultados(resultados)
                else:
                    resultados_mostrar = resultados
                    for r in resultados_mostrar:
                        r['es_agrupada'] = False
                        r['crns'] = [r['crn']]
                        r['grupos_lista'] = [r.get('grupo') or '']
                
                # Métricas rápidas
                total = len(resultados_mostrar)
                total_originales = len(resultados)
                con_inscritos = sum(1 for r in resultados_mostrar if r.get('inscritos', 0) > 0)
                total_inscritos = sum(r.get('inscritos', 0) for r in resultados_mostrar)
                
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1:
                    if ver_agrupado:
                        st.metric("🔗 Clases (agrupadas)", total, delta=f"{total - total_originales}")
                    else:
                        st.metric("📝 Clases encontradas", total)
                with col_m2:
                    st.metric("✅ Con inscritos", con_inscritos)
                with col_m3:
                    st.metric("👥 Total estudiantes", total_inscritos)
                with col_m4:
                    if ver_agrupado:
                        agrupadas_count = sum(1 for r in resultados_mostrar if r.get('es_agrupada'))
                        st.metric("🔗 Filas agrupadas", agrupadas_count)
                
                st.divider()
                
                # Tabla de resultados
                filas = []
                for c in resultados_mostrar:
                    materia = c.get("materias") or {}
                    maestro = c.get("maestros") or {}
                    carrera = c.get("carreras") or {}
                    programa_info = (carrera.get("programas") or {}) if carrera else {}
                    
                    if c.get('es_agrupada'):
                        crns_str = f"🔗 {', '.join(str(x) for x in c['crns'])}"
                        grupos_str = ', '.join(c['grupos_lista'])
                    else:
                        crns_str = str(c['crns'][0]) if c.get('crns') else str(c.get('crn', ''))
                        grupos_str = c['grupos_lista'][0] if c.get('grupos_lista') else c.get('grupo', '')
                    
                    filas.append({
                        "CRN(s)": crns_str,
                        "Periodo": c["periodo_id"],
                        "Clave": c.get("clave_periodo") or "",
                        "Grupo(s)": grupos_str,
                        "Materia": materia.get("descripcion") or "(multi)",
                        "Maestro": maestro.get("nombre_completo") or "Sin asignar",
                        "Programa": programa_info.get("nombre") or "(multi-carrera)",
                        "Nivel": programa_info.get("nivel_codigo") or "—",
                        "Status": c.get("status") or "",
                        "Inscritos/Cap": f"{c.get('inscritos', 0)}/{c.get('capacidad_materia', 0)}",
                        "F. Inicio": c.get("fecha_inicio") or "",
                        "F. Fin": c.get("fecha_fin") or ""
                    })
                
                df = pd.DataFrame(filas)
                st.dataframe(df, use_container_width=True, hide_index=True, height=500)
                
                st.caption(f"Mostrando hasta 1000 resultados. Refina los filtros para resultados más específicos.")
            else:
                st.warning("⚠️ No se encontraron clases con esos filtros")
    else:
        st.info("👆 Selecciona filtros y haz clic en **Buscar** para ver las clases")


main()