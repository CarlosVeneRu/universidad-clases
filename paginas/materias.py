"""
Página de materias: catálogo navegable por nivel/programa o búsqueda.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.ui import encabezado
import streamlit as st
import pandas as pd
from app.utils.queries import (
    buscar_materias_con_conteo, grupos_de_materia, grupos_de_materia_agrupados,
    cargar_periodos, cargar_niveles, cargar_programas, get_client
)


DIAS_CORTO = {
    'LUNES': 'LUN', 'MARTES': 'MAR', 'MIERCOLES': 'MIÉ',
    'JUEVES': 'JUE', 'VIERNES': 'VIE', 'SABADO': 'SÁB', 'DOMINGO': 'DOM'
}
DIAS_ORDEN = ['LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO', 'DOMINGO']


@st.cache_data(ttl=120)
def materias_de_programa(programa_clave):
    """Devuelve las materias que tienen clases en un programa específico."""
    client = get_client()
    
    # 1. Obtener las carreras vinculadas a este programa
    carreras_res = client.table("carreras").select("id").eq("programa_clave", programa_clave).execute()
    if not carreras_res.data:
        return []
    
    ids_carreras = [c['id'] for c in carreras_res.data]
    
    # 2. Obtener las materia_ids únicas de las clases de esas carreras
    clases_res = client.table("clases").select("materia_id").in_("carrera_id", ids_carreras).execute()
    materia_ids = list(set(c['materia_id'] for c in clases_res.data if c.get('materia_id')))
    
    if not materia_ids:
        return []
    
    # 3. Obtener los datos completos de esas materias
    materias_res = client.table("materias").select(
        "id, descripcion, grado_materia, semanas_curso, area_concentracion"
    ).in_("id", materia_ids).order("descripcion").execute()
    
    # 4. Contar grupos por cada materia (solo de las carreras del programa)
    conteo = {}
    for c in clases_res.data:
        mid = c.get('materia_id')
        if mid:
            conteo[mid] = conteo.get(mid, 0) + 1
    
    for m in materias_res.data:
        m['num_grupos'] = conteo.get(m['id'], 0)
    
    return materias_res.data


@st.cache_data(ttl=120)
def materias_de_nivel(nivel_codigo):
    """Devuelve las materias que tienen clases en cualquier programa de un nivel."""
    client = get_client()
    
    # 1. Programas de ese nivel
    programas_res = client.table("programas").select("clave").eq("nivel_codigo", nivel_codigo).execute()
    if not programas_res.data:
        return []
    
    claves_programas = [p['clave'] for p in programas_res.data]
    
    # 2. Carreras vinculadas a esos programas
    carreras_res = client.table("carreras").select("id").in_("programa_clave", claves_programas).execute()
    if not carreras_res.data:
        return []
    
    ids_carreras = [c['id'] for c in carreras_res.data]
    
    # 3. Materia_ids de las clases de esas carreras
    clases_res = client.table("clases").select("materia_id").in_("carrera_id", ids_carreras).execute()
    materia_ids = list(set(c['materia_id'] for c in clases_res.data if c.get('materia_id')))
    
    if not materia_ids:
        return []
    
    # 4. Datos de las materias
    materias_res = client.table("materias").select(
        "id, descripcion, grado_materia, semanas_curso, area_concentracion"
    ).in_("id", materia_ids).order("descripcion").execute()
    
    # 5. Contar grupos
    conteo = {}
    for c in clases_res.data:
        mid = c.get('materia_id')
        if mid:
            conteo[mid] = conteo.get(mid, 0) + 1
    
    for m in materias_res.data:
        m['num_grupos'] = conteo.get(m['id'], 0)
    
    return materias_res.data

@st.cache_data(ttl=120)
def materias_multicarrera():
    """Materias cuyas clases no están ligadas a una sola carrera (multicarrera)."""
    client = get_client()
    return client.rpc("materias_multicarrera", {}).execute().data or []

def main():
    encabezado("Materias", "Catálogo de materias por nivel y programa", "📚")
    
    # ===== MODO DE BÚSQUEDA =====
    modo = st.radio(
        "¿Cómo quieres buscar las materias?",
        ["🎓 Por nivel/programa", "🔍 Por nombre o ID", "📋 Ver todas"],
        horizontal=True,
        key="modo_busqueda_materias"
    )
    
    st.divider()
    
    materias = []
    
    # ===== MODO 1: POR NIVEL/PROGRAMA =====
    if modo == "🎓 Por nivel/programa":
        col_n1, col_n2 = st.columns(2)
        
        with col_n1:
            niveles = cargar_niveles()
            opciones_nivel = ["Todos los niveles"] + [f"{n['codigo']} - {n['descripcion_corta']}" for n in niveles]
            nivel_sel = st.selectbox("🎓 Nivel académico", opciones_nivel, key="nivel_materias")
            nivel_filtro = None
            if not nivel_sel.startswith("Todos"):
                nivel_filtro = nivel_sel.split(" - ")[0]
        
        with col_n2:
            # Cargar programas según si hay nivel filtrado o no
            if nivel_filtro:
                programas = cargar_programas(nivel_filtro)
            else:
                programas = cargar_programas()  # Todos los programas
            
            opciones_programa = ["Todos los programas", "🔀 Multicarrera (materias de varias carreras)"] + \
                [f"{p['clave']} - {p['nombre']}" for p in programas]
            programa_sel = st.selectbox("📘 Programa", opciones_programa, key="programa_materias")
            programa_filtro = None
            es_multicarrera = programa_sel.startswith("🔀 Multicarrera")
            if not programa_sel.startswith("Todos") and not es_multicarrera:
                programa_filtro = programa_sel.split(" - ")[0]
        
        # Validar que al menos uno esté seleccionado
        if not nivel_filtro and not programa_filtro and not es_multicarrera:
            st.info("👆 Selecciona al menos un nivel, un programa, o Multicarrera para empezar")
            return
        
        # Cargar materias según el filtro
        with st.spinner("Cargando materias..."):
            if es_multicarrera:
                materias = materias_multicarrera()
            elif programa_filtro:
                # Si hay programa específico, filtramos por ese (incluso si también hay nivel)
                materias = materias_de_programa(programa_filtro)
            elif nivel_filtro:
                # Solo nivel, sin programa específico
                materias = materias_de_nivel(nivel_filtro)
        
        if not materias:
            st.warning("⚠️ No hay materias con clases activas para este filtro")
            return
        
        # Mostrar contexto del filtro
        if es_multicarrera:
            st.success(f"✅ {len(materias)} materias multicarrera (compartidas entre varias carreras)")
        elif programa_filtro:
            programa_info = next((p for p in programas if p['clave'] == programa_filtro), None)
            if programa_info:
                contexto = f"**{programa_info['nombre']}**"
                if nivel_filtro:
                    nivel_info = next((n for n in niveles if n['codigo'] == nivel_filtro), None)
                    if nivel_info:
                        contexto += f" (nivel {nivel_info['descripcion_corta']})"
                st.success(f"✅ {len(materias)} materias en {contexto}")
        else:
            nivel_info = next((n for n in niveles if n['codigo'] == nivel_filtro), None)
            if nivel_info:
                st.success(f"✅ {len(materias)} materias en nivel **{nivel_info['descripcion_corta']}**")
    
    # ===== MODO 2: POR NOMBRE =====
    elif modo == "🔍 Por nombre o ID":
        nombre_busqueda = st.text_input(
            "Buscar materia",
            placeholder="Escribe parte del nombre o ID (ej: BIOLOGY, MATE, PBIO0402B)..."
        )
        
        if not nombre_busqueda.strip() or len(nombre_busqueda.strip()) < 2:
            st.info("👆 Escribe al menos 2 caracteres para buscar materias")
            return
        
        materias = buscar_materias_con_conteo(nombre_busqueda)
        
        if not materias:
            st.warning("⚠️ No se encontraron materias con ese criterio")
            return
        
        st.success(f"✅ {len(materias)} materias encontradas")
    
    # ===== MODO 3: VER TODAS =====
    else:  # modo == "📋 Ver todas"
        with st.spinner("Cargando catálogo completo..."):
            materias = buscar_materias_con_conteo("")
        
        if not materias:
            st.warning("⚠️ No hay materias en el catálogo")
            return
        
        st.success(f"✅ {len(materias)} materias en el catálogo completo")
    
    # ===== SELECCIONAR MATERIA =====
    def formatear_opcion(m):
        partes = [m['id'], m['descripcion']]
        if m.get('semanas_curso'):
            partes.append(f"{m['semanas_curso']} sem")
        num = m.get('num_grupos', 0)
        if num == 0:
            partes.append("Sin grupos")
        elif num == 1:
            partes.append("1 grupo")
        else:
            partes.append(f"{num} grupos")
        return " · ".join(partes)
    
    opciones = [formatear_opcion(m) for m in materias]
    seleccion = st.selectbox("Selecciona una materia para ver sus grupos", opciones)
    
    materia_id = seleccion.split(" · ")[0]
    materia_obj = next(m for m in materias if m['id'] == materia_id)
    
    st.divider()
    
    # ===== DETALLE DE LA MATERIA =====
    st.header(f"📚 {materia_obj['descripcion']}")
    st.caption(f"ID: {materia_id}")
    
    # Calcular horas semanales de la materia (por grupo)
    # Usamos los grupos AGRUPADOS para que las clases divididas
    # sumen las horas de sus partes en vez de promediarlas.
    horas_semana_materia = None
    grupos_todos = grupos_de_materia_agrupados(materia_id)
    if grupos_todos:
        horas_por_grupo = []
        for g in grupos_todos:
            horarios_g = g.get('horarios') or []
            horas_g = 0
            for h in horarios_g:
                try:
                    ini_p = str(h['hora_inicio']).split(':')
                    fin_p = str(h['hora_fin']).split(':')
                    minutos = (int(fin_p[0]) * 60 + int(fin_p[1])) - (int(ini_p[0]) * 60 + int(ini_p[1]))
                    horas_g += minutos / 60
                except Exception:
                    pass
            if horas_g > 0:
                horas_por_grupo.append(horas_g)
        
        if horas_por_grupo:
            # Usar el promedio (casi siempre todos los grupos tienen las mismas horas)
            horas_semana_materia = sum(horas_por_grupo) / len(horas_por_grupo)
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("🎓 Grado", materia_obj.get('grado_materia') or 'N/A')
    with col_m2:
        st.metric("📅 Semanas del curso", materia_obj.get('semanas_curso') or 'N/A')
    with col_m3:
        if horas_semana_materia:
            st.metric("⏰ Horas/semana", f"{horas_semana_materia:.1f} hrs")
        else:
            st.metric("⏰ Horas/semana", "N/A")
    with col_m4:
        st.metric("🔬 Área", materia_obj.get('area_concentracion') or 'N/A')
    
    # Filtro de periodo y toggle
    periodos = cargar_periodos()
    
    col_per, col_tog = st.columns([2, 2])
    with col_per:
        opciones_periodo = ["Todos"] + [f"{p['id']}" for p in periodos]
        periodo_sel = st.selectbox("Filtrar por periodo", opciones_periodo, key="periodo_materia")
        periodo_id = int(periodo_sel) if periodo_sel != "Todos" else None
    
    with col_tog:
        st.write("")
        ver_agrupado = st.toggle(
            "🔗 Ver clases agrupadas",
            value=True,
            help="Junta automáticamente los grupos divididos (ej: 17A + 17B = una sola clase)",
            key="toggle_agrupado_materias"
        )
    
    # Obtener grupos (agrupados o no)
    if ver_agrupado:
        grupos = grupos_de_materia_agrupados(materia_id, periodo_id)
    else:
        grupos = grupos_de_materia(materia_id, periodo_id)
        for g in grupos:
            g['es_agrupada'] = False
            g['crns'] = [g['crn']]
            g['grupos'] = [g.get('grupo') or '']
            g['num_partes'] = 1
    
    if not grupos:
        st.info("Esta materia no tiene grupos en el filtro seleccionado")
        return
    
    st.divider()
    
    # ===== MÉTRICAS DE GRUPOS =====
    total_grupos = len(grupos)
    total_inscritos = sum(g.get('inscritos', 0) for g in grupos)
    total_capacidad = sum(g.get('capacidad_materia', 0) for g in grupos)
    porcentaje_lleno = (total_inscritos / total_capacidad * 100) if total_capacidad > 0 else 0
    
    col_g1, col_g2, col_g3, col_g4 = st.columns(4)
    with col_g1:
        st.metric("📋 Total grupos", total_grupos)
    with col_g2:
        st.metric("👥 Inscritos", total_inscritos)
    with col_g3:
        st.metric("🪑 Capacidad", total_capacidad)
    with col_g4:
        st.metric("📊 Lleno", f"{porcentaje_lleno:.1f}%")
    
    st.subheader("📋 Grupos disponibles")
    
    filas = []
    for g in grupos:
        maestro = g.get("maestros") or {}
        horarios_grupo = g.get("horarios") or []
        
        horarios_ordenados = sorted(
            horarios_grupo,
            key=lambda h: (DIAS_ORDEN.index(h['dia_semana']) if h['dia_semana'] in DIAS_ORDEN else 99, h['hora_inicio'])
        )
        
        salones_usados = set()
        tiene_virtual = False
        
        for h in horarios_ordenados:
            if h.get('es_virtual'):
                tiene_virtual = True
            else:
                salon = h.get('salon_codigo')
                if salon:
                    salones_usados.add(salon)
        
        if not salones_usados and tiene_virtual:
            salones_str = "🌐 Virtual"
        elif not salones_usados:
            salones_str = "Sin salón"
        elif len(salones_usados) == 1:
            salones_str = list(salones_usados)[0]
            if tiene_virtual:
                salones_str += " + 🌐 Virtual"
        else:
            salones_str = " · ".join(sorted(salones_usados))
            if tiene_virtual:
                salones_str += " + 🌐"
        
        # ===== Construir horario limpio =====
        # Agrupar días que tienen el MISMO rango de horas
        rangos_por_hora = {}  # "07:00-08:59" -> ["LUN", "MIE", "VIE"]
        
        for h in horarios_ordenados:
            hora_ini = str(h['hora_inicio'])[:5]
            hora_fin = str(h['hora_fin'])[:5]
            rango = f"{hora_ini}-{hora_fin}"
            dia_corto = DIAS_CORTO.get(h['dia_semana'], h['dia_semana'][:3])
            
            if rango not in rangos_por_hora:
                rangos_por_hora[rango] = []
            rangos_por_hora[rango].append(dia_corto)
        
        # Construir el texto final
        if not rangos_por_hora:
            horario_str = "Sin horario"
        else:
            partes_horario = []
            # Ordenar por hora de inicio
            for rango in sorted(rangos_por_hora.keys()):
                dias = rangos_por_hora[rango]
                # Ordenar los días en orden correcto
                orden_dias = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM']
                dias_ordenados = sorted(dias, key=lambda d: orden_dias.index(d) if d in orden_dias else 99)
                dias_str = "·".join(dias_ordenados)
                partes_horario.append(f"{dias_str} {rango}")
            
            horario_str = " | ".join(partes_horario)
        
        if g.get('es_agrupada'):
            crns_str = f"🔗 {', '.join(str(x) for x in g['crns'])}"
            grupos_str = ', '.join(g['grupos'])
        else:
            crns_str = str(g['crns'][0]) if g.get('crns') else str(g.get('crn', ''))
            grupos_str = g['grupos'][0] if g.get('grupos') else g.get('grupo', '')
        
        filas.append({
            "CRN(s)": crns_str,
            "Periodo": g["periodo_id"],
            "Clave": g.get("clave_periodo") or "",
            "Grupo(s)": grupos_str,
            "Maestro": maestro.get("nombre_completo") or "Sin asignar",
            "Horario": horario_str,
            "Salones": salones_str,
            "Status": g.get("status") or "",
            "Inscritos": f"{g.get('inscritos', 0)}/{g.get('capacidad_materia', 0)}",
            "F. Inicio": g.get("fecha_inicio") or "",
            "F. Fin": g.get("fecha_fin") or ""
        })
    
    df = pd.DataFrame(filas)
    
    altura_calc = 38 + (len(df) * 38) + 3
    altura_calc = min(altura_calc, 600)
    
    st.dataframe(df, use_container_width=True, hide_index=True, height=altura_calc)
    
    if ver_agrupado:
        agrupadas = sum(1 for g in grupos if g.get('es_agrupada'))
        if agrupadas > 0:
            st.caption(f"🔗 {agrupadas} de las {len(grupos)} filas son clases agrupadas")


main()