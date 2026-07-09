"""
Pagina de detalle de choques de salones con filtros y visualizacion.
Choques del mismo salon/dia/hora se agrupan en una sola tarjeta.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.utils.queries import get_client
from app.utils.ui import encabezado

DIAS_ORDEN = ["LUNES","MARTES","MIERCOLES","JUEVES","VIERNES","SABADO","DOMINGO"]
DIAS_CORTO = {"LUNES":"LUN","MARTES":"MAR","MIERCOLES":"MIÉ","JUEVES":"JUE","VIERNES":"VIE","SABADO":"SÁB","DOMINGO":"DOM"}
ETIQUETAS_CLASE = ["🅰️","🅱️","🅲","🅳","🅴","🅵","🅶","🅷"]


def emoji_clase(idx):
    """Devuelve una etiqueta HTML con la letra idx en un cuadrito rojo."""
    letra = chr(ord("A") + idx)
    return (
        f"<span style='background-color:#E53935; color:white; "
        f"padding:2px 8px; border-radius:4px; font-weight:bold; "
        f"font-family:sans-serif; font-size:0.9em;'>{letra}</span>"
    )


def main():
    encabezado("Choques de Salones", "Clases distintas que comparten el mismo salon", "🚨")
    client = get_client()
    incluir_terminadas = False

    with st.spinner("Detectando choques..."):
        choques_raw = client.rpc("detectar_choques_salon", {"incluir_terminadas": incluir_terminadas}).execute().data

    if not choques_raw:
        st.success("✅ No hay choques de salones en el sistema.")
        return

    pares_unicos = {}
    for c in choques_raw:
        clave = (c["crn_1"], c["crn_2"], c["periodo"])
        if clave not in pares_unicos:
            pares_unicos[clave] = {
                "crn_1": c["crn_1"], "crn_2": c["crn_2"],
                "salon": c["salon"], "periodo": c["periodo"],
                "bloque": c["salon"][3] if len(c["salon"]) > 3 else "?",
                "dias": []
            }
        pares_unicos[clave]["dias"].append({
            "dia": c["dia"],
            "hora_inicio": str(c["hora_inicio"])[:5],
            "hora_fin": str(c["hora_fin"])[:5]
        })

    crns_involucrados = set()
    for p in pares_unicos.values():
        crns_involucrados.add(p["crn_1"])
        crns_involucrados.add(p["crn_2"])

    clases_info = {}
    if crns_involucrados:
        res = client.table("clases").select(
            "crn, periodo_id, grupo, fecha_inicio, fecha_fin, clave_periodo, "
            "materias(id, descripcion), maestros(nombre_completo), "
            "carreras(nombre_banner, programa_clave, programas(nombre, nivel_codigo))"
        ).in_("crn", list(crns_involucrados)).execute()
        for c in res.data:
            clases_info[(c["crn"], c["periodo_id"])] = c

    horarios_de_clases = {}
    if crns_involucrados:
        res_h = client.table("horarios").select(
            "crn, periodo_id, dia_semana, hora_inicio, hora_fin, salon_codigo, es_virtual"
        ).in_("crn", list(crns_involucrados)).execute()
        for h in res_h.data:
            clave = (h["crn"], h["periodo_id"])
            horarios_de_clases.setdefault(clave, []).append(h)

    res_salones = client.table("salones").select("codigo, tipo_uso_descripcion, capacidad").limit(500).execute()
    salones_info = {s["codigo"]: s for s in res_salones.data}

    for clave, par in pares_unicos.items():
        c1 = clases_info.get((par["crn_1"], par["periodo"]), {})
        c2 = clases_info.get((par["crn_2"], par["periodo"]), {})
        salon_data = salones_info.get(par["salon"], {})

        par["materia_1"] = (c1.get("materias") or {}).get("descripcion", "N/A")
        par["materia_2"] = (c2.get("materias") or {}).get("descripcion", "N/A")
        par["maestro_1"] = (c1.get("maestros") or {}).get("nombre_completo", "Sin asignar")
        par["maestro_2"] = (c2.get("maestros") or {}).get("nombre_completo", "Sin asignar")

        c_1 = c1.get("carreras") or {}
        c_2 = c2.get("carreras") or {}
        prog_1 = (c_1.get("programas") or {}) if c_1 else {}
        prog_2 = (c_2.get("programas") or {}) if c_2 else {}
        par["programa_1"] = prog_1.get("nombre") or "(multi)"
        par["programa_2"] = prog_2.get("nombre") or "(multi)"
        par["tipo_salon"] = salon_data.get("tipo_uso_descripcion", "?")
        par["capacidad_salon"] = salon_data.get("capacidad", 0)

        try:
            clas_bd = client.rpc("clasificar_choque", {"p_crn_1": par["crn_1"], "p_crn_2": par["crn_2"], "p_periodo": par["periodo"]}).execute().data
        except Exception:
            clas_bd = None

        mismo_maestro = par["maestro_1"] == par["maestro_2"] and par["maestro_1"] != "Sin asignar"
        misma_materia = par["materia_1"] == par["materia_2"]

        if clas_bd == "espejo":
            par["diagnostico"] = "🪞 Clase espejo: misma materia, salon, horario y fechas."
            par["tipo"] = "espejo"
        elif clas_bd == "posible_espejo":
            par["diagnostico"] = "🔎 Posible espejo: misma materia con diferencia menor."
            par["tipo"] = "posible_espejo"
        elif mismo_maestro and not misma_materia:
            par["diagnostico"] = "⚠️ ERROR: el maestro aparece dando 2 materias al mismo tiempo."
            par["tipo"] = "error"
        elif misma_materia and not mismo_maestro:
            par["diagnostico"] = "📋 Misma materia con maestros distintos: posible grupo dividido."
            par["tipo"] = "grupo_dividido"
        else:
            par["diagnostico"] = "🔴 Choque real: dos clases distintas comparten salon."
            par["tipo"] = "real"

    st.subheader("🎯 Filtros")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        bloques_disponibles = sorted(set(p["bloque"] for p in pares_unicos.values()))
        opciones_bloque = ["📍 Todos los edificios"] + [f"Edificio {b}" for b in bloques_disponibles]
        bloque_sel = st.selectbox("📍 Edificio:", opciones_bloque)
        tipos_disponibles = sorted(set(p["tipo_salon"] for p in pares_unicos.values() if p["tipo_salon"]))
        opciones_tipo = ["🚪 Todos los tipos"] + tipos_disponibles
        tipo_sel = st.selectbox("🚪 Tipo de salon:", opciones_tipo)
    with col_f2:
        programas_disp = set()
        for p in pares_unicos.values():
            if p["programa_1"] != "(multi)":
                programas_disp.add(p["programa_1"])
            if p["programa_2"] != "(multi)":
                programas_disp.add(p["programa_2"])
        opciones_programa = ["📚 Todos los programas"] + sorted(programas_disp) + ["❓ Solo multi-carrera"]
        programa_sel = st.selectbox("📚 Programa:", opciones_programa)

    choques_filtrados = []
    for clave, par in pares_unicos.items():
        if not bloque_sel.startswith("📍 Todos"):
            bloque_buscado = bloque_sel.replace("Edificio ", "")
            if par["bloque"] != bloque_buscado:
                continue
        if not tipo_sel.startswith("🚪 Todos"):
            if par["tipo_salon"] != tipo_sel:
                continue
        if not programa_sel.startswith("📚 Todos"):
            if programa_sel.startswith("❓"):
                if par["programa_1"] != "(multi)" and par["programa_2"] != "(multi)":
                    continue
            else:
                if par["programa_1"] != programa_sel and par["programa_2"] != programa_sel:
                    continue
        choques_filtrados.append(par)

    st.divider()
    if not choques_filtrados:
        st.info("No hay choques que coincidan con los filtros.")
        return


    st.divider()

    def clave_orden_salon(codigo):
        try:
            sin_prefijo = codigo.split("-", 1)[1] if "-" in codigo else codigo
            letra = ""
            numero_str = ""
            i = 0
            while i < len(sin_prefijo) and sin_prefijo[i].isdigit():
                i += 1
            if i < len(sin_prefijo) and sin_prefijo[i].isalpha():
                letra = sin_prefijo[i].upper()
                i += 1
            while i < len(sin_prefijo) and sin_prefijo[i].isdigit():
                numero_str += sin_prefijo[i]
                i += 1
            numero = int(numero_str) if numero_str else 0
            return (letra, numero, codigo)
        except Exception:
            return ("Z", 999, codigo)

    def agrupar_pares(pares):
        padre = {}
        def find(x):
            while padre.get(x, x) != x:
                padre[x] = padre.get(padre.get(x, x), padre.get(x, x))
                x = padre[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                padre[ra] = rb
        for p in pares:
            k1 = (p["salon"], p["periodo"], p["crn_1"])
            k2 = (p["salon"], p["periodo"], p["crn_2"])
            padre.setdefault(k1, k1)
            padre.setdefault(k2, k2)
            union(k1, k2)

        grupos = {}
        for p in pares:
            raiz = find((p["salon"], p["periodo"], p["crn_1"]))
            grupos.setdefault(raiz, []).append(p)

        conflictos = []
        for raiz, pares_del_grupo in grupos.items():
            crns_unicas = []
            for p in pares_del_grupo:
                for c in [p["crn_1"], p["crn_2"]]:
                    if c not in crns_unicas:
                        crns_unicas.append(c)
            crns_unicas.sort()

            todos_dias = []
            vistos = set()
            for p in pares_del_grupo:
                for d in p["dias"]:
                    k = (d["dia"], d["hora_inicio"], d["hora_fin"])
                    if k not in vistos:
                        vistos.add(k)
                        todos_dias.append(d)

            tipos_pares = [p["tipo"] for p in pares_del_grupo]
            if "real" in tipos_pares: tipo_conf = "real"
            elif "error" in tipos_pares: tipo_conf = "error"
            elif "grupo_dividido" in tipos_pares: tipo_conf = "grupo_dividido"
            elif "posible_espejo" in tipos_pares: tipo_conf = "posible_espejo"
            else: tipo_conf = "espejo"

            if len(crns_unicas) > 2:
                diagnostico = f"🚨 Conflicto multiple: {len(crns_unicas)} clases pidiendo el mismo salon/hora."
            else:
                diagnostico = pares_del_grupo[0]["diagnostico"]

            conflictos.append({
                "salon": pares_del_grupo[0]["salon"],
                "periodo": pares_del_grupo[0]["periodo"],
                "tipo_salon": pares_del_grupo[0]["tipo_salon"],
                "capacidad_salon": pares_del_grupo[0]["capacidad_salon"],
                "bloque": pares_del_grupo[0]["bloque"],
                "crns": crns_unicas,
                "dias": todos_dias,
                "tipo": tipo_conf,
                "diagnostico": diagnostico,
            })
        return conflictos

    conflictos = agrupar_pares(choques_filtrados)
    conflictos_accion = [c for c in conflictos if c["tipo"] in ("real", "error", "grupo_dividido")]
    conflictos_espejos = [c for c in conflictos if c["tipo"] in ("espejo", "posible_espejo")]
    conflictos_accion.sort(key=lambda c: clave_orden_salon(c["salon"]))
    conflictos_espejos.sort(key=lambda c: clave_orden_salon(c["salon"]))
    
    # Métricas basadas en conflictos agrupados (no en pares)
    n_reales = sum(1 for c in conflictos_accion if c["tipo"] == "real")
    n_errores = sum(1 for c in conflictos_accion if c["tipo"] == "error")
    n_espejo = sum(1 for c in conflictos_espejos if c["tipo"] == "espejo")
    n_posibles = sum(1 for c in conflictos_espejos if c["tipo"] == "posible_espejo")

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1: st.metric("🔴 Reales", n_reales)
    with col_m2: st.metric("⚠️ Errores", n_errores)
    with col_m3: st.metric("🪞 Espejos", n_espejo)
    with col_m4: st.metric("🔎 Posibles espejos", n_posibles)

    st.divider()

    def datos_clase(crn, periodo):
        c = clases_info.get((crn, periodo), {})
        carrera = c.get("carreras") or {}
        prog = (carrera.get("programas") or {}) if carrera else {}
        return {
            "crn": crn,
            "materia": (c.get("materias") or {}).get("descripcion", "N/A"),
            "maestro": (c.get("maestros") or {}).get("nombre_completo", "Sin asignar"),
            "grupo": c.get("grupo", "N/A"),
            "programa": prog.get("nombre") or "(multi)",
            "nivel": prog.get("nivel_codigo") or "—",
            "nivel_periodo": (c.get("clave_periodo") or "—").upper(),
            "fecha_inicio": c.get("fecha_inicio") or "—",
            "fecha_fin": c.get("fecha_fin") or "—",
        }

    def dibujar_bloque_clase(datos, emoji, letra):
        st.markdown(f"##### {emoji} Clase {letra} · CRN {datos['crn']}", unsafe_allow_html=True)
        st.markdown(f"📚 **Materia:** {datos['materia']}")
        st.markdown(f"👨‍🏫 **Maestro:** {datos['maestro']}")
        st.markdown(f"📋 **Grupo:** {datos['grupo']}")
        st.markdown(f"🎓 **Programa:** {datos['programa']} ({datos['nivel']})")
        st.markdown(f"🏷️ **Nivel del periodo:** {datos['nivel_periodo']}")
        st.markdown(f"📅 **Fechas:** {datos['fecha_inicio']} → {datos['fecha_fin']}")

    def dibujar_grid_clases(crns, periodo):
        for i in range(0, len(crns), 2):
            if i > 0:
                st.markdown("<hr style='margin:8px 0; border:none; border-top:1px solid #DDD;'>",
                            unsafe_allow_html=True)
            col_izq, col_der = st.columns(2)
            datos_izq = datos_clase(crns[i], periodo)
            letra_izq = chr(ord("A") + i)
            emoji_izq = emoji_clase(i)
            with col_izq:
                dibujar_bloque_clase(datos_izq, emoji_izq, letra_izq)
            if i + 1 < len(crns):
                datos_der = datos_clase(crns[i+1], periodo)
                letra_der = chr(ord("A") + i + 1)
                emoji_der = emoji_clase(i+1)
                with col_der:
                    dibujar_bloque_clase(datos_der, emoji_der, letra_der)

    def hora_dentro(h_int, horario):
        try:
            h_ini = int(str(horario["hora_inicio"]).split(":")[0])
            h_fin_str = str(horario["hora_fin"])
            h_fin = int(h_fin_str.split(":")[0])
            if int(h_fin_str.split(":")[1]) >= 30:
                h_fin += 1
            return h_ini <= h_int < h_fin
        except Exception:
            return False

    def dibujar_cuadricula(conf):
        crns = conf["crns"]
        periodo = conf["periodo"]
        horarios_por_crn = {}
        todas_horas = []
        for crn in crns:
            hs = horarios_de_clases.get((crn, periodo), [])
            horarios_por_crn[crn] = hs
            for h in hs:
                try:
                    h_ini = int(str(h["hora_inicio"]).split(":")[0])
                    h_fin_str = str(h["hora_fin"])
                    h_fin = int(h_fin_str.split(":")[0])
                    if int(h_fin_str.split(":")[1]) >= 30:
                        h_fin += 1
                    for hh in range(h_ini, h_fin):
                        todas_horas.append(hh)
                except Exception:
                    pass
        if not todas_horas:
            st.info("No hay datos de horario")
            return
        hora_min = min(todas_horas)
        hora_max = max(todas_horas)
        filas_grid = []
        for h in range(hora_min, hora_max + 1):
            fila = {"⏰ Hora": f"{h:02d}:00 - {h:02d}:59"}
            for dia in DIAS_ORDEN:
                dia_corto = DIAS_CORTO[dia]
                clases_aqui = []
                for idx, crn in enumerate(crns):
                    for hh in horarios_por_crn[crn]:
                        if hh["dia_semana"] == dia and hora_dentro(h, hh):
                            if hh.get("salon_codigo") == conf["salon"]:
                                clases_aqui.append(idx)
                                break
                if len(clases_aqui) > 1:
                    fila[dia_corto] = "⚠️ CHOQUE"
                elif len(clases_aqui) == 1:
                    idx = clases_aqui[0]
                    letra = chr(ord("A") + idx)
                    fila[dia_corto] = f"{letra}"
                else:
                    algo = False
                    for idx, crn in enumerate(crns):
                        for hh in horarios_por_crn[crn]:
                            if hh["dia_semana"] == dia and hora_dentro(h, hh):
                                algo = True
                                break
                        if algo:
                            break
                    fila[dia_corto] = "•" if algo else ""
            filas_grid.append(fila)
        df_grid = pd.DataFrame(filas_grid)
        st.dataframe(df_grid, use_container_width=True, hide_index=True,
                     height=min(38 + (len(df_grid) * 38) + 3, 500))

    def dibujar_conflicto(conf, numero):
        colores = {
            "real": ("🔴", "#E53935"),
            "error": ("⚠️", "#FF9800"),
            "espejo": ("🪞", "#43A047"),
            "posible_espejo": ("🔎", "#FBC02D"),
            "grupo_dividido": ("📋", "#1976D2"),
        }
        emoji_card, color_borde = colores.get(conf["tipo"], ("🔴", "#E53935"))

        titulo = f"{emoji_card} **Choque #{numero}** · Salon `{conf['salon']}` · Periodo {conf['periodo']} · {len(conf['crns'])} clases"

        with st.expander(titulo, expanded=False):
            st.markdown(
                f"<div style='background-color:#F5F5F5; padding:12px; border-radius:8px; "
                f"border-left:4px solid {color_borde}; margin-bottom:12px;'>"
                f"<b>📍 Salon:</b> {conf['salon']} · <b>Tipo:</b> {conf['tipo_salon']} · "
                f"<b>Capacidad:</b> {conf['capacidad_salon']}<br>"
                f"<b>Diagnostico:</b> {conf['diagnostico']}"
                f"</div>",
                unsafe_allow_html=True
            )
            dibujar_grid_clases(conf["crns"], conf["periodo"])
            st.markdown("---")
            st.markdown("**📅 Horario semanal en el salon:**")
            leyenda = " · ".join(
                f"{emoji_clase(i)} = Clase {chr(ord('A')+i)}"
                for i in range(len(conf["crns"]))
            )
            st.markdown(f"⚠️ CHOQUE = 2+ clases al mismo tiempo · {leyenda}", unsafe_allow_html=True)
            dibujar_cuadricula(conf)
            st.markdown("---")
            st.markdown("**⚠️ Momentos de choque:**")
            dias_ordenados = sorted(
                conf["dias"],
                key=lambda d: (
                    DIAS_ORDEN.index(d["dia"]) if d["dia"] in DIAS_ORDEN else 99,
                    d["hora_inicio"]
                )
            )
            for d in dias_ordenados:
                st.markdown(f"   - **{d['dia'].capitalize()}** {d['hora_inicio']}-{d['hora_fin']}")
            st.markdown("**📆 Horario completo por clase:**")
            for i in range(0, len(conf["crns"]), 2):
                col_izq, col_der = st.columns(2)
                for offset, col in [(0, col_izq), (1, col_der)]:
                    idx = i + offset
                    if idx >= len(conf["crns"]):
                        continue
                    crn = conf["crns"][idx]
                    emoji = emoji_clase(idx)
                    letra = chr(ord("A") + idx)
                    with col:
                        st.markdown(f"{emoji} **Clase {letra} (CRN {crn}):**", unsafe_allow_html=True)
                        hs = horarios_de_clases.get((crn, conf["periodo"]), [])
                        if hs:
                            for h in sorted(hs, key=lambda x: (DIAS_ORDEN.index(x["dia_semana"]) if x["dia_semana"] in DIAS_ORDEN else 99, str(x["hora_inicio"]))):
                                salon = h.get("salon_codigo") or "🌐 Virtual"
                                dia_c = DIAS_CORTO.get(h["dia_semana"], h["dia_semana"][:3])
                                st.markdown(f"   - **{dia_c}** {str(h['hora_inicio'])[:5]}-{str(h['hora_fin'])[:5]} ({salon})")
                        else:
                            st.caption("Sin horarios")

    st.subheader(f"📋 Choques que requieren revision ({len(conflictos_accion)})")
    if not conflictos_accion:
        st.success("✅ No hay choques que requieran accion de coordinacion.")
    else:
        for i, conf in enumerate(conflictos_accion, 1):
            dibujar_conflicto(conf, i)

    st.divider()
    st.subheader(f"🪞 Clases espejo y posibles espejos ({len(conflictos_espejos)})")
    st.caption("Son grupos donde varias CRN corresponden a la misma clase. Normalmente se puede archivar una.")
    if not conflictos_espejos:
        st.info("No hay espejos detectados.")
    else:
        for i, conf in enumerate(conflictos_espejos, 1):
            dibujar_conflicto(conf, i)


main()