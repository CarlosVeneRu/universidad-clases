"""
Punto de entrada del Sistema de Gestión de Clases UVM.
Configura la navegación personalizada.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st


st.set_page_config(
    page_title="Sistema de Clases UVM",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Definir las páginas principales
inicio = st.Page("paginas/inicio.py", title="Inicio", icon="🏠", default=True)
buscar = st.Page("paginas/buscar_clases.py", title="Clases", icon="🔍")
maestros = st.Page("paginas/maestros.py", title="Maestros", icon="👨‍🏫")
salones = st.Page("paginas/salones.py", title="Salones", icon="🚪")
materias = st.Page("paginas/materias.py", title="Materias", icon="📚")

# Páginas de alertas (subsecciones)
choques = st.Page("paginas/choques.py", title="Choques", icon="🚨")
vencidas = st.Page("paginas/vencidas.py", title="Vencidas", icon="📦")

# Páginas de administración
exportar = st.Page("paginas/exportar.py", title="Exportar Datos", icon="📤")
subir = st.Page("paginas/subir_excel.py", title="Subir Excel", icon="📥")


# Configurar la navegación con secciones
pg = st.navigation({
    "Principal": [inicio, buscar, maestros, salones, materias],
    "Alertas": [choques, vencidas],
    "Administración": [subir, exportar]
})
pg.run()