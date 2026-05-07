"""
Carga los salones desde el Excel A_ESCENARIOS.xlsx hacia la tabla 'salones' en Supabase.
Maneja salones multifuncionales (mismo código, varios tipos de uso) consolidándolos.
"""
import sys
from pathlib import Path

# Permitir importar desde la carpeta raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
from app.utils.supabase_client import get_supabase_client


def cargar_salones(ruta_excel: str):
    """
    Lee el archivo de salones y los inserta en Supabase.
    Si un salón aparece varias veces (multifuncional), consolida sus tipos de uso.
    """
    print(f"📂 Leyendo archivo: {ruta_excel}")
    df = pd.read_excel(ruta_excel)
    print(f"   Encontradas {len(df)} filas")
    
    client = get_supabase_client()
    
    # 1. Asegurarnos de que el campus existe
    campus_unicos = df['CodeCampus'].unique()
    print(f"\n🏫 Verificando campus...")
    for campus_id in campus_unicos:
        client.table("campus").upsert({
            "id": int(campus_id),
            "nombre": "QUERETARO" if campus_id == 11 else f"CAMPUS_{campus_id}"
        }).execute()
        print(f"   ✅ Campus {campus_id} listo")
    
    # 2. Consolidar salones multifuncionales
    print(f"\n🔍 Consolidando salones multifuncionales...")
    
    # Limpiar valores
    df['CodeRoom'] = df['CodeRoom'].astype(str).str.strip()
    df['CodeUseType'] = df['CodeUseType'].astype(str).str.strip()
    df['DescriptionUseType'] = df['DescriptionUseType'].astype(str).str.strip()
    
    # Agrupar por CodeRoom y unir los tipos de uso
    consolidados = df.groupby('CodeRoom').agg({
        'CodeCampus': 'first',
        'DescriptionRoom': 'first',
        'Capacity': 'first',
        'CodeUseType': lambda x: ','.join(sorted(set(x))),
        'DescriptionUseType': lambda x: ', '.join(sorted(set(x)))
    }).reset_index()
    
    duplicados_originales = len(df) - len(consolidados)
    if duplicados_originales > 0:
        print(f"   ℹ️  Se consolidaron {duplicados_originales} entradas duplicadas")
    print(f"   Total de salones únicos: {len(consolidados)}")
    
    # 3. Preparar datos para Supabase
    print(f"\n🚪 Cargando salones a Supabase...")
    salones_a_cargar = []
    
    for _, row in consolidados.iterrows():
        salon = {
            "codigo": row['CodeRoom'],
            "descripcion": row['DescriptionRoom'] if pd.notna(row['DescriptionRoom']) else None,
            "capacidad": int(row['Capacity']) if pd.notna(row['Capacity']) else 0,
            "tipo_uso_codigo": row['CodeUseType'],
            "tipo_uso_descripcion": row['DescriptionUseType'],
            "campus_id": int(row['CodeCampus'])
        }
        salones_a_cargar.append(salon)
    
    # Insertar en lotes de 100
    total = len(salones_a_cargar)
    lote_tam = 100
    cargados = 0
    
    for i in range(0, total, lote_tam):
        lote = salones_a_cargar[i:i + lote_tam]
        try:
            client.table("salones").upsert(lote).execute()
            cargados += len(lote)
            print(f"   ✅ Cargados {cargados}/{total}")
        except Exception as e:
            print(f"   ❌ Error en lote {i}: {e}")
    
    print(f"\n🎉 Total de salones cargados: {cargados}/{total}")
    return cargados


if __name__ == "__main__":
    ruta = input("Ruta del archivo Excel de salones (Enter para usar el por defecto): ").strip()
    if not ruta:
        ruta = "data/A_ESCENARIOS.xlsx"
    
    cargar_salones(ruta)