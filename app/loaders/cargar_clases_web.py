"""
Versión web del cargador de clases.
Recibe el Excel como bytes (subido desde el navegador), procesa todo
y devuelve un reporte detallado de los cambios.

NO modifica la base directamente: primero compara con lo existente,
construye un reporte de cambios, y solo aplica si se confirma.
"""
import io
import re
import pandas as pd
from app.utils.supabase_client import get_supabase_client


DIAS = {
    'Lunes': 'LUNES',
    'Martes': 'MARTES',
    'Miercoles': 'MIERCOLES',
    'Jueves': 'JUEVES',
    'Viernes': 'VIERNES',
    'Sábado': 'SABADO',
    'Domingo': 'DOMINGO'
}


def parsear_horario(texto):
    """Extrae dos horas HH:MM del texto. Devuelve (None, None) si no se puede."""
    if pd.isna(texto) or not str(texto).strip():
        return None, None
    horas = re.findall(r'\d{1,2}:\d{2}', str(texto).strip())
    if len(horas) >= 2:
        h_inicio, h_fin = horas[0], horas[1]
        if len(h_inicio.split(':')[0]) == 1:
            h_inicio = '0' + h_inicio
        if len(h_fin.split(':')[0]) == 1:
            h_fin = '0' + h_fin
        return h_inicio, h_fin
    return None, None


def limpiar_str(valor):
    if pd.isna(valor):
        return None
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    s = str(valor).strip()
    return s if s else None


def limpiar_int(valor):
    if pd.isna(valor):
        return None
    try:
        return int(valor)
    except (ValueError, TypeError):
        return None


def limpiar_fecha(valor):
    if pd.isna(valor):
        return None
    try:
        if isinstance(valor, str):
            valor = pd.to_datetime(valor)
        return valor.strftime('%Y-%m-%d')
    except Exception:
        return None


def es_salon_virtual(codigo):
    if codigo is None:
        return False
    return '-Z' in str(codigo).upper()


def leer_excel_a_dataframe(excel_bytes):
    """Recibe bytes del Excel y devuelve un DataFrame."""
    return pd.read_excel(io.BytesIO(excel_bytes))


def validar_estructura_excel(df):
    """Verifica que el Excel tenga las columnas mínimas necesarias."""
    columnas_requeridas = [
        'Crn ID', 'Periodo Banner ID', 'Grupo ID', 'Materia ID',
        'Materia DESC', 'Fecha Inicio ID', 'Fecha Final ID'
    ]
    faltantes = [c for c in columnas_requeridas if c not in df.columns]
    return faltantes


