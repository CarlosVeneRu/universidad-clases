"""
Carga los salones desde el Excel A_ESCENARIOS.xlsx hacia la tabla 'salones' en Supabase.
Excluye salones virtuales (con código que empieza con '-Z').
Maneja salones multifuncionales consolidando sus tipos de uso.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
from app.utils.supabase_client import get_supabase_client


def cargar_salones(ruta_excel: str):
    """
    Lee el archivo de salones y los inserta en Supabase.
    - Excluye salones virtuales (códigos con '-Z').
    - Consolida salones multifuncionales (mismo código, varios tipos de uso).
    """
    print(f"📂 Leyendo archivo: {ruta_excel}")
    df = pd.read_excel(ruta_excel)
    print(f"   Encontradas {len(df)} filas")
    
    client = get_supabase_client()
    
    # 1. Asegurar que el campus existe
    campus_unicos = df['CodeCampus'].unique()
    print(f"\n🏫 Verificando campus...")
    for campus_id in campus_unicos:
        client.table("campus").upsert({
            "id": int(campus_id),
            "nombre": "QUERETARO" if campus_id == 11 else f"CAMPUS_{campus_id}"
        }).execute()
        print(f"   ✅ Campus {campus_id} listo")
    
    # 2. Limpiar valores
    df['CodeRoom'] = df['CodeRoom'].astype(str).str.strip()
    df['CodeUseType'] = df['CodeUseType'].astype(str).str.strip()
    df['DescriptionUseType'] = df['DescriptionUseType'].astype(str).str.strip()
    
    # 3. EXCLUIR SALONES VIRTUALES (con -Z en el código)
    print(f"\n🚫 Filtrando salones virtuales...")
    total_antes = len(df)
    df = df[~df['CodeRoom'].str.contains('-Z', case=False, na=False)]
    excluidos = total_antes - len(df)
    print(f"   ℹ️  Excluidos {excluidos} salones virtuales (con '-Z')")
    print(f"   ✅ Quedan {len(df)} entradas de salones físicos")
    
    # 4. Consolidar salones multifuncionales
    print(f"\n🔍 Consolidando salones multifuncionales...")
    consolidados = df.groupby('CodeRoom').agg({
        'CodeCampus': 'first',
        'DescriptionRoom': 'first',
        'Capacity': 'first',
        'CodeUseType': lambda x: ','.join(sorted(set(x))),
        'DescriptionUseType': lambda x: ', '.join(sorted(set(x)))
    }).reset_index()
    
    duplicados = len(df) - len(consolidados)
    if duplicados > 0:
        print(f"   ℹ️  Se consolidaron {duplicados} entradas duplicadas")
    print(f"   Total de salones únicos: {len(consolidados)}")
    
    # 5. Preparar y cargar datos
    print(f"\n🚪 Cargando salones a Supabase...")
    salones_a_cargar = []
    for _, row in consolidados.iterrows():
        salones_a_cargar.append({
            "codigo": row['CodeRoom'],
            "descripcion": row['DescriptionRoom'] if pd.notna(row['DescriptionRoom']) else None,
            "capacidad": int(row['Capacity']) if pd.notna(row['Capacity']) else 0,
            "tipo_uso_codigo": row['CodeUseType'],
            "tipo_uso_descripcion": row['DescriptionUseType'],
            "campus_id": int(row['CodeCampus'])
        })
    
    total = len(salones_a_cargar)
    cargados = 0
    for i in range(0, total, 100):
        lote = salones_a_cargar[i:i + 100]
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