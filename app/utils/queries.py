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


# Códigos de nivel que reconocemos en las claves de periodo
NIVELES_LEGIBLES = {
    "LX": "Licenciatura Ejecutiva", "NC": "Ciencias de la Salud",
    "PT": "Posgrado / Maestría", "L6": "Licenciatura", "LS": "Licenciatura",
    "B6": "Bachillerato", "6B": "Bachillerato",
}


def _codigos_de_desc(desc):
    """De 'BL6,EL6,LS' devuelve una lista ordenada de códigos de nivel encontrados."""
    codigos = []
    hay_otros = False
    for parte in str(desc or "").split(","):
        parte = parte.strip().upper()
        if not parte:
            continue
        encontrado = None
        for cod in ["LX", "NC", "PT", "L6", "LS", "B6", "6B"]:
            if cod in parte:
                encontrado = cod
                break
        if encontrado and encontrado not in codigos:
            codigos.append(encontrado)
        elif not encontrado:
            hay_otros = True
    if hay_otros and "Otros" not in codigos:
        codigos.append("Otros")
    return codigos


def etiqueta_periodo_bonita(pid, desc, estado=None):
    """Devuelve texto tipo '202680 · Licenciatura (LS, L6)' o
    '202610 · Bachillerato Concluido (B6)' según el estado."""
    codigos = _codigos_de_desc(desc)
    if not codigos:
        base = str(pid)
    else:
        principal = None
        for cod in codigos:
            if cod in NIVELES_LEGIBLES:
                principal = NIVELES_LEGIBLES[cod]
                break
        if estado == "concluido":
            if principal:
                nombre = f"{principal} Concluido"
            else:
                nombre = "Concluido"
        else:
            nombre = principal or "Otros"
        base = f"{pid} · {nombre} ({', '.join(codigos)})"
    return base


@st.cache_data(ttl=300)
def cargar_periodos(solo_activos=False):
    """Devuelve la lista de periodos con su estado (activo, concluido, vacio).
    Si solo_activos=True, filtra los concluidos y vacíos."""
    client = get_client()
    res = client.table("periodos_con_estado").select("*").order("id").execute()
    datos = res.data or []
    if solo_activos:
        datos = [p for p in datos if p.get("estado") == "activo"]
    return datos


@st.cache_data(ttl=300)
def cargar_tipos_salon():
    """Devuelve los tipos únicos de salones."""
    client = get_client()
    res = client.table("salones").select("tipo_uso_descripcion").execute()
    tipos = sorted(set(s['tipo_uso_descripcion'] for s in res.data if s.get('tipo_uso_descripcion')))
    return tipos


@st.cache_data(ttl=60)
def maestros_con_clases_activas():
    """Devuelve el set de claves de maestros que TIENEN al menos una clase
    activa hoy o en el futuro (fecha_fin >= hoy). Se usa para pintar 🟢/🔴 en el selector."""
    from datetime import date
    client = get_client()
    hoy = date.today().isoformat()
    claves = set()
    tamano = 1000
    inicio = 0
    while True:
        res = (client.table("clases")
               .select("maestro_clave")
               .gte("fecha_fin", hoy)
               .not_.is_("maestro_clave", "null")
               .order("maestro_clave")
               .range(inicio, inicio + tamano - 1)
               .execute()).data or []
        if not res:
            break
        for r in res:
            if r.get("maestro_clave") is not None:
                claves.add(r["maestro_clave"])
        if len(res) < tamano:
            break
        inicio += tamano
    return claves


@st.cache_data(ttl=60)
def buscar_maestros(nombre_busqueda=""):
    """Busca maestros por nombre (parcial) o por docente ID (clave).
    Si el texto son solo dígitos, busca por clave (contiene). Si no, busca por nombre."""
    client = get_client()
    query = client.table("maestros").select("clave, nombre_completo, activo")

    b = nombre_busqueda.strip() if nombre_busqueda else ""
    if b:
        if b.isdigit():
            # Búsqueda por docente ID: traer todos y filtrar en memoria (contiene)
            res = query.order("nombre_completo").execute()
            return [m for m in (res.data or []) if b in str(m['clave'])][:1000]
        else:
            query = query.ilike("nombre_completo", f"%{b}%")

    res = query.order("nombre_completo").limit(1000).execute()
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
    
    query = client.table("materias").select(
        "id, descripcion, grado_materia, semanas_curso, area_concentracion"
    )
    
    if nombre_busqueda.strip():
        query = query.ilike("descripcion", f"%{nombre_busqueda.strip()}%")
    
    materias = query.order("descripcion").limit(2000).execute().data
    
    if not materias:
        return []
    
    ids_materias = [m['id'] for m in materias]
    grupos_res = client.table("clases").select("materia_id").in_("materia_id", ids_materias).execute()
    
    conteo = {}
    for c in grupos_res.data:
        mid = c['materia_id']
        conteo[mid] = conteo.get(mid, 0) + 1
    
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
        datos = client.rpc("uso_salones_por_periodo",
                           {"p_periodo": int(periodo_id)}).execute().data or []
    else:
        datos = client.table("uso_salones").select("*").execute().data or []

    if codigo_busqueda.strip():
        cb = codigo_busqueda.strip().lower()
        datos = [d for d in datos if cb in str(d.get("codigo") or "").lower()]

    if tipo_filtro and tipo_filtro != "Todos":
        datos = [d for d in datos if d.get("tipo_uso_descripcion") == tipo_filtro]

    datos.sort(key=lambda d: str(d.get("codigo") or ""))
    return datos


