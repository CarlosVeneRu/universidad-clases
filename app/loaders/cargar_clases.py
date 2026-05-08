"""
Carga las clases desde el Excel Detalle_Mega_Figpos.xlsx hacia Supabase.
Llena en cascada: periodos → carreras → maestros → materias → clases → horarios.

Maneja:
- CRNs duplicados en periodos diferentes (llave compuesta crn+periodo_id).
- Salones virtuales (-Z): los marca pero no los referencia como salones físicos.
- Datos faltantes (carreras, docentes vacíos = clases multi).
"""
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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
    """Convierte un valor a string limpio o None. Maneja floats que son enteros (33.0 → '33')."""
    if pd.isna(valor):
        return None
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    s = str(valor).strip()
    return s if s else None


def limpiar_int(valor):
    """Convierte a int o None."""
    if pd.isna(valor):
        return None
    try:
        return int(valor)
    except (ValueError, TypeError):
        return None


def limpiar_fecha(valor):
    """Convierte a string ISO 'YYYY-MM-DD' o None."""
    if pd.isna(valor):
        return None
    try:
        if isinstance(valor, str):
            valor = pd.to_datetime(valor)
        return valor.strftime('%Y-%m-%d')
    except Exception:
        return None


def es_salon_virtual(codigo):
    """Determina si un código de salón corresponde a uno virtual (-Z)."""
    if codigo is None:
        return False
    return '-Z' in str(codigo).upper()