def analizar_cambios(df_nuevo):
    """
    Compara el Excel nuevo con los datos actuales en la base.
    NO modifica nada. Solo devuelve un reporte de qué cambiaría.
    """
    client = get_supabase_client()
    
    # 1. Obtener todas las clases actuales (paginando)
    clases_actuales_list = []
    offset = 0
    while True:
        batch = client.table("clases").select(
            "crn, periodo_id, grupo, materia_id, maestro_clave, "
            "fecha_inicio, fecha_fin, inscritos, capacidad_materia, status, "
            "modificado_por, modificado_en"
        ).range(offset, offset + 999).execute()
        if not batch.data:
            break
        clases_actuales_list.extend(batch.data)
        if len(batch.data) < 1000:
            break
        offset += 1000
    
    # Indexar por (crn, periodo_id)
    clases_actuales = {}
    for c in clases_actuales_list:
        clases_actuales[(c['crn'], c['periodo_id'])] = c
    
    # 2. Procesar el Excel: obtener las "claves" únicas
    claves_excel = set()
    clases_excel = {}  # (crn, periodo_id) -> dict con datos
    
    for _, row in df_nuevo.iterrows():
        crn = limpiar_int(row.get('Crn ID'))
        periodo_id = limpiar_int(row.get('Periodo Banner ID'))
        
        if crn is None or periodo_id is None:
            continue
        
        clave = (crn, periodo_id)
        if clave in claves_excel:
            continue  # Duplicado en el Excel
        claves_excel.add(clave)
        
        clases_excel[clave] = {
            'crn': crn,
            'periodo_id': periodo_id,
            'grupo': limpiar_str(row.get('Grupo ID')),
            'materia_id': limpiar_str(row.get('Materia ID')),
            'fecha_inicio': limpiar_fecha(row.get('Fecha Inicio ID')),
            'fecha_fin': limpiar_fecha(row.get('Fecha Final ID')),
            'inscritos': limpiar_int(row.get('Inscritos')) or 0,
            'capacidad_materia': limpiar_int(row.get('Capacidad')),
            'status': limpiar_str(row.get('Status ID')) or 'ACTIVA'
        }
    
    # 3. Categorizar las diferencias
    claves_actuales = set(clases_actuales.keys())
    
    nuevas = claves_excel - claves_actuales  # Están en el Excel pero no en la base
    eliminadas = claves_actuales - claves_excel  # Están en la base pero no en el Excel
    en_ambos = claves_actuales & claves_excel
    
    # 4. De las que están en ambos, ver cuáles tienen cambios
    actualizadas = []
    iguales = 0
    con_cambios_manuales = []  # Clases que tienen modificado_por != NULL
    
    campos_a_comparar = ['grupo', 'materia_id', 'fecha_inicio', 'fecha_fin', 
                          'inscritos', 'capacidad_materia', 'status']
    
    for clave in en_ambos:
        actual = clases_actuales[clave]
        nueva = clases_excel[clave]
        
        # Detectar diferencias
        diffs = {}
        for campo in campos_a_comparar:
            v_actual = actual.get(campo)
            v_nuevo = nueva.get(campo)
            
            # Normalizar tipos
            if v_actual != v_nuevo:
                diffs[campo] = {'antes': v_actual, 'despues': v_nuevo}
        
        if diffs:
            cambio_info = {
                'crn': clave[0],
                'periodo_id': clave[1],
                'grupo': actual.get('grupo'),
                'diferencias': diffs,
                'tiene_cambio_manual': actual.get('modificado_por') is not None
            }
            actualizadas.append(cambio_info)
            
            if actual.get('modificado_por'):
                con_cambios_manuales.append(cambio_info)
        else:
            iguales += 1
    
    return {
        'total_excel': len(claves_excel),
        'total_actual': len(claves_actuales),
        'nuevas': sorted(list(nuevas)),
        'eliminadas': sorted(list(eliminadas)),
        'actualizadas': actualizadas,
        'iguales': iguales,
        'con_cambios_manuales': con_cambios_manuales,
        'clases_excel_raw': clases_excel,
        'df_nuevo': df_nuevo  # Para usar después si se aplica
    }
    
# ============================================
# APLICACIÓN DE CAMBIOS
# ============================================

def _obtener_horarios_de_excel(df_nuevo, crn_objetivo, periodo_objetivo):
    """Extrae los horarios de una clase específica del Excel."""
    fila = df_nuevo[
        (df_nuevo['Crn ID'].apply(limpiar_int) == crn_objetivo) &
        (df_nuevo['Periodo Banner ID'].apply(limpiar_int) == periodo_objetivo)
    ]
    
    if fila.empty:
        return []
    
    row = fila.iloc[0]
    horarios = []
    
    # Mapeo: columna_horario -> columna_salon -> día normalizado
    dias_cols = [
        ('Horario Lunes ID', 'Salón Lunes ID', 'LUNES'),
        ('Horario Martes ID', 'Salón Martes ID', 'MARTES'),
        ('Horario Miercoles ID', 'Salón Miercoles ID', 'MIERCOLES'),
        ('Horario Jueves ID', 'Salon Jueves ID', 'JUEVES'),  # nota: "Salon" sin tilde
        ('Horario Viernes ID', 'Salón Viernes ID', 'VIERNES'),
        ('Horario Sábado ID', 'Salón Sabado ID', 'SABADO'),
        ('Horario Domingo ID', 'Salón Domingo ID', 'DOMINGO'),
    ]
    
    for col_horario, col_salon, dia in dias_cols:
        if col_horario not in row or col_salon not in row:
            continue
        
        h_inicio, h_fin = parsear_horario(row[col_horario])
        if h_inicio is None or h_fin is None:
            continue
        
        salon = limpiar_str(row[col_salon])
        es_virtual = es_salon_virtual(salon)
        
        horarios.append({
            'crn': crn_objetivo,
            'periodo_id': periodo_objetivo,
            'dia_semana': dia,
            'hora_inicio': h_inicio,
            'hora_fin': h_fin,
            'salon_codigo': None if es_virtual else salon,
            'es_virtual': es_virtual
        })
    
    return horarios


