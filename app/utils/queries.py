"""
Funciones reutilizables para consultar la base de datos.
Centraliza las queries para que cada página no las repita.
"""
import streamlit as st
from app.utils.supabase_client import get_supabase_client


@st.cache_resource
def get_client():
    """Cliente de Supabase compartido entre páginas."""
    return get_supabase_client()


@st.cache_data(ttl=300)
def cargar_periodos():
    """Devuelve la lista de periodos."""
    client = get_client()
    res = client.table("periodos").select("*").order("id").execute()
    return res.data


@st.cache_data(ttl=300)
def cargar_tipos_salon():
    """Devuelve los tipos únicos de salones."""
    client = get_client()
    res = client.table("salones").select("tipo_uso_descripcion").execute()
    tipos = sorted(set(s['tipo_uso_descripcion'] for s in res.data if s.get('tipo_uso_descripcion')))
    return tipos


@st.cache_data(ttl=60)
def buscar_maestros(nombre_busqueda=""):
    """Busca maestros por nombre (parcial)."""
    client = get_client()
    query = client.table("maestros").select("clave, nombre_completo, activo")
    
    if nombre_busqueda.strip():
        query = query.ilike("nombre_completo", f"%{nombre_busqueda.strip()}%")
    
    res = query.order("nombre_completo").limit(200).execute()
    return res.data


@st.cache_data(ttl=60)
def buscar_materias(nombre_busqueda=""):
    """Busca materias por descripción (parcial)."""
    client = get_client()
    query = client.table("materias").select("id, descripcion, grado_materia, semanas_curso, area_concentracion")
    
    if nombre_busqueda.strip():
        query = query.ilike("descripcion", f"%{nombre_busqueda.strip()}%")
    
    res = query.order("descripcion").limit(2000).execute()
    return res.data


@st.cache_data(ttl=60)
def buscar_materias_con_conteo(nombre_busqueda=""):
    """
    Busca materias y para cada una cuenta cuántos grupos abiertos tiene.
    """
    client = get_client()
    
    # 1. Buscar las materias
    query = client.table("materias").select(
        "id, descripcion, grado_materia, semanas_curso, area_concentracion"
    )
    
    if nombre_busqueda.strip():
        query = query.ilike("descripcion", f"%{nombre_busqueda.strip()}%")
    
    materias = query.order("descripcion").limit(2000).execute().data
    
    if not materias:
        return []
    
    # 2. Para cada materia, contar sus grupos
    ids_materias = [m['id'] for m in materias]
    grupos_res = client.table("clases").select("materia_id").in_("materia_id", ids_materias).execute()
    
    # Contar grupos por materia
    conteo = {}
    for c in grupos_res.data:
        mid = c['materia_id']
        conteo[mid] = conteo.get(mid, 0) + 1
    
    # 3. Agregar el conteo a cada materia
    for m in materias:
        m['num_grupos'] = conteo.get(m['id'], 0)
    
    return materias


@st.cache_data(ttl=60)
def buscar_salones(codigo_busqueda="", tipo_filtro="", periodo_id=None):
    """Busca salones por código o tipo. Si se pasa periodo_id, calcula el uso REAL
    de ese periodo (usando la función RPC uso_salones_por_periodo). Si no, usa la
    vista general uso_salones (que suma clases de todos los periodos, útil solo
    como panorama, no como métrica real)."""
    client = get_client()

    if periodo_id is not None:
        # Uso calculado por periodo (métrica honesta)
        datos = client.rpc("uso_salones_por_periodo",
                           {"p_periodo": int(periodo_id)}).execute().data or []
    else:
        # Panorama general (suma todos los periodos)
        datos = client.table("uso_salones").select("*").execute().data or []

    # Filtros en memoria (aplican igual sin importar la fuente)
    if codigo_busqueda.strip():
        cb = codigo_busqueda.strip().lower()
        datos = [d for d in datos if cb in str(d.get("codigo") or "").lower()]

    if tipo_filtro and tipo_filtro != "Todos":
        datos = [d for d in datos if d.get("tipo_uso_descripcion") == tipo_filtro]

    datos.sort(key=lambda d: str(d.get("codigo") or ""))
    return datos


