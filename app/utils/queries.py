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
    
    res = query.order("descripcion").limit(200).execute()
    return res.data


@st.cache_data(ttl=60)
def buscar_salones(codigo_busqueda="", tipo_filtro=""):
    """Busca salones por código o tipo."""
    client = get_client()
    query = client.table("salones").select("*")
    
    if codigo_busqueda.strip():
        query = query.ilike("codigo", f"%{codigo_busqueda.strip()}%")
    
    if tipo_filtro and tipo_filtro != "Todos":
        query = query.eq("tipo_uso_descripcion", tipo_filtro)
    
    res = query.order("codigo").execute()
    return res.data


def clases_de_maestro(maestro_clave, periodo_id=None):
    """Devuelve todas las clases de un maestro, con sus horarios."""
    client = get_client()
    query = client.table("clases").select(
        "crn, periodo_id, grupo, clave_periodo, status, "
        "fecha_inicio, fecha_fin, inscritos, capacidad_materia, "
        "materias(id, descripcion), "
        "horarios(dia_semana, hora_inicio, hora_fin, salon_codigo, es_virtual)"
    ).eq("maestro_clave", maestro_clave)
    
    if periodo_id:
        query = query.eq("periodo_id", periodo_id)
    
    res = query.order("periodo_id").execute()
    return res.data


def clases_en_salon(salon_codigo, periodo_id=None):
    """Devuelve todas las clases que ocupan un salón."""
    client = get_client()
    
    # Query: horarios -> clases -> materia/maestro
    query = client.table("horarios").select(
        "dia_semana, hora_inicio, hora_fin, crn, periodo_id, "
        "clases(crn, periodo_id, grupo, clave_periodo, materia_id, "
        "materias(descripcion), maestros(nombre_completo))"
    ).eq("salon_codigo", salon_codigo)
    
    if periodo_id:
        query = query.eq("periodo_id", periodo_id)
    
    res = query.execute()
    return res.data


def grupos_de_materia(materia_id, periodo_id=None):
    """Devuelve todos los grupos (CRNs) de una materia."""
    client = get_client()
    query = client.table("clases").select(
        "crn, periodo_id, grupo, clave_periodo, status, inscritos, capacidad_materia, "
        "fecha_inicio, fecha_fin, "
        "maestros(clave, nombre_completo)"
    ).eq("materia_id", materia_id)
    
    if periodo_id:
        query = query.eq("periodo_id", periodo_id)
    
    res = query.order("periodo_id").order("grupo").execute()
    return res.data