def _datos_completos_clase(df_nuevo, crn, periodo_id):
    """Obtiene todos los campos de una clase desde el Excel para INSERT/UPDATE."""
    fila = df_nuevo[
        (df_nuevo['Crn ID'].apply(limpiar_int) == crn) &
        (df_nuevo['Periodo Banner ID'].apply(limpiar_int) == periodo_id)
    ]
    
    if fila.empty:
        return None
    
    row = fila.iloc[0]
    
    return {
        'crn': crn,
        'periodo_id': periodo_id,
        'grupo': limpiar_str(row.get('Grupo ID')),
        'clave_periodo': limpiar_str(row.get('Clave Periodo ID')),
        'materia_id': limpiar_str(row.get('Materia ID')),
        'maestro_clave': limpiar_int(row.get('Docente ID')),
        'fecha_inicio': limpiar_fecha(row.get('Fecha Inicio ID')),
        'fecha_fin': limpiar_fecha(row.get('Fecha Final ID')),
        'inscritos': limpiar_int(row.get('Inscritos')) or 0,
        'capacidad_materia': limpiar_int(row.get('Capacidad')),
        'capacidad_escenario': limpiar_int(row.get('Capacidad Escenario')),
        'vacantes': limpiar_int(row.get('Vacantes')),
        'status': limpiar_str(row.get('Status ID')) or 'ACTIVA',
        'tipo_curso': limpiar_str(row.get('Tipo Curso ID')),
        'tipo_horario': limpiar_str(row.get('Tipo Horario ID')),
        'metodo': limpiar_str(row.get('Método ID')),
        'sin_docente': str(row.get('Sin Docente ID', '')).strip() == '1',
        'sin_horario': str(row.get('Sin Horario ID', '')).strip() == '1',
        'impartido_id': limpiar_str(row.get('Impartición ID')),
        'impartido_descripcion': limpiar_str(row.get('Desc Impartición ID')),
        'modulo_id': limpiar_str(row.get('Modulo ID')),
        'modulo_descripcion': limpiar_str(row.get('desc modulo Ptms')),
        'semanas_curso': limpiar_int(row.get('Semanas del curso')),
        'horas_long': limpiar_str(row.get('Horas Long')),
    }


def aplicar_cambios(analisis, respetar_cambios_manuales=True, usuario="sistema_web"):
    """
    Aplica los cambios analizados a la base de datos.
    
    Args:
        analisis: el dict resultado de analizar_cambios()
        respetar_cambios_manuales: si True, las clases con modificado_por != NULL no se actualizan
        usuario: nombre del usuario que aplica los cambios (para auditoría)
    
    Returns:
        dict con el reporte de lo que se hizo
    """
    client = get_supabase_client()
    df_nuevo = analisis['df_nuevo']
    
    reporte = {
        'nuevas_insertadas': 0,
        'actualizadas': 0,
        'actualizadas_saltadas': 0,  # las que tenían cambio manual y se respetaron
        'horarios_actualizados': 0,
        'errores': []
    }
    
    # 1. INSERTAR CLASES NUEVAS
    for crn, periodo_id in analisis['nuevas']:
        try:
            datos = _datos_completos_clase(df_nuevo, crn, periodo_id)
            if datos is None:
                continue
            
            datos['creado_por'] = usuario
            datos['modificado_por'] = None  # NO marcar como manual
            
            client.table("clases").insert(datos).execute()
            
            # Insertar horarios
            horarios = _obtener_horarios_de_excel(df_nuevo, crn, periodo_id)
            if horarios:
                client.table("horarios").insert(horarios).execute()
                reporte['horarios_actualizados'] += len(horarios)
            
            reporte['nuevas_insertadas'] += 1
        except Exception as e:
            reporte['errores'].append(f"Insertando CRN {crn}: {str(e)[:100]}")
    
    # 2. ACTUALIZAR CLASES EXISTENTES
    for cambio in analisis['actualizadas']:
        crn = cambio['crn']
        periodo_id = cambio['periodo_id']
        
        # Si tiene cambio manual y queremos respetarlo, saltar
        if cambio['tiene_cambio_manual'] and respetar_cambios_manuales:
            reporte['actualizadas_saltadas'] += 1
            continue
        
        try:
            datos = _datos_completos_clase(df_nuevo, crn, periodo_id)
            if datos is None:
                continue
            
            # NO marcar como modificado_por: el Excel es la fuente de verdad
            datos['modificado_por'] = None
            
            # UPDATE usando la llave compuesta
            client.table("clases").update(datos).eq("crn", crn).eq("periodo_id", periodo_id).execute()
            
            # Actualizar horarios: borrar viejos + insertar nuevos
            client.table("horarios").delete().eq("crn", crn).eq("periodo_id", periodo_id).execute()
            
            horarios = _obtener_horarios_de_excel(df_nuevo, crn, periodo_id)
            if horarios:
                client.table("horarios").insert(horarios).execute()
                reporte['horarios_actualizados'] += len(horarios)
            
            reporte['actualizadas'] += 1
        except Exception as e:
            reporte['errores'].append(f"Actualizando CRN {crn}: {str(e)[:100]}")
    
    return reporte