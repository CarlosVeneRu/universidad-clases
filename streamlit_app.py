"""
Punto de entrada del Sistema de Gestión de Clases UVM.
Configura la navegación personalizada.
"""
import sys
import base64
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import streamlit as st

st.set_page_config(
    page_title="Gestor de Clases UVM",
    page_icon="assets/uvm_logo.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# LOGO UVM grande en el header del sidebar (vía CSS background)
# ============================================
def _logo_base64(ruta):
    with open(ruta, "rb") as f:
        return base64.b64encode(f.read()).decode()

_logo_b64 = _logo_base64("assets/uvm_logo.png")

st.markdown(f"""
    <style>
        /* Pintar el logo como fondo del header del sidebar */
        [data-testid="stSidebarHeader"] {{
            background-image: url("data:image/png;base64,{_logo_b64}");
            background-repeat: no-repeat;
            background-position: center;
            background-size: contain;
            height: 120px;
            margin: 0.5rem 1rem 0.5rem 1rem;
        }}

        /* Esconder el logo chiquito por defecto de st.logo si lo hubiera */
        [data-testid="stLogo"] {{
            display: none;
        }}

        /* ====== TEXTO DE LAS PÁGINAS MÁS GRANDE ====== */
        /* Texto normal (párrafos, markdown) */
        [data-testid="stMarkdownContainer"] p {{
            font-size: 1.25rem;
            line-height: 1.65;
        }}

        /* Texto dentro de listas */
        [data-testid="stMarkdownContainer"] li {{
            font-size: 1.25rem;
            line-height: 1.65;
        }}

        /* Etiquetas de los selectores y filtros */
        [data-testid="stWidgetLabel"] label p {{
            font-size: 1.15rem;
        }}

        /* Texto de las pestañas y radios */
        [data-testid="stRadio"] label p,
        [data-baseweb="tab"] {{
            font-size: 1.12rem;
        }}

        /* Captions (texto pequeño gris) un poco más grandes */
        [data-testid="stCaptionContainer"] p {{
            font-size: 1.0rem;
        }}
    </style>
""", unsafe_allow_html=True)

# ============================================
# DEFINIR PÁGINAS
# ============================================
inicio = st.Page("paginas/inicio.py", title="Inicio", icon="🏠", default=True)
buscar = st.Page("paginas/buscar_clases.py", title="Clases", icon="🔍")
maestros = st.Page("paginas/maestros.py", title="Maestros", icon="👨‍🏫")
salones = st.Page("paginas/salones.py", title="Salones", icon="🚪")
materias = st.Page("paginas/materias.py", title="Materias", icon="📚")

# Páginas de alertas
choques = st.Page("paginas/choques.py", title="Choques", icon="🚨")
vencidas = st.Page("paginas/vencidas.py", title="Vencidas", icon="📦")

# Página de reportes
reportes = st.Page("paginas/reportes.py", title="Reportes", icon="📊")

# Páginas de administración
exportar = st.Page("paginas/exportar.py", title="Exportar Datos", icon="📤")
subir = st.Page("paginas/subir_excel.py", title="Subir Excel", icon="📥")
editar = st.Page("paginas/editar_clases.py", title="Editar Clases", icon="✏️")

# ============================================
# NAVEGACIÓN
# ============================================
pg = st.navigation({
    "Principal": [inicio, buscar, maestros, salones, materias],
    "Reportes": [reportes],
    "Alertas": [choques, vencidas],
    "Administración": [editar, subir, exportar]
})
pg.run()