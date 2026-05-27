"""
Página de detalle de choques de salones.
Muestra todos los choques reales detectados en el sistema.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.utils.queries import get_client


def main():
    st.title("🚨 Choques de Salones")
    st.markdown("Clases distintas que comparten el mismo salón al mismo tiempo")
    st.divider()
    
    client = get_client()
    
    with st.spinner("Detectando choques..."):
        choques_raw = client.rpc("detectar_choques_salon").execute().data
    
    if not choques_raw:
        st.success("✅ ¡Felicidades! No hay choques de salones en el sistema.")
        return
    
    # Agrupar choques por par único (crn_1, crn_2)
    pares_unicos = {}
    for c in choques_raw:
        clave = (c['crn_1'], c['crn_2'])
        if clave not in pares_unicos:
            pares_unicos[clave] = {
                'crn_1': c['crn_1'],
                'crn_2': c['crn_2'],
                'salon': c['salon'],
                'periodo': c.get('periodo'),
                'dias': []
            }
        pares_unicos[clave]['dias'].append({
            'dia': c['dia'],
            'hora_inicio': c['hora_inicio'],
            'hora_fin': c['hora_fin']
        })
    
    st.warning(f"⚠️ Se detectaron **{len(pares_unicos)} choques** (pares únicos de clases en conflicto)")
    
    st.divider()
    
    # Cargar info detallada de cada CRN involucrado
    crns_involucrados = set()
    for p in pares_unicos.values():
        crns_involucrados.add(p['crn_1'])
        crns_involucrados.add(p['crn_2'])
    
    # Consultar info de las clases en bloque
    clases_info = {}
    if crns_involucrados:
        res = client.table("clases").select(
            "crn, periodo_id, grupo, "
            "materias(descripcion), "
            "maestros(nombre_completo)"
        ).in_("crn", list(crns_involucrados)).execute()
        
        for c in res.data:
            clases_info[(c['crn'], c['periodo_id'])] = c
    
    # Mostrar cada choque con detalle
    for i, par in enumerate(pares_unicos.values(), 1):
        c1 = clases_info.get((par['crn_1'], par['periodo']), {})
        c2 = clases_info.get((par['crn_2'], par['periodo']), {})
        
        materia1 = (c1.get('materias') or {}).get('descripcion', 'N/A')
        materia2 = (c2.get('materias') or {}).get('descripcion', 'N/A')
        maestro1 = (c1.get('maestros') or {}).get('nombre_completo', 'Sin asignar')
        maestro2 = (c2.get('maestros') or {}).get('nombre_completo', 'Sin asignar')
        
        # Diagnóstico del choque
        if maestro1 == maestro2 and maestro1 != 'Sin asignar':
            diagnostico = "💡 Mismo maestro — podría ser una clase espejo administrativa"
            color = "info"
        elif materia1 == materia2:
            diagnostico = "💡 Misma materia — podría ser un grupo dividido"
            color = "info"
        else:
            diagnostico = "🔴 Choque real: dos clases distintas pidiendo el mismo salón"
            color = "error"
        
        with st.expander(f"⚠️ Choque #{i}: {par['salon']} · Periodo {par['periodo']} (CRN {par['crn_1']} vs CRN {par['crn_2']})"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"### CRN {par['crn_1']}")
                st.markdown(f"📚 **Materia:** {materia1}")
                st.markdown(f"👨‍🏫 **Maestro:** {maestro1}")
                st.markdown(f"📋 **Grupo:** {c1.get('grupo', 'N/A')}")
            
            with col2:
                st.markdown(f"### CRN {par['crn_2']}")
                st.markdown(f"📚 **Materia:** {materia2}")
                st.markdown(f"👨‍🏫 **Maestro:** {maestro2}")
                st.markdown(f"📋 **Grupo:** {c2.get('grupo', 'N/A')}")
            
            st.markdown(f"**Salón en conflicto:** `{par['salon']}`")
            
            # Días del choque
            st.markdown("**Días y horas del choque:**")
            for d in par['dias']:
                hora_ini = str(d['hora_inicio'])[:5]
                hora_fin = str(d['hora_fin'])[:5]
                st.markdown(f"   - {d['dia']}: {hora_ini} - {hora_fin}")
            
            # Diagnóstico
            if color == "info":
                st.info(diagnostico)
            else:
                st.error(diagnostico)
    
    # Resumen al final
    st.divider()
    st.caption(f"💡 Tip: Los choques con 'mismo maestro' o 'misma materia' suelen ser agrupamientos administrativos. Los 'choques reales' son los que requieren acción.")


main()