def clases_de_maestro(maestro_clave, periodo_id=None):
    """Devuelve todas las clases de un maestro, con sus horarios."""
    client = get_client()
    query = client.table("clases").select(
        "crn, periodo_id, grupo, clave_periodo, status, "
        "inscritos, capacidad_materia, fecha_inicio, fecha_fin, "
        "materias(descripcion), "
        "horarios(dia_semana, hora_inicio, hora_fin, salon_codigo, es_virtual)"
    ).eq("maestro_clave", maestro_clave)
    
    if periodo_id:
        query = query.eq("periodo_id", periodo_id)
    
    res = query.order("periodo_id").execute()
    return res.data


def clases_en_salon(salon_codigo, periodo_id=None):
    """Devuelve todas las clases que ocupan un salón."""
    client = get_client()
    
    query = client.table("horarios").select(
        "dia_semana, hora_inicio, hora_fin, crn, periodo_id, "
        "clases(crn, periodo_id, grupo, clave_periodo, materia_id, "
        "fecha_inicio, fecha_fin, "
        "materias(descripcion), maestros(nombre_completo))"
    ).eq("salon_codigo", salon_codigo)
    
    if periodo_id:
        query = query.eq("periodo_id", periodo_id)
    
    res = query.execute()
    return res.data


def grupos_de_materia(materia_id, periodo_id=None):
    """Devuelve todos los grupos (CRNs) de una materia, con sus horarios y salones."""
    client = get_client()
    query = client.table("clases").select(
        "crn, periodo_id, grupo, clave_periodo, status, inscritos, capacidad_materia, "
        "fecha_inicio, fecha_fin, "
        "maestros(clave, nombre_completo), "
        "horarios(dia_semana, hora_inicio, hora_fin, salon_codigo, es_virtual)"
    ).eq("materia_id", materia_id)
    
    if periodo_id:
        query = query.eq("periodo_id", periodo_id)
    
    res = query.order("periodo_id").order("grupo").execute()
    return res.data

def clases_agrupadas_de_maestro(maestro_clave, periodo_id=None):
    """
    Devuelve las clases de un maestro AGRUPADAS según el patrón detectado:
    misma materia + maestro + periodo + grupo_base.
    Las clases que NO se pueden agrupar se devuelven individualmente.
    """
    client = get_client()
    
    # 1. Obtener todas las clases del maestro (originales)
    todas = clases_de_maestro(maestro_clave, periodo_id)
    
    # 2. Obtener los grupos agrupables del maestro
    query_agrup = client.table("clases_agrupadas").select("*").eq("maestro_clave", maestro_clave)
    if periodo_id:
        query_agrup = query_agrup.eq("periodo_id", periodo_id)
    agrupadas = query_agrup.execute().data
    
    # 3. Construir un mapeo de CRN+periodo → grupo_agrupado
    crns_agrupados = {}  # (crn, periodo_id) → grupo_id
    info_grupos = {}  # grupo_id → datos del agrupamiento
    
    for g in agrupadas:
        for crn in g['crns']:
            crns_agrupados[(crn, g['periodo_id'])] = g['grupo_id']
        info_grupos[g['grupo_id']] = g
    
    # 4. Procesar las clases:
    #    - Las que pertenecen a un grupo agrupado → consolidar en una sola entrada
    #    - Las que no → mantener como están
    resultados = []
    grupos_ya_procesados = set()
    
    for c in todas:
        clave = (c['crn'], c['periodo_id'])
        
        if clave in crns_agrupados:
            grupo_id = crns_agrupados[clave]
            if grupo_id in grupos_ya_procesados:
                continue  # Ya lo agregamos
            grupos_ya_procesados.add(grupo_id)
            
            # Recolectar TODAS las clases originales de este grupo
            info = info_grupos[grupo_id]
            clases_del_grupo = [
                cc for cc in todas 
                if (cc['crn'], cc['periodo_id']) in [(crn, info['periodo_id']) for crn in info['crns']]
            ]
            
            # Consolidar horarios (de todas las partes)
            todos_horarios = []
            for cc in clases_del_grupo:
                todos_horarios.extend(cc.get('horarios') or [])
            
            # Tomar la materia del primero
            materia = clases_del_grupo[0].get('materias') or {}
            
            resultados.append({
                'es_agrupada': True,
                'crns': info['crns'],
                'grupos': info['grupos'],
                'num_partes': info['num_partes'],
                'periodo_id': info['periodo_id'],
                'clave_periodo': info['clave_periodo'],
                'materias': materia,
                'horarios': todos_horarios,
                'inscritos': info['inscritos_total'],
                'capacidad_materia': info['capacidad_total'],
                'status': info['status'],
                'fecha_inicio': info['fecha_inicio'],
                'fecha_fin': info['fecha_fin']
            })
        else:
            # Clase normal, sin agrupar
            c_copia = dict(c)
            c_copia['es_agrupada'] = False
            c_copia['crns'] = [c['crn']]
            c_copia['grupos'] = [c.get('grupo') or '']
            c_copia['num_partes'] = 1
            resultados.append(c_copia)
    
    return resultados


def grupos_de_materia_agrupados(materia_id, periodo_id=None):
    """
    Devuelve los grupos de una materia, agrupando los que parezcan ser la misma clase.
    """
    client = get_client()
    
    # 1. Obtener todos los grupos (originales)
    todos = grupos_de_materia(materia_id, periodo_id)
    
    # 2. Obtener los grupos agrupables de esta materia
    query_agrup = client.table("clases_agrupadas").select("*").eq("materia_id", materia_id)
    if periodo_id:
        query_agrup = query_agrup.eq("periodo_id", periodo_id)
    agrupadas = query_agrup.execute().data
    
    # 3. Mapeo CRN+periodo → grupo_id
    crns_agrupados = {}
    info_grupos = {}
    
    for g in agrupadas:
        for crn in g['crns']:
            crns_agrupados[(crn, g['periodo_id'])] = g['grupo_id']
        info_grupos[g['grupo_id']] = g
    
    # 4. Procesar
    resultados = []
    grupos_ya_procesados = set()
    
    for c in todos:
        clave = (c['crn'], c['periodo_id'])
        
        if clave in crns_agrupados:
            grupo_id = crns_agrupados[clave]
            if grupo_id in grupos_ya_procesados:
                continue
            grupos_ya_procesados.add(grupo_id)
            
            info = info_grupos[grupo_id]
            clases_del_grupo = [
                cc for cc in todos 
                if (cc['crn'], cc['periodo_id']) in [(crn, info['periodo_id']) for crn in info['crns']]
            ]
            
            todos_horarios = []
            for cc in clases_del_grupo:
                todos_horarios.extend(cc.get('horarios') or [])
            
            maestro = clases_del_grupo[0].get('maestros') or {}
            
            resultados.append({
                'es_agrupada': True,
                'crns': info['crns'],
                'grupos': info['grupos'],
                'num_partes': info['num_partes'],
                'crn': info['crn_principal'],  # para compatibilidad
                'periodo_id': info['periodo_id'],
                'clave_periodo': info['clave_periodo'],
                'grupo': ', '.join(info['grupos']),
                'maestros': maestro,
                'horarios': todos_horarios,
                'inscritos': info['inscritos_total'],
                'capacidad_materia': info['capacidad_total'],
                'status': info['status'],
                'fecha_inicio': info['fecha_inicio'],
                'fecha_fin': info['fecha_fin']
            })
        else:
            c_copia = dict(c)
            c_copia['es_agrupada'] = False
            c_copia['crns'] = [c['crn']]
            c_copia['grupos'] = [c.get('grupo') or '']
            c_copia['num_partes'] = 1
            resultados.append(c_copia)
    
    return resultados

@st.cache_data(ttl=300)
def cargar_niveles():
    """Devuelve los niveles académicos disponibles."""
    client = get_client()
    res = client.table("niveles_academicos").select("*").order("codigo").execute()
    return res.data


@st.cache_data(ttl=300)
def cargar_programas(nivel_codigo=None):
    """Devuelve los programas, opcionalmente filtrados por nivel."""
    client = get_client()
    query = client.table("programas").select("clave, nombre, nivel_codigo").eq("activo", True)
    
    if nivel_codigo:
        query = query.eq("nivel_codigo", nivel_codigo)
    
    res = query.order("nombre").execute()
    return res.data


@st.cache_data(ttl=300)
def carreras_huerfanas():
    """Devuelve las carreras que NO tienen programa asignado (no están en el Excel oficial)."""
    client = get_client()
    res = client.table("carreras").select("*").is_("programa_clave", "null").execute()
    return res.data