def cargar_clases(ruta_excel: str):
    """Procesa el Excel completo y carga datos en 6 tablas en cascada."""
    print(f"📂 Leyendo archivo: {ruta_excel}")
    df = pd.read_excel(ruta_excel)
    print(f"   Encontradas {len(df)} filas")
    
    client = get_supabase_client()
    
    # =============================================
    # 1. PERIODOS
    # =============================================
    print(f"\n📅 Cargando periodos...")
    periodos_agrupados = df.groupby('Periodo Banner ID').agg({
        'Año ID': 'first',
        'Ciclo ID': 'first',
        'Clave Periodo ID': lambda x: ','.join(sorted(set(str(v) for v in x.dropna())))
    }).reset_index()
    
    periodos_data = []
    for _, row in periodos_agrupados.iterrows():
        periodos_data.append({
            "id": int(row['Periodo Banner ID']),
            "anio": int(row['Año ID']),
            "ciclo": int(row['Ciclo ID']),
            "descripcion": limpiar_str(row['Clave Periodo ID'])
        })
    
    if periodos_data:
        client.table("periodos").upsert(periodos_data).execute()
        print(f"   ✅ Cargados {len(periodos_data)} periodos")
    
    # =============================================
    # 2. CARRERAS
    # =============================================
    print(f"\n🎓 Cargando carreras...")
    carreras = df[[
        'Carrera Hpn ID', 'Carrera Hpn DESC',
        'Carrera Banner ID', 'Carrera Banner DESC',
        'Departamento ID', 'Nivel ID', 'Nivel DESC'
    ]].copy()
    
    carreras = carreras[
        carreras['Carrera Hpn ID'].notna() | carreras['Carrera Banner ID'].notna()
    ]
    
    carreras['_hpn'] = carreras['Carrera Hpn ID'].apply(lambda x: limpiar_str(x) if pd.notna(x) else None)
    carreras['_banner'] = carreras['Carrera Banner ID'].apply(lambda x: limpiar_str(x))
    carreras = carreras.drop_duplicates(subset=['_hpn', '_banner'], keep='first')
    
    carreras_data = []
    for _, row in carreras.iterrows():
        carreras_data.append({
            "clave_hpn": row['_hpn'],
            "nombre_hpn": limpiar_str(row['Carrera Hpn DESC']),
            "clave_banner": row['_banner'],
            "nombre_banner": limpiar_str(row['Carrera Banner DESC']),
            "departamento_id": limpiar_int(row['Departamento ID']),
            "nivel_id": limpiar_str(row['Nivel ID']),
            "nivel_descripcion": limpiar_str(row['Nivel DESC'])
        })
    
    if carreras_data:
        for i in range(0, len(carreras_data), 100):
            lote = carreras_data[i:i+100]
            try:
                client.table("carreras").upsert(
                    lote, 
                    on_conflict="clave_hpn,clave_banner"
                ).execute()
            except Exception as e:
                print(f"   ⚠️  Error en lote carreras {i}: {e}")
        print(f"   ✅ Cargadas {len(carreras_data)} carreras")
    
    print(f"   🔍 Construyendo mapeo de carreras...")
    carrera_keys_to_id = {}
    response = client.table("carreras").select("id, clave_hpn, clave_banner").execute()
    for c in response.data:
        carrera_keys_to_id[(c['clave_hpn'], c['clave_banner'])] = c['id']
    print(f"   ✅ Mapeo de {len(carrera_keys_to_id)} carreras listo")
    
    # =============================================
    # 3. MAESTROS
    # =============================================
    print(f"\n👨‍🏫 Cargando maestros...")
    maestros_df = df[df['Docente ID'].notna()][['Docente ID', 'Docente DESC']].drop_duplicates()
    
    maestros_data = []
    maestros_vistos = set()
    for _, row in maestros_df.iterrows():
        try:
            clave = int(float(str(row['Docente ID']).strip()))
            if clave in maestros_vistos:
                continue
            maestros_vistos.add(clave)
            maestros_data.append({
                "clave": clave,
                "nombre_completo": limpiar_str(row['Docente DESC']) or "SIN NOMBRE",
                "activo": True
            })
        except (ValueError, TypeError):
            continue
    
    if maestros_data:
        for i in range(0, len(maestros_data), 200):
            lote = maestros_data[i:i+200]
            client.table("maestros").upsert(lote).execute()
        print(f"   ✅ Cargados {len(maestros_data)} maestros")
    
    # =============================================
    # 4. MATERIAS
    # =============================================
    print(f"\n📚 Cargando materias...")
    materias_df = df[['Materia ID', 'Materia DESC', 'Grado materia', 
                       'A. concentracion', 'Semanas del curso', 'Tipo uso materia']].drop_duplicates(subset=['Materia ID'])
    
    materias_data = []
    for _, row in materias_df.iterrows():
        materias_data.append({
            "id": limpiar_str(row['Materia ID']),
            "descripcion": limpiar_str(row['Materia DESC']) or "SIN DESCRIPCION",
            "grado_materia": limpiar_int(row['Grado materia']),
            "area_concentracion": limpiar_str(row['A. concentracion']),
            "semanas_curso": limpiar_int(row['Semanas del curso']),
            "tipos_uso_compatibles": limpiar_str(row['Tipo uso materia'])
        })
    
    if materias_data:
        for i in range(0, len(materias_data), 200):
            lote = materias_data[i:i+200]
            client.table("materias").upsert(lote).execute()
        print(f"   ✅ Cargadas {len(materias_data)} materias")
    
    # =============================================
    # 5. CLASES (llave compuesta CRN + periodo)
    # =============================================
    print(f"\n📝 Cargando clases (llave: CRN + periodo)...")
    
    clases_data = []
    crn_periodo_vistos = set()
    
    for _, row in df.iterrows():
        crn = limpiar_int(row['Crn ID'])
        periodo_id = limpiar_int(row['Periodo Banner ID'])
        
        if crn is None or periodo_id is None:
            continue
        
        # La llave única ahora es (crn, periodo_id)
        clave = (crn, periodo_id)
        if clave in crn_periodo_vistos:
            continue
        crn_periodo_vistos.add(clave)
        
        clave_hpn = limpiar_str(row['Carrera Hpn ID']) if pd.notna(row['Carrera Hpn ID']) else None
        clave_banner = limpiar_str(row['Carrera Banner ID'])
        carrera_id = carrera_keys_to_id.get((clave_hpn, clave_banner))
        
        maestro_clave = None
        if pd.notna(row['Docente ID']):
            try:
                maestro_clave = int(float(str(row['Docente ID']).strip()))
            except (ValueError, TypeError):
                pass
        
        clases_data.append({
            "crn": crn,
            "periodo_id": periodo_id,
            "grupo": limpiar_str(row['Grupo ID']),
            "materia_id": limpiar_str(row['Materia ID']),
            "maestro_clave": maestro_clave,
            "carrera_id": carrera_id,
            "campus_id": limpiar_int(row['Campus ID']),
            "fecha_inicio": limpiar_fecha(row['Fecha Inicio ID']),
            "fecha_fin": limpiar_fecha(row['Fecha Final ID']),
            "capacidad_materia": limpiar_int(row['Capacidad']),
            "capacidad_escenario": limpiar_int(row['Capacidad Escenario']),
            "inscritos": limpiar_int(row['Inscritos']) or 0,
            "vacantes": limpiar_int(row['Vacantes']) or 0,
            "tipo_curso": limpiar_str(row['Tipo Curso ID']),
            "tipo_horario": limpiar_str(row['Tipo Horario ID']),
            "metodo": limpiar_str(row['Método ID']),
            "status": limpiar_str(row['Status ID']) or 'ACTIVA',
            "semanas_curso": limpiar_int(row['Semanas del curso']),
            "impartido_id": limpiar_str(row['Impartición ID']),
            "impartido_descripcion": limpiar_str(row['Desc Impartición ID']),
            "modulo_id": limpiar_str(row['Modulo ID']),
            "modulo_descripcion": limpiar_str(row['desc modulo Ptms']),
            "sin_docente": bool(limpiar_int(row['Sin Docente ID'])),
            "sin_horario": bool(limpiar_int(row['Sin Horario ID'])),
            "horas_long": limpiar_int(row['Horas Long'])
        })
    
    if clases_data:
        total = len(clases_data)
        cargados = 0
        for i in range(0, total, 100):
            lote = clases_data[i:i+100]
            try:
                client.table("clases").upsert(lote, on_conflict="crn,periodo_id").execute()
                cargados += len(lote)
                if cargados % 500 == 0 or cargados == total:
                    print(f"   ✅ Cargadas {cargados}/{total} clases")
            except Exception as e:
                print(f"   ❌ Error en lote clases {i}: {e}")
        print(f"   ✅ Total clases cargadas: {cargados}/{total}")
    
    # =============================================
    # 6. HORARIOS
    # =============================================
    print(f"\n🕐 Cargando horarios...")
    
    horarios_data = []
    horarios_virtuales = 0
    
    for _, row in df.iterrows():
        crn = limpiar_int(row['Crn ID'])
        periodo_id = limpiar_int(row['Periodo Banner ID'])
        
        if crn is None or periodo_id is None:
            continue
        
        for dia, dia_nombre in DIAS.items():
            col_horario = f'Horario {dia} ID'
            if dia == 'Jueves':
                col_salon = 'Salon Jueves ID'
            elif dia == 'Sábado':
                col_salon = 'Salón Sabado ID'
            else:
                col_salon = f'Salón {dia} ID'
            
            if col_horario not in df.columns or col_salon not in df.columns:
                continue
            
            horario_txt = row[col_horario]
            salon_txt = row[col_salon]
            
            h_inicio, h_fin = parsear_horario(horario_txt)
            if not h_inicio or not h_fin:
                continue
            
            salon_codigo = limpiar_str(salon_txt)
            es_virtual = es_salon_virtual(salon_codigo)
            
            if es_virtual:
                horarios_virtuales += 1
                # Para horarios virtuales, NO guardamos referencia al salón
                # (porque el salón Z no existe en la tabla salones)
                horarios_data.append({
                    "crn": crn,
                    "periodo_id": periodo_id,
                    "dia_semana": dia_nombre,
                    "hora_inicio": h_inicio,
                    "hora_fin": h_fin,
                    "salon_codigo": None,  # Sin referencia física
                    "es_virtual": True
                })
            else:
                horarios_data.append({
                    "crn": crn,
                    "periodo_id": periodo_id,
                    "dia_semana": dia_nombre,
                    "hora_inicio": h_inicio,
                    "hora_fin": h_fin,
                    "salon_codigo": salon_codigo,
                    "es_virtual": False
                })
    
    if horarios_data:
        total = len(horarios_data)
        cargados = 0
        for i in range(0, total, 200):
            lote = horarios_data[i:i+200]
            try:
                client.table("horarios").insert(lote).execute()
                cargados += len(lote)
                if cargados % 1000 == 0 or cargados == total:
                    print(f"   ✅ Cargados {cargados}/{total} horarios")
            except Exception as e:
                print(f"   ⚠️  Error en lote horarios {i}: {e}")
        print(f"   ✅ Total horarios cargados: {cargados}/{total}")
        if horarios_virtuales > 0:
            print(f"   📡 De ellos, {horarios_virtuales} son virtuales (sin salón físico)")
    
    # =============================================
    # RESUMEN FINAL
    # =============================================
    print(f"\n{'='*60}")
    print(f"🎉 CARGA COMPLETADA")
    print(f"{'='*60}")
    print(f"   Periodos:           {len(periodos_data)}")
    print(f"   Carreras:           {len(carreras_data)}")
    print(f"   Maestros:           {len(maestros_data)}")
    print(f"   Materias:           {len(materias_data)}")
    print(f"   Clases (CRN+per):   {len(clases_data)}")
    print(f"   Horarios:           {len(horarios_data)}")
    print(f"     - Físicos:        {len(horarios_data) - horarios_virtuales}")
    print(f"     - Virtuales:      {horarios_virtuales}")
    print(f"{'='*60}")


if __name__ == "__main__":
    ruta = input("Ruta del archivo Excel de clases (Enter para usar el por defecto): ").strip()
    if not ruta:
        ruta = "data/Detalle_Mega_Figpos.xlsx"
    cargar_clases(ruta)