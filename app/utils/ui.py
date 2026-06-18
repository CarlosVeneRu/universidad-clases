"""
Componentes visuales reutilizables para mantener consistencia entre páginas.
"""
import streamlit as st


def encabezado(titulo, subtitulo="", icono=""):
    """
    Dibuja un encabezado consistente y centrado para cualquier página.
    
    titulo: el nombre de la página (ej: "Clases")
    subtitulo: texto descriptivo debajo (opcional)
    icono: emoji que acompaña el título (opcional)
    """
    sub_html = ""
    if subtitulo:
        sub_html = (
            f"<div style='font-size:1.05rem; color:#777; margin-top:8px; font-weight:400;'>"
            f"{subtitulo}</div>"
        )
    
    icono_html = f"{icono} " if icono else ""
    
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(90deg, rgba(253,243,243,0) 0%, #FDF3F3 50%, rgba(253,243,243,0) 100%);
            border-top: 3px solid #E30613;
            border-bottom: 3px solid #E30613;
            padding: 24px 16px;
            margin-bottom: 22px;
            text-align: center;
        ">
            <div style="font-size:2.3rem; font-weight:800; color:#1F1F1F; line-height:1.15;">
                {icono_html}{titulo}
            </div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True
    )