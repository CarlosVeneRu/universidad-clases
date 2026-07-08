"""
Página de Inicio: Dashboard con resumen general del sistema.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from app.utils.queries import get_client
from app.utils.ui import encabezado


# ---------------------------------------------------------------
# Traducción de los códigos de periodo a niveles legibles
# ---------------------------------------------------------------
# Cada periodo trae una "descripción" con códigos tipo "1LX,2LX,LX"
# o "ANC,DNC,NC". Cada código termina con el código del NIVEL
# (LX, NC, PT, L6, LS, B6...). Aquí los traducimos a un nombre claro.
#
# Si algún nombre no es como lo llaman en la UVM, cámbialo aquí.
NIVELES_LEGIBLES = {
    "LX": "Licenciatura Ejecutiva",
    "NC": "Ciencias de la Salud",
    "PT": "Posgrado / Maestría",
    "L6": "Licenciatura",
    "LS": "Licenciatura",
    "B6": "Bachillerato",
    "6B": "Bachillerato",
}

# Programas que pertenecen a cada nivel (tomado de Claves_programas_niveles).
# Si quieres editar nombres o agregar programas, hazlo aquí.
PROGRAMAS_POR_NIVEL = {
    "Bachillerato": [
        "Bachillerato General con enf Bicultural por Compe",
        "Bachillerato General por Competencias",
    ],
    "Licenciatura": [
        "Administración Turística y Hotelera",
        "Administración de Empresas",
        "Administración de Negocios Internacionales",
        "Admón de Empr del Entretenimiento",
        "Arquitectura",
        "Comercio y Logística Internacionales",
        "Comunicación y Medios Digitales",
        "Contaduría Pública y Finanzas",
        "Criminología",
        "Derecho",
        "Diseño Industrial",
        "Diseño Multimedia",
        "Diseño de la Moda e Industria del Vestido",
        "Diseño y Comunicación Gráfica",
        "Finanzas y Banca",
        "Gastronomía Internacional",
        "Ing Biomédica",
        "Ing Civil",
        "Ing Industrial y de Sistemas",
        "Ing Mecatrónica",
        "Ing Mecatrónica con enf Automotriz",
        "Ing en Ciencia de Datos",
        "Ing en Desarrollo de Videojuegos",
        "Ing en Sistemas Computacionales",
        "Lenguas Extranjeras",
        "Merca y Pub en Entornos Digitales",
        "Mercadotecnia",
        "Pedagogía",
        "Psicología",
        "Relaciones Internacionales",
    ],
    "Licenciatura Ejecutiva": [
        "Administración",
        "Contaduría Pública y Finanzas",
        "Derecho",
        "Ing Industrial y de Sistemas",
        "Psicología",
    ],
    "Ciencias de la Salud": [
        "Cirujano Dentista",
        "Enfermería",
        "Fisioterapia",
        "Fisioterapia PM",
        "Ing Biomédica",
        "Ing en Biotecnología",
        "Medicina",
        "Medicina Veterinaria y Zootecnia",
        "Nutrición",
        "Psicología",
        "Químico Farmacéutico Biotecnólogo",
    ],
    "Posgrado / Maestría": [
        "M en Administración de Negocios",
        "M en Admón de Neg con Orient en Finanzas",
        "M en Admón de Neg con Orient en Gest Estrat del Cap Hum",
        "M en Admón de Neg con Orient en Logística",
        "M en Nutrición Deportiva",
    ],
}


def niveles_de_periodo(descripcion: str) -> dict:
    """Devuelve {nombre_legible: [códigos de nivel encontrados]} para un periodo.
    Los códigos reconocidos se agrupan bajo su nombre legible.
    Los NO reconocidos se juntan todos bajo la etiqueta 'Otros'."""
    resultado = {}
    if not descripcion:
        return resultado

    otros = []  # códigos que no reconocimos
    for codigo in descripcion.split(","):
        codigo = codigo.strip().upper()
        if not codigo:
            continue

        clave_encontrada = None
        nombre = None
        for clave, legible in NIVELES_LEGIBLES.items():
            if clave in codigo:
                clave_encontrada = clave
                nombre = legible
                break

        if nombre is None:
            # No reconocido: se junta con los demás desconocidos
            if codigo not in otros:
                otros.append(codigo)
            continue

        resultado.setdefault(nombre, [])
        if clave_encontrada not in resultado[nombre]:
            resultado[nombre].append(clave_encontrada)

    # Al final, agregar los desconocidos como una sola entrada "Otros"
    if otros:
        resultado["Otros"] = otros

    return resultado


def main():
    encabezado(
    "Sistema de Gestión de Clases",
    "Universidad del Valle de México · Campus Querétaro",
    "🎓"
)
    
    try:
        client = get_client()
        
        st.subheader("📊 Resumen general")
        
        col1, col2, col3, col4 = st.columns(4)
        
        # Obtener métricas básicas
        clases_total = client.table("clases").select("crn", count="exact").execute().count
        maestros_total = client.table("maestros").select("clave", count="exact").execute().count
        materias_total = client.table("materias").select("id", count="exact").execute().count
        salones_total = client.table("salones").select("codigo", count="exact").execute().count
        
        # Calcular clases agrupadas
        agrupadas = client.table("clases_agrupadas").select("num_partes").execute().data
        num_grupos_agrupables = len(agrupadas)
        clases_en_grupos = sum(g['num_partes'] for g in agrupadas)
        # "Clases reales" = (total - clases que se agrupan) + (grupos como una sola)
        clases_reales = clases_total - clases_en_grupos + num_grupos_agrupables
        
        with col1:
            st.metric(
                "📝 Clases activas",
                clases_total,
                delta=f"{clases_reales} agrupadas",
                delta_color="off",
                help=f"Total de registros: {clases_total}. Si se agrupan las divididas, son {clases_reales} clases reales."
            )
        
        with col2:
            st.metric("👨‍🏫 Maestros", maestros_total)
        
        with col3:
            st.metric("📚 Materias", materias_total)
        
        with col4:
            st.metric("🚪 Salones físicos", salones_total)
        
        st.divider()
        
        col_izq, col_der = st.columns(2)
        
        with col_izq:
            st.subheader("📅 Periodos académicos")
            periodos = client.table("periodos").select("*").order("id").execute()
            for p in periodos.data:
                niveles = niveles_de_periodo(p.get("descripcion", ""))
                if niveles:
                    partes = [f"{nombre} ({', '.join(codigos)})" for nombre, codigos in niveles.items()]
                    etiqueta = ", ".join(partes)
                else:
                    etiqueta = "—"

                with st.expander(f"**{p['id']}** · {etiqueta}"):
                    # Juntar los programas de todos los niveles del periodo
                    programas = []
                    for nombre in niveles.keys():
                        for prog in PROGRAMAS_POR_NIVEL.get(nombre, []):
                            if prog not in programas:
                                programas.append(prog)

                    if programas:
                        st.caption(f"{len(programas)} programas")
                        for prog in programas:
                            st.markdown(f"- {prog}")
                    else:
                        st.caption("Sin programas asociados.")
        
        with col_der:
            st.subheader("⚠️ Alertas del sistema")
            
            # CHOQUES DE SALONES (clickeable)
            choques_rpc = client.rpc("detectar_choques_salon").execute()
            num_choques = len(set((c['crn_1'], c['crn_2']) for c in choques_rpc.data)) if choques_rpc.data else 0
            
            if num_choques > 0:
                st.warning(f"🚨 {num_choques} choques de salones detectados")
                if st.button("🔍 Ver detalle de choques", key="btn_choques", use_container_width=True):
                    st.switch_page("paginas/choques.py")
            else:
                st.success("✅ Sin choques de salones")
            
            # CLASES VENCIDAS (clickeable)
            pendientes = client.rpc("clases_pendientes_archivar").execute()
            num_vencidas = pendientes.data[0]['total'] if pendientes.data and pendientes.data[0]['total'] > 0 else 0
            
            if num_vencidas > 0:
                st.info(f"📦 {num_vencidas} clases vencidas pendientes de archivar")
                if st.button("📋 Ver clases vencidas", key="btn_vencidas", use_container_width=True):
                    st.switch_page("paginas/vencidas.py")
            else:
                st.success("✅ Sin clases vencidas")
            
            # DATOS INCONSISTENTES
            inconsistentes = client.table("clases").select("crn", count="exact").eq("datos_consistentes", False).execute()
            if inconsistentes.count > 0:
                st.warning(f"⚠️ {inconsistentes.count} clases con datos inconsistentes")
            else:
                st.success("✅ Todos los datos consistentes")
            
            # Info sobre agrupamiento
            if num_grupos_agrupables > 0:
                st.info(
                    f"🔗 **{num_grupos_agrupables} clases** están divididas en **{clases_en_grupos} registros** del sistema. "
                    f"Activa el toggle '🔗 Ver clases agrupadas' en las páginas para consolidarlas."
                )
        
        st.divider()
        
        st.markdown("""
        ### Bienvenido al sistema
        
        Usa el menú lateral izquierdo para navegar entre las secciones.
        """)
    
    except Exception as e:
        st.error(f"❌ Error al conectar con la base de datos: {e}")


main()