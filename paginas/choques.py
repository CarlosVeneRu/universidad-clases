"""
Página de detalle de choques de salones con filtros y visualización tipo horario.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.utils.queries import get_client
from app.utils.ui import encabezado

DIAS_ORDEN = ['LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO', 'DOMINGO']
DIAS_CORTO = {
    'LUNES': 'LUN', 'MARTES': 'MAR', 'MIERCOLES': 'MIÉ',
    'JUEVES': 'JUE', 'VIERNES': 'VIE', 'SABADO': 'SÁB', 'DOMINGO': 'DOM'
}


def main():
    encabezado(
    "Choques de Salones",
    "Clases distintas que comparten el mismo salón al mismo tiempo",
    "🚨"
)
    
    client = get_client()
    
    # ============================================
    # CARGAR DATOS BASE
    # ============================================
    with st.spinner("Detectando choques..."):
        choques_raw = client.rpc("detectar_choques_salon").execute().data
    
    if not choques_raw:
        st.success("✅ ¡Felicidades! No hay choques de salones en el sistema.")
        return
    
    # Agrupar choques por par único (crn_1, crn_2)
    pares_unicos = {}
    for c in choques_raw:
        clave = (c['crn_1'], c['crn_2'], c['periodo'])
        if clave not in pares_unicos:
            pares_unicos[clave] = {
                'crn_1': c['crn_1'],
                'crn_2': c['crn_2'],
                'salon': c['salon'],
                'periodo': c['periodo'],
                'bloque': c['salon'][3] if len(c['salon']) > 3 else '?',
                'dias': []
            }
        pares_unicos[clave]['dias'].append({
            'dia': c['dia'],
            'hora_inicio': str(c['hora_inicio'])[:5],
            'hora_fin': str(c['hora_fin'])[:5]
        })
    
    # Cargar info detallada de TODAS las clases involucradas
    crns_involucrados = set()
    for p in pares_unicos.values():
        crns_involucrados.add(p['crn_1'])
        crns_involucrados.add(p['crn_2'])
    
    clases_info = {}
    if crns_involucrados:
        res = client.table("clases").select(
            "crn, periodo_id, grupo, "
            "materias(id, descripcion), "
            "maestros(nombre_completo), "
            "carreras(nombre_banner, programa_clave, programas(nombre, nivel_codigo))"
        ).in_("crn", list(crns_involucrados)).execute()
        
        for c in res.data:
            clases_info[(c['crn'], c['periodo_id'])] = c
    
    # Cargar TODOS los horarios de los CRNs involucrados
    horarios_de_clases = {}  # (crn, periodo_id) -> [horario1, horario2, ...]
    if crns_involucrados:
        res_h = client.table("horarios").select(
            "crn, periodo_id, dia_semana, hora_inicio, hora_fin, salon_codigo, es_virtual"
        ).in_("crn", list(crns_involucrados)).execute()
        
        for h in res_h.data:
            clave = (h['crn'], h['periodo_id'])
            if clave not in horarios_de_clases:
                horarios_de_clases[clave] = []
            horarios_de_clases[clave].append(h)
    
    # Cargar info de salones (para tipo)
    res_salones = client.table("salones").select("codigo, tipo_uso_descripcion, capacidad").limit(500).execute()
    salones_info = {s['codigo']: s for s in res_salones.data}
    
    # Enriquecer cada choque con info derivada
    for clave, par in pares_unicos.items():
        c1 = clases_info.get((par['crn_1'], par['periodo']), {})
        c2 = clases_info.get((par['crn_2'], par['periodo']), {})
        salon_data = salones_info.get(par['salon'], {})
        
        par['materia_1'] = (c1.get('materias') or {}).get('descripcion', 'N/A')
        par['materia_2'] = (c2.get('materias') or {}).get('descripcion', 'N/A')
        par['maestro_1'] = (c1.get('maestros') or {}).get('nombre_completo', 'Sin asignar')
        par['maestro_2'] = (c2.get('maestros') or {}).get('nombre_completo', 'Sin asignar')
        par['grupo_1'] = c1.get('grupo', 'N/A')
        par['grupo_2'] = c2.get('grupo', 'N/A')
        
        # Programas
        carrera_1 = c1.get('carreras') or {}
        carrera_2 = c2.get('carreras') or {}
        prog_1 = (carrera_1.get('programas') or {}) if carrera_1 else {}
        prog_2 = (carrera_2.get('programas') or {}) if carrera_2 else {}
        
        par['programa_1'] = prog_1.get('nombre') or '(multi)'
        par['programa_2'] = prog_2.get('nombre') or '(multi)'
        par['nivel_1'] = prog_1.get('nivel_codigo') or '—'
        par['nivel_2'] = prog_2.get('nivel_codigo') or '—'
        par['tipo_salon'] = salon_data.get('tipo_uso_descripcion', '?')
        par['capacidad_salon'] = salon_data.get('capacidad', 0)
        
        # Diagnóstico automático REFINADO con las 4 categorías reales
        mismo_maestro = par['maestro_1'] == par['maestro_2'] and par['maestro_1'] != 'Sin asignar'
        misma_materia = par['materia_1'] == par['materia_2']
        
        if mismo_maestro and misma_materia:
            par['diagnostico'] = '✅ Clase espejo verdadera: mismo maestro impartiendo la misma materia bajo 2 CRNs distintos. No requiere acción.'
            par['tipo'] = 'espejo'
        elif mismo_maestro and not misma_materia:
            par['diagnostico'] = '⚠️ ERROR DE PROGRAMACIÓN: el maestro aparece dando 2 materias distintas al mismo tiempo. Imposible físicamente. Revisar con coordinación.'
            par['tipo'] = 'error'
        elif misma_materia and not mismo_maestro:
            par['diagnostico'] = '📋 Misma materia con maestros distintos: posible grupo dividido entre varios docentes.'
            par['tipo'] = 'grupo_dividido'
        else:
            par['diagnostico'] = '🔴 Choque real: dos clases distintas comparten salón. Requiere acción de coordinación.'
            par['tipo'] = 'real'
    
    # ============================================
    # FILTROS
    # ============================================
    st.subheader("🎯 Filtros")
    
    col_f1, col_f2 = st.columns(2)
    
    with col_f1:
        # Filtro por bloque (letra del salón)
        bloques_disponibles = sorted(set(p['bloque'] for p in pares_unicos.values()))
        opciones_bloque = ["📍 Todos los bloques"] + [f"Bloque {b}" for b in bloques_disponibles]
        bloque_sel = st.selectbox("📍 Bloque (letra del salón):", opciones_bloque)
        
        # Filtro por tipo de salón
        tipos_disponibles = sorted(set(p['tipo_salon'] for p in pares_unicos.values() if p['tipo_salon']))
        opciones_tipo = ["🚪 Todos los tipos"] + tipos_disponibles
        tipo_sel = st.selectbox("🚪 Tipo de salón:", opciones_tipo)
    
    with col_f2:
        # Filtro por programa
        programas_disp = set()
        for p in pares_unicos.values():
            if p['programa_1'] != '(multi)':
                programas_disp.add(p['programa_1'])
            if p['programa_2'] != '(multi)':
                programas_disp.add(p['programa_2'])
        opciones_programa = ["📚 Todos los programas"] + sorted(programas_disp) + ["❓ Solo multi-carrera"]
        programa_sel = st.selectbox("📚 Programa:", opciones_programa)
        
        # Filtro por tipo de diagnóstico (más opciones)
        opciones_tipo_diag = [
            "🔍 Todos los tipos",
            "🔴 Solo choques reales (requieren acción)",
            "⚠️ Solo errores de programación",
            "✅ Solo clases espejo verdaderas",
            "📋 Solo grupos divididos",
        ]
        diag_sel = st.selectbox("🔍 Tipo de diagnóstico:", opciones_tipo_diag)
    
    # Aplicar filtros
    choques_filtrados = []
    for clave, par in pares_unicos.items():
        # Filtro de bloque
        if not bloque_sel.startswith("📍 Todos"):
            bloque_buscado = bloque_sel.replace("Bloque ", "")
            if par['bloque'] != bloque_buscado:
                continue
        
        # Filtro de tipo de salón
        if not tipo_sel.startswith("🚪 Todos"):
            if par['tipo_salon'] != tipo_sel:
                continue
        
        # Filtro de programa
        if not programa_sel.startswith("📚 Todos"):
            if programa_sel.startswith("❓"):
                # Solo multi-carrera
                if par['programa_1'] != '(multi)' and par['programa_2'] != '(multi)':
                    continue
            else:
                if par['programa_1'] != programa_sel and par['programa_2'] != programa_sel:
                    continue
        
        # Filtro de diagnóstico (4 categorías ahora)
        if not diag_sel.startswith("🔍 Todos"):
            if diag_sel.startswith("🔴") and par['tipo'] != 'real':
                continue
            if diag_sel.startswith("⚠️") and par['tipo'] != 'error':
                continue
            if diag_sel.startswith("✅") and par['tipo'] != 'espejo':
                continue
            if diag_sel.startswith("📋") and par['tipo'] != 'grupo_dividido':
                continue
        
        choques_filtrados.append(par)
    
    # ============================================
    # MÉTRICAS RESUMEN
    # ============================================
    st.divider()
    st.subheader(f"📊 Resumen ({len(choques_filtrados)} de {len(pares_unicos)} choques)")
    
    if not choques_filtrados:
        st.info("ℹ️ No hay choques que coincidan con los filtros. Cambia los filtros para ver más.")
        return
    
    # Métricas (ahora con 5 categorías)
    total = len(choques_filtrados)
    reales = sum(1 for c in choques_filtrados if c['tipo'] == 'real')
    errores = sum(1 for c in choques_filtrados if c['tipo'] == 'error')
    espejo = sum(1 for c in choques_filtrados if c['tipo'] == 'espejo')
    divididos = sum(1 for c in choques_filtrados if c['tipo'] == 'grupo_dividido')
    
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    with col_m1:
        st.metric("🚨 Total", total)
    with col_m2:
        st.metric("🔴 Choques reales", reales, help="Requieren acción inmediata")
    with col_m3:
        st.metric("⚠️ Errores", errores, help="Maestro dando 2 materias al mismo tiempo (imposible)")
    with col_m4:
        st.metric("✅ Espejos", espejo, help="Misma clase con varios CRNs (normal)")
    with col_m5:
        st.metric("📋 Grupos divididos", divididos, help="Misma materia con varios maestros")
    
    # Distribución por bloque (mini gráfica)
    st.markdown("**Distribución por bloque:**")
    dist_bloque = {}
    for c in choques_filtrados:
        b = c['bloque']
        dist_bloque[b] = dist_bloque.get(b, 0) + 1
    
    cols = st.columns(len(dist_bloque))
    for i, (b, cant) in enumerate(sorted(dist_bloque.items())):
        with cols[i]:
            st.metric(f"📍 {b}", cant)
    
    st.divider()
    
    # ============================================
    # LISTA DETALLADA DE CHOQUES
    # ============================================
    st.subheader("📋 Detalle de cada choque")
    
    # Ordenar por código de salón alfabético + numérico (A001, A002, A015, C000, C003...)
    def clave_orden_salon(codigo):
        """11-A015 -> ('A', 15) para ordenar primero por letra, luego por número."""
        try:
            # Quitar el prefijo del campus (11-)
            sin_prefijo = codigo.split('-', 1)[1] if '-' in codigo else codigo
            # Extraer la primera letra y el primer bloque de dígitos
            letra = ''
            numero_str = ''
            i = 0
            # Saltar dígitos iniciales si hubiera
            while i < len(sin_prefijo) and sin_prefijo[i].isdigit():
                i += 1
            # Capturar la letra
            if i < len(sin_prefijo) and sin_prefijo[i].isalpha():
                letra = sin_prefijo[i].upper()
                i += 1
            # Capturar los dígitos
            while i < len(sin_prefijo) and sin_prefijo[i].isdigit():
                numero_str += sin_prefijo[i]
                i += 1
            numero = int(numero_str) if numero_str else 0
            return (letra, numero, codigo)  # 3er elemento de desempate
        except Exception:
            return ('Z', 999, codigo)  # Casos raros al final
    
    choques_filtrados.sort(key=lambda c: clave_orden_salon(c['salon']))
    
    for i, par in enumerate(choques_filtrados, 1):
        # Color/emoji según tipo (4 categorías)
        if par['tipo'] == 'real':
            emoji_card = "🔴"
            color_borde = "#E53935"  # Rojo
        elif par['tipo'] == 'error':
            emoji_card = "⚠️"
            color_borde = "#FF9800"  # Naranja brillante (alerta)
        elif par['tipo'] == 'espejo':
            emoji_card = "✅"
            color_borde = "#43A047"  # Verde (todo OK)
        else:  # grupo_dividido
            emoji_card = "📋"
            color_borde = "#1976D2"  # Azul
        
        # Construir título del choque
        titulo = f"{emoji_card} **Choque #{i}** · Salón `{par['salon']}` · Periodo {par['periodo']}"
        
        with st.expander(titulo, expanded=False):
            # Card con info del salón
            st.markdown(
                f"<div style='background-color:#F5F5F5; padding:12px; border-radius:8px; border-left:4px solid {color_borde}; margin-bottom:12px;'>"
                f"<b>📍 Salón:</b> {par['salon']} · <b>Tipo:</b> {par['tipo_salon']} · <b>Capacidad:</b> {par['capacidad_salon']}<br>"
                f"<b>Diagnóstico:</b> {par['diagnostico']}"
                f"</div>",
                unsafe_allow_html=True
            )
            
            # Info de las 2 clases en paralelo
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.markdown(f"##### 🅰️ Clase A · CRN {par['crn_1']}")
                st.markdown(f"📚 **Materia:** {par['materia_1']}")
                st.markdown(f"👨‍🏫 **Maestro:** {par['maestro_1']}")
                st.markdown(f"📋 **Grupo:** {par['grupo_1']}")
                st.markdown(f"🎓 **Programa:** {par['programa_1']} ({par['nivel_1']})")
            
            with col_b:
                st.markdown(f"##### 🅱️ Clase B · CRN {par['crn_2']}")
                st.markdown(f"📚 **Materia:** {par['materia_2']}")
                st.markdown(f"👨‍🏫 **Maestro:** {par['maestro_2']}")
                st.markdown(f"📋 **Grupo:** {par['grupo_2']}")
                st.markdown(f"🎓 **Programa:** {par['programa_2']} ({par['nivel_2']})")
            
            st.markdown("---")
            
            # Visualización tipo horario: días y horas del choque + horarios completos
            st.markdown("**📅 Horario completo de ambas clases:**")
            st.caption("⚠️ CHOQUE = donde se solapan · 🅰️ = solo Clase A · 🅱️ = solo Clase B")
            
            # Obtener TODOS los horarios de ambas clases
            horarios_a = horarios_de_clases.get((par['crn_1'], par['periodo']), [])
            horarios_b = horarios_de_clases.get((par['crn_2'], par['periodo']), [])
            
            # Función para determinar si una hora h está dentro de un horario
            def hora_dentro(h_int, horario):
                try:
                    h_ini = int(str(horario['hora_inicio']).split(':')[0])
                    h_fin_str = str(horario['hora_fin'])
                    h_fin = int(h_fin_str.split(':')[0])
                    if int(h_fin_str.split(':')[1]) >= 30:
                        h_fin += 1
                    return h_ini <= h_int < h_fin
                except Exception:
                    return False
            
            # Función para verificar si hay solapamiento (choque) en (dia, hora)
            def es_choque(dia, h_int):
                for d in par['dias']:
                    if d['dia'] == dia:
                        try:
                            h_ini = int(d['hora_inicio'].split(':')[0])
                            h_fin_str = d['hora_fin']
                            h_fin = int(h_fin_str.split(':')[0])
                            if int(h_fin_str.split(':')[1]) >= 30:
                                h_fin += 1
                            if h_ini <= h_int < h_fin:
                                return True
                        except Exception:
                            pass
                return False
            
            # Calcular el rango de horas considerando TODOS los horarios de ambas clases
            todas_horas = []
            for horario_list in [horarios_a, horarios_b]:
                for h in horario_list:
                    try:
                        h_ini = int(str(h['hora_inicio']).split(':')[0])
                        h_fin_str = str(h['hora_fin'])
                        h_fin = int(h_fin_str.split(':')[0])
                        if int(h_fin_str.split(':')[1]) >= 30:
                            h_fin += 1
                        for hh in range(h_ini, h_fin):
                            todas_horas.append(hh)
                    except Exception:
                        pass
            
            if not todas_horas:
                st.info("No hay datos de horario")
                continue
            
            hora_min = min(todas_horas)
            hora_max = max(todas_horas)
            
            # Construir la cuadrícula
            filas_grid = []
            for h in range(hora_min, hora_max + 1):
                fila = {"⏰ Hora": f"{h:02d}:00 - {h:02d}:59"}
                for dia in DIAS_ORDEN:
                    dia_corto = DIAS_CORTO[dia]
                    
                    # ¿Hay choque aquí?
                    if es_choque(dia, h):
                        fila[dia_corto] = "⚠️ CHOQUE"
                    else:
                        # ¿La clase A tiene horario aquí?
                        a_aqui = any(
                            hh['dia_semana'] == dia and hora_dentro(h, hh)
                            for hh in horarios_a
                        )
                        # ¿La clase B tiene horario aquí?
                        b_aqui = any(
                            hh['dia_semana'] == dia and hora_dentro(h, hh)
                            for hh in horarios_b
                        )
                        
                        if a_aqui and b_aqui:
                            fila[dia_corto] = "⚠️ CHOQUE"  # respaldo por si acaso
                        elif a_aqui:
                            fila[dia_corto] = "🅰️ Clase A"
                        elif b_aqui:
                            fila[dia_corto] = "🅱️ Clase B"
                        else:
                            fila[dia_corto] = ""
                filas_grid.append(fila)
            
            df_grid = pd.DataFrame(filas_grid)
            st.dataframe(df_grid, use_container_width=True, hide_index=True, 
                        height=min(38 + (len(df_grid) * 38) + 3, 500))
            
            # Detalle textual de los choques + horarios completos
            col_d1, col_d2, col_d3 = st.columns(3)
            
            with col_d1:
                st.markdown("**⚠️ Momentos de choque:**")
                for d in par['dias']:
                    st.markdown(f"   - **{d['dia'].capitalize()}** {d['hora_inicio']}-{d['hora_fin']}")
            
            with col_d2:
                st.markdown("**🅰️ Horario completo Clase A:**")
                if horarios_a:
                    for h in sorted(horarios_a, key=lambda x: (DIAS_ORDEN.index(x['dia_semana']) if x['dia_semana'] in DIAS_ORDEN else 99, str(x['hora_inicio']))):
                        salon = h.get('salon_codigo') or '🌐 Virtual'
                        dia_c = DIAS_CORTO.get(h['dia_semana'], h['dia_semana'][:3])
                        st.markdown(f"   - **{dia_c}** {str(h['hora_inicio'])[:5]}-{str(h['hora_fin'])[:5]} ({salon})")
                else:
                    st.caption("Sin horarios")
            
            with col_d3:
                st.markdown("**🅱️ Horario completo Clase B:**")
                if horarios_b:
                    for h in sorted(horarios_b, key=lambda x: (DIAS_ORDEN.index(x['dia_semana']) if x['dia_semana'] in DIAS_ORDEN else 99, str(x['hora_inicio']))):
                        salon = h.get('salon_codigo') or '🌐 Virtual'
                        dia_c = DIAS_CORTO.get(h['dia_semana'], h['dia_semana'][:3])
                        st.markdown(f"   - **{dia_c}** {str(h['hora_inicio'])[:5]}-{str(h['hora_fin'])[:5]} ({salon})")
                else:
                    st.caption("Sin horarios")
    
    # ============================================
    # NOTA AL FINAL
    # ============================================
    st.divider()
    st.caption(
        "💡 **Tipos de diagnóstico:**\n\n"
        "- 🔴 **Choque real**: dos clases distintas (materias y maestros distintos) comparten salón. **Requiere acción.**\n"
        "- ⚠️ **Error de programación**: el mismo maestro aparece dando 2 materias distintas al mismo tiempo (imposible físicamente). **Revisar con coordinación.**\n"
        "- ✅ **Clase espejo verdadera**: misma materia y mismo maestro bajo 2 CRNs distintos. Es un caso administrativo normal (ej: la clase se ofrece a varias carreras).\n"
        "- 📋 **Grupo dividido**: misma materia con maestros distintos. Es un caso administrativo normal."
    )


main()