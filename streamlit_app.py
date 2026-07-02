"""
Punto de entrada del Sistema de Gestión de Clases UVM.
Login + navegación según el rol del usuario.
"""
import sys
import base64
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import streamlit as st

from app.utils.queries import get_client

st.set_page_config(
    page_title="Gestor de Clases UVM",
    page_icon="assets/uvm_logo.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# LOGO UVM en el header del sidebar (vía CSS)
# ============================================
def _logo_base64(ruta):
    with open(ruta, "rb") as f:
        return base64.b64encode(f.read()).decode()

_logo_b64 = _logo_base64("assets/uvm_logo.png")

st.markdown(f"""
    <style>
        [data-testid="stSidebarHeader"] {{
            background-image: url("data:image/png;base64,{_logo_b64}");
            background-repeat: no-repeat;
            background-position: center;
            background-size: contain;
            height: 120px;
            margin: 0.5rem 1rem 0.5rem 1rem;
        }}
        [data-testid="stLogo"] {{ display: none; }}
        [data-testid="stMarkdownContainer"] p {{ font-size: 1.25rem; line-height: 1.65; }}
        [data-testid="stMarkdownContainer"] li {{ font-size: 1.25rem; line-height: 1.65; }}
        [data-testid="stWidgetLabel"] label p {{ font-size: 1.15rem; }}
        [data-testid="stRadio"] label p,
        [data-baseweb="tab"] {{ font-size: 1.12rem; }}
        [data-testid="stCaptionContainer"] p {{ font-size: 1.0rem; }}
    </style>
""", unsafe_allow_html=True)


# ============================================
# LOGIN / LOGOUT
# ============================================
def pantalla_login():
    col_i, col_c, col_d = st.columns([1, 1.3, 1])
    with col_c:
        st.markdown("<div style='height:5vh'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<div style='text-align:center'>"
            f"<img src='data:image/png;base64,{_logo_b64}' style='max-width:220px; width:60%'></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<h2 style='text-align:center; margin-bottom:0'>Sistema de Gestión de Clases</h2>"
            "<p style='text-align:center; color:#777; margin-top:4px'>"
            "Universidad del Valle de México · Campus Querétaro</p>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:2vh'></div>", unsafe_allow_html=True)

        usuario = st.text_input("Usuario", key="login_usuario", placeholder="Tu usuario")
        password = st.text_input("Contraseña", type="password", key="login_password", placeholder="Tu contraseña")
        entrar = st.button("Entrar", type="primary", use_container_width=True)

        # Pista al navegador: es un login, no un registro (evita el popup de "crear contraseña")
        st.components.v1.html(
            """
            <script>
            const d = window.parent.document;
            d.querySelectorAll('input[type=password]').forEach(function(el){
                el.setAttribute('autocomplete','current-password');
            });
            const u = d.querySelector('input[aria-label="Usuario"]');
            if (u) { u.setAttribute('autocomplete','username'); }
            </script>
            """,
            height=0,
        )

        if entrar:
            if not usuario or not password:
                st.error("Escribe tu usuario y contraseña.")
                return
            try:
                client = get_client()
                res = client.rpc("verificar_login",
                                 {"p_usuario": usuario, "p_password": password}).execute().data
                if res:
                    u = res[0]
                    st.session_state["logged_in"] = True
                    st.session_state["usuario"] = u["usuario"]
                    st.session_state["nombre"] = u["nombre"]
                    st.session_state["rol"] = u["rol"]
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
            except Exception as e:
                st.error(f"No se pudo verificar el login: {e}")


def cerrar_sesion():
    for k in ["logged_in", "usuario", "nombre", "rol"]:
        st.session_state.pop(k, None)
    st.rerun()


# ============================================
# DEFINIR PÁGINAS
# ============================================
inicio = st.Page("paginas/inicio.py", title="Inicio", icon="🏠", default=True)
buscar = st.Page("paginas/buscar_clases.py", title="Clases", icon="🔍")
maestros = st.Page("paginas/maestros.py", title="Maestros", icon="👨‍🏫")
salones = st.Page("paginas/salones.py", title="Salones", icon="🚪")
materias = st.Page("paginas/materias.py", title="Materias", icon="📚")
choques = st.Page("paginas/choques.py", title="Choques", icon="🚨")
vencidas = st.Page("paginas/vencidas.py", title="Vencidas", icon="📦")
reportes = st.Page("paginas/reportes.py", title="Reportes", icon="📊")
exportar = st.Page("paginas/exportar.py", title="Exportar Datos", icon="📤")
subir = st.Page("paginas/subir_excel.py", title="Subir Excel", icon="📥")
editar = st.Page("paginas/editar_clases.py", title="Editar Clases", icon="✏️")
agregar = st.Page("paginas/agregar_clase.py", title="Agregar Clase", icon="➕")
gestionar = st.Page("paginas/archivar_eliminar.py", title="Archivar / Eliminar", icon="🗑️")


# ============================================
# NAVEGACIÓN: primero login, luego menú según rol
# ============================================
if not st.session_state.get("logged_in"):
    # Sin sesión: solo se ve la pantalla de login
    st.navigation([st.Page(pantalla_login, title="Iniciar sesión", icon="🔒")]).run()
else:
    rol = st.session_state.get("rol", "viewer")

    # Estas secciones las ven TODOS los roles
    menu = {
        "Principal": [inicio, buscar, maestros, salones, materias],
        "Reportes": [reportes, exportar],
        "Alertas": [choques, vencidas],
    }

    # Solo admin y moderador pueden modificar datos
    if rol in ("admin", "moderador"):
        administracion = [editar, agregar, gestionar]
        if rol == "admin":
            administracion.append(subir)  # Subir Excel: solo admin
        menu["Administración"] = administracion

    pg = st.navigation(menu)

    # Datos del usuario + botón de salir, abajo en el sidebar
    with st.sidebar:
        st.divider()
        st.caption(f"👤 {st.session_state.get('nombre', '')} · rol: {rol}")
        if st.button("🔒 Cerrar sesión", use_container_width=True):
            cerrar_sesion()

    pg.run()