def buscar_salones_por_rango(codigo_busqueda="", tipo_filtro="", fecha_ini=None, fecha_fin=None):
    """Busca salones y calcula uso REAL en el rango de fechas dado.
    Usa la RPC uso_salones_por_rango."""
    client = get_client()
    fi = fecha_ini.isoformat() if fecha_ini else "1900-01-01"
    ff = fecha_fin.isoformat() if fecha_fin else "9999-12-31"

    datos = client.rpc("uso_salones_por_rango",
                       {"p_fecha_ini": fi, "p_fecha_fin": ff}).execute().data or []

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


def clases_en_salon_por_rango(salon_codigo, fecha_ini, fecha_fin):
    """Devuelve las clases del salón cuyas fechas se traslapan con el rango dado."""
    client = get_client()
    fi = fecha_ini.isoformat() if fecha_ini else "1900-01-01"
    ff = fecha_fin.isoformat() if fecha_fin else "9999-12-31"

    res = client.table("horarios").select(
        "dia_semana, hora_inicio, hora_fin, crn, periodo_id, "
        "clases!inner(crn, periodo_id, grupo, clave_periodo, materia_id, "
        "fecha_inicio, fecha_fin, "
        "materias(descripcion), maestros(nombre_completo))"
    ).eq("salon_codigo", salon_codigo).execute()

    # Filtrar en Python por traslape de fechas
    out = []
    for h in (res.data or []):
        c = h.get("clases") or {}
        cfi = c.get("fecha_inicio") or "1900-01-01"
        cff = c.get("fecha_fin") or "9999-12-31"
        if cfi <= ff and fi <= cff:
            out.append(h)
    return out


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
    
    todas = clases_de_maestro(maestro_clave, periodo_id)
    
    query_agrup = client.table("clases_agrupadas").select("*").eq("maestro_clave", maestro_clave)
    if periodo_id:
        query_agrup = query_agrup.eq("periodo_id", periodo_id)
    agrupadas = query_agrup.execute().data
    
    crns_agrupados = {}
    info_grupos = {}
    
    for g in agrupadas:
        for crn in g['crns']:
            crns_agrupados[(crn, g['periodo_id'])] = g['grupo_id']
        info_grupos[g['grupo_id']] = g
    
    resultados = []
    grupos_ya_procesados = set()
    
    for c in todas:
        clave = (c['crn'], c['periodo_id'])
        
        if clave in crns_agrupados:
            grupo_id = crns_agrupados[clave]
            if grupo_id in grupos_ya_procesados:
                continue
            grupos_ya_procesados.add(grupo_id)
            
            info = info_grupos[grupo_id]
            clases_del_grupo = [
                cc for cc in todas 
                if (cc['crn'], cc['periodo_id']) in [(crn, info['periodo_id']) for crn in info['crns']]
            ]
            
            todos_horarios = []
            for cc in clases_del_grupo:
                todos_horarios.extend(cc.get('horarios') or [])
            
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
    
    todos = grupos_de_materia(materia_id, periodo_id)
    
    query_agrup = client.table("clases_agrupadas").select("*").eq("materia_id", materia_id)
    if periodo_id:
        query_agrup = query_agrup.eq("periodo_id", periodo_id)
    agrupadas = query_agrup.execute().data
    
    crns_agrupados = {}
    info_grupos = {}
    
    for g in agrupadas:
        for crn in g['crns']:
            crns_agrupados[(crn, g['periodo_id'])] = g['grupo_id']
        info_grupos[g['grupo_id']] = g
    
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
                'crn': info['crn_principal'],
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