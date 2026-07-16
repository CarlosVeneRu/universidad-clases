"""
Página de búsqueda avanzada de clases.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date
import streamlit as st
import pandas as pd
from app.utils.ui import encabezado
from app.utils.queries import (
    get_client, cargar_periodos, buscar_maestros, buscar_materias,
    cargar_programas, buscar_archivadas_como_activas
)

from app.utils.horarios import construir_horario_cuadricula

NIVELES_LEGIBLES = {
    "LX": "Licenciatura Ejecutiva", "NC": "Ciencias de la Salud",
    "PT": "Posgrado / Maestría", "L6": "Licenciatura", "LS": "Licenciatura",
    "B6": "Bachillerato", "6B": "Bachillerato",
}


def etiqueta_periodo(periodo_id, descripcion):
    """Devuelve '202630 · Licenciatura Ejecutiva (LX)'."""
    codigos = []
    for clave in str(descripcion or "").split(","):
        clave = clave.strip().upper()
        for cod in NIVELES_LEGIBLES:
            if cod in clave and cod not in codigos:
                codigos.append(cod)
                break
    if not codigos:
        return str(periodo_id)
    return f"{periodo_id} · {NIVELES_LEGIBLES[codigos[0]]} ({', '.join(sorted(codigos))})"


def _mostrar_detalle_clase(c):
    """Muestra los datos y el horario (cuadrícula) de una clase seleccionada."""
    client = get_client()
    crns = c.get("crns") or [c.get("crn")]
    periodo = c["periodo_id"]
    materia = (c.get("materias") or {}).get("descripcion") or "(multi)"
    maestro = (c.get("maestros") or {}).get("nombre_completo") or "Sin asignar"
    carrera = c.get("carreras") or {}
    programa = (carrera.get("programas") or {}).get("nombre") or "(multi-carrera)"

    st.markdown(f"### 📘 {materia}")
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**CRN(s):** {', '.join(str(x) for x in crns)}")
    c1.markdown(f"**Periodo:** {periodo}")
    c2.markdown(f"**Maestro:** {maestro}")
    c2.markdown(f"**Programa:** {programa}")
    c3.markdown(f"**Inscritos:** {c.get('inscritos', 0)} / {c.get('capacidad_materia', 0)}")
    c3.markdown(f"**Fechas:** {c.get('fecha_inicio') or '?'} → {c.get('fecha_fin') or '?'}")

    # Si es archivada, usar el snapshot JSON en vez de la tabla horarios
    if c.get("_archivada") and c.get("horarios_snapshot"):
        hors = list(c["horarios_snapshot"]) if isinstance(c["horarios_snapshot"], list) else []
        for h in hors:
            h["crn"] = c.get("crn")
    else:
        hors = (client.table("horarios")
                .select("dia_semana,hora_inicio,hora_fin,salon_codigo,es_virtual,crn")
                .in_("crn", crns).eq("periodo_id", periodo).execute().data)
    if not hors:
        st.info("Esta clase no tiene horario asignado." + (" (Archivada)" if c.get("_archivada") else ""))
        return
    for h in hors:
        h["materia_nombre"] = materia
    df_grid, _ = construir_horario_cuadricula(hors, etiqueta_extra="salon")
    if df_grid is not None and not df_grid.empty:
        st.markdown("**Horario semanal:**")
        st.dataframe(df_grid, use_container_width=True, hide_index=True,
                     height=38 + len(df_grid) * 38 + 3)


def agrupar_resultados(resultados):
    """
    Toma los resultados de la búsqueda y agrupa las clases que probablemente son 'la misma'.
    Criterio: misma materia + maestro + periodo + grupo_base (quitando última letra).
    """
    import re

    grupos = {}
    individuales = []

    for c in resultados:
        materia = c.get("materias") or {}
        maestro_obj = c.get("maestros") or {}
        materia_id = materia.get("id")
        maestro_clave = maestro_obj.get("clave")
        periodo_id = c.get("periodo_id")
        grupo = c.get("grupo") or ""

        if not (materia_id and maestro_clave and periodo_id and re.search(r'[A-Z]$', grupo)):
            individuales.append(c)
            continue

        grupo_base = re.sub(r'[A-Z]$', '', grupo)
        clave = (materia_id, maestro_clave, periodo_id, grupo_base)

        if clave not in grupos:
            grupos[clave] = []
        grupos[clave].append(c)

    resultados_final = []

    for clave, clases_del_grupo in grupos.items():
        if len(clases_del_grupo) == 1:
            c = clases_del_grupo[0]
            c['es_agrupada'] = False
            c['crns'] = [c['crn']]
            c['grupos_lista'] = [c.get('grupo') or '']
            resultados_final.append(c)
        else:
            primera = clases_del_grupo[0]
            crns = sorted([c['crn'] for c in clases_del_grupo])
            grupos_lista = sorted([c.get('grupo') or '' for c in clases_del_grupo])

            inscritos_lista = [c.get('inscritos', 0) for c in clases_del_grupo]
            capacidad_lista = [c.get('capacidad_materia', 0) for c in clases_del_grupo]

            inscritos_max = max(inscritos_lista) if inscritos_lista else 0
            capacidad_max = max(capacidad_lista) if capacidad_lista else 0

            inscritos_inconsistentes = len(set(inscritos_lista)) > 1

            agrupada = dict(primera)
            agrupada['es_agrupada'] = True
            agrupada['crns'] = crns
            agrupada['grupos_lista'] = grupos_lista
            agrupada['inscritos'] = inscritos_max
            agrupada['capacidad_materia'] = capacidad_max
            agrupada['inscritos_inconsistentes'] = inscritos_inconsistentes
            agrupada['num_partes'] = len(clases_del_grupo)
            resultados_final.append(agrupada)

    for c in individuales:
        c['es_agrupada'] = False
        c['crns'] = [c['crn']]
        c['grupos_lista'] = [c.get('grupo') or '']
        resultados_final.append(c)

    return resultados_final


def _nivel_de_clave_periodo(clave):
    """Replica de nivel_desde_clave_periodo pero en Python. Devuelve el nivel académico
    inferido del sufijo de clave_periodo (ej: BL6→L6, DNC→NC, B6B→6B)."""
    if not clave:
        return None
    c = str(clave).upper()
    r2 = c[-2:] if len(c) >= 2 else ""
    if c in ("B6B", "BB6") or r2 in ("6B", "B6"):
        return "6B"
    if r2 in ("L6", "LS", "LX", "NC", "PT"):
        return r2
    return None


def buscar_clases_avanzado(filtros):
    """Busca clases con todos los filtros aplicados."""
    # Si el estado temporal es 'archivadas', ir a otra función
    if filtros.get("estado_temporal") == "archivadas":
        return buscar_archivadas_como_activas(filtros)

    client = get_client()

    query = client.table("clases").select(
        "crn, periodo_id, grupo, clave_periodo, status, "
        "fecha_inicio, fecha_fin, inscritos, capacidad_materia, vacantes, "
        "tipo_curso, sin_docente, sin_horario, carrera_id, "
        "materias(id, descripcion), "
        "maestros(clave, nombre_completo), "
        "carreras(nombre_banner, programa_clave, programas(nombre, nivel_codigo))"
    )

    if filtros.get("periodo_id"):
        query = query.eq("periodo_id", filtros["periodo_id"])

    if filtros.get("clave_periodo"):
        query = query.eq("clave_periodo", filtros["clave_periodo"])

    if filtros.get("crn"):
        query = query.eq("crn", filtros["crn"])

    if filtros.get("maestro_clave"):
        query = query.eq("maestro_clave", filtros["maestro_clave"])

    if filtros.get("materia_id"):
        val = filtros["materia_id"]
        if isinstance(val, list):
            query = query.in_("materia_id", val)
        else:
            query = query.eq("materia_id", val)

    if filtros.get("carrera_ids"):
        carrera_ids_f = filtros["carrera_ids"]
        nivel_prog = filtros.get("nivel_del_programa")
        if nivel_prog:
            # Traer clases con carrera del programa O multicarrera (carrera_id IS NULL).
            # Después se filtran las multicarrera para dejar solo las del mismo nivel.
            ids_str = ",".join(str(x) for x in carrera_ids_f)
            query = query.or_(f"carrera_id.in.({ids_str}),carrera_id.is.null")
        else:
            query = query.in_("carrera_id", carrera_ids_f)

    # Supabase corta a 1000 registros por consulta por defecto.
    # Para conseguir hasta 5000, paginamos con .range() en un loop.
    query = query.order("crn").order("periodo_id")
    todas = []
    offset = 0
    tamaño_pagina = 1000
    while offset < 5000:
        pagina = query.range(offset, offset + tamaño_pagina - 1).execute().data
        if not pagina:
            break
        todas.extend(pagina)
        offset += tamaño_pagina
        if len(pagina) < tamaño_pagina:
            break

    # Filtro post-query: las multicarrera que se colaron deben ser del nivel del programa
    nivel_prog_filtro = filtros.get("nivel_del_programa")
    if filtros.get("carrera_ids") and nivel_prog_filtro:
        def _pasa_por_programa(c):
            carrera = c.get("carreras") or {}
            if carrera:
                return True  # Con carrera: viene del filtro carrera_ids
            # Multicarrera: filtrar por nivel del programa
            return _nivel_de_clave_periodo(c.get("clave_periodo")) == nivel_prog_filtro
        todas = [c for c in todas if _pasa_por_programa(c)]

    # Filtro por nivel académico (en memoria, después de traer los datos)
    nivel = filtros.get("nivel")
    if nivel:
        def _pasa_filtro_nivel(c):
            carrera = c.get("carreras") or {}
            if nivel == "multicarrera":
                return not carrera
            # 1) Si tiene carrera, mirar programas.nivel_codigo (normalizado B6→6B)
            programas = carrera.get("programas") or {}
            nivel_carrera = programas.get("nivel_codigo")
            if nivel_carrera:
                if nivel_carrera == "B6":
                    nivel_carrera = "6B"
                return nivel_carrera == nivel
            # 2) Sin carrera: inferir desde clave_periodo
            return _nivel_de_clave_periodo(c.get("clave_periodo")) == nivel

        todas = [c for c in todas if _pasa_filtro_nivel(c)]

    return todas


def main():
    encabezado("Clases", "Busca y filtra las clases del campus", "🔍")

    # Cargar opciones
    periodos = cargar_periodos(solo_activos=True)

    # ===== FILTROS PRINCIPALES =====
    st.subheader("🎯 Filtros principales")

    col1, col2, col3 = st.columns(3)

    with col1:
        # Nivel académico (sustituye al filtro por periodo)
        NIVELES_OPCIONES = [
            ("Todos", "Todos los niveles"),
            ("6B", "🎓 Bachillerato (6B)"),
            ("L6", "🎓 Licenciatura semestral (L6)"),
            ("LS", "🎓 Licenciatura sabatinos (LS)"),
            ("LX", "🎓 Licenciatura Ejecutiva (LX)"),
            ("NC", "🎓 Ciencias de la Salud (NC)"),
            ("PT", "🎓 Posgrado / Maestría (PT)"),
            ("multicarrera", "🔀 Multicarrera (sin carrera asignada)"),
        ]
        nivel_sel = st.selectbox(
            "🏷️ Nivel académico",
            [k for k, _ in NIVELES_OPCIONES],
            format_func=lambda k: dict(NIVELES_OPCIONES)[k],
        )
        nivel_filtro = None if nivel_sel == "Todos" else nivel_sel

        # Estas dos variables ya no se usan pero se dejan como None para no romper el dict de filtros
        periodo_id = None
        clave_periodo = None

    with col2:
        # CRN específico
        crn_input = st.text_input("🔢 CRN específico", placeholder="Ej: 6971")
        crn_filter = None
        if crn_input.strip():
            try:
                crn_filter = int(crn_input.strip())
            except ValueError:
                st.warning("El CRN debe ser un número")

    with col3:
        # Búsqueda por maestro
        st.caption("💡 Escribe al menos 3 letras del nombre y presiona **Enter** para buscar.")
        maestro_busqueda = st.text_input(
            "👨‍🏫 Buscar maestro",
            placeholder="Nombre del maestro"
        )
        maestro_clave = None
        texto_m = maestro_busqueda.strip()
        if texto_m and len(texto_m) >= 3:
            maestros_encontrados = buscar_maestros(maestro_busqueda)
            if maestros_encontrados:
                opciones_maestro = ["Cualquiera"] + [f"{m['clave']} - {m['nombre_completo']}" for m in maestros_encontrados]
                maestro_sel = st.selectbox(
                    f"Seleccionar ({len(maestros_encontrados)} encontrados)",
                    opciones_maestro
                )
                if maestro_sel != "Cualquiera":
                    maestro_clave = int(maestro_sel.split(" - ")[0])
            else:
                st.warning(f"⚠️ No se encontraron maestros que coincidan con «{texto_m}».")

        # Búsqueda por materia
        st.caption("💡 Escribe al menos 3 letras (o el ID) y presiona **Enter** para buscar.")
        materia_busqueda = st.text_input(
            "📚 Buscar materia",
            placeholder="Nombre o ID de materia"
        )
        materia_id = None
        texto_mat = materia_busqueda.strip()
        _materia_lista_ok = False
        if texto_mat and len(texto_mat) >= 3:
            materias_encontradas = buscar_materias(materia_busqueda)
            if materias_encontradas:
                _materia_lista_ok = True
                # Agrupar por nombre (case/acento-insensitive) para juntar variantes
                import unicodedata

                def _normalizar(s):
                    if not s:
                        return ""
                    s = str(s).upper()
                    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
                    return s.strip()

                grupos_materia = {}
                for m in materias_encontradas:
                    clave_norm = _normalizar(m['descripcion'])
                    if clave_norm not in grupos_materia:
                        grupos_materia[clave_norm] = {
                            "nombre": m['descripcion'],
                            "ids": []
                        }
                    grupos_materia[clave_norm]["ids"].append(m['id'])

                opciones_materia = ["Cualquiera"]
                for clave_norm, info in grupos_materia.items():
                    n_ids = len(info["ids"])
                    label = info["nombre"] if n_ids == 1 else f"{info['nombre']} ({n_ids} versiones)"
                    opciones_materia.append(label)

                materia_sel = st.selectbox(
                    f"Seleccionar ({len(materias_encontradas)} encontradas)",
                    opciones_materia
                )
                if materia_sel != "Cualquiera":
                    for clave_norm, info in grupos_materia.items():
                        label = info["nombre"] if len(info["ids"]) == 1 else f"{info['nombre']} ({len(info['ids'])} versiones)"
                        if label == materia_sel:
                            ids = info["ids"]
                            materia_id = ids if len(ids) > 1 else ids[0]
                            break
            else:
                st.warning(f"⚠️ No se encontraron materias que coincidan con «{texto_mat}».")

    # Filtro por programa académico (dependiente del nivel seleccionado)
    programa_filtro = None
    carrera_ids_filtro = None
    nivel_del_programa = None  # nivel al que pertenece el programa (para incluir multicarrera de ese nivel)
    sin_carreras_vinculadas = False
    client = get_client()

    if nivel_filtro == "multicarrera":
        # Multicarrera = clases sin carrera asignada, no aplica programa
        st.caption("ℹ️ El filtro por programa no aplica cuando el nivel es **Multicarrera** "
                   "(son clases sin carrera asignada).")
    else:
        # Si hay un nivel específico, solo mostrar programas de ese nivel.
        # Manejo especial de Bachillerato: en la base hay '6B' y 'B6' (mismo bachillerato).
        if nivel_filtro == "6B":
            programas_6b = cargar_programas("6B") + cargar_programas("B6")
            vistos = set()
            programas = []
            for p in programas_6b:
                if p["clave"] not in vistos:
                    vistos.add(p["clave"])
                    programas.append(p)
        elif nivel_filtro:
            programas = cargar_programas(nivel_filtro)
        else:
            programas = cargar_programas()

        opciones_programa = ["Todos"] + [f"{p['clave']} - {p['nombre']}" for p in programas]
        label = "🎓 Programa académico"
        if nivel_filtro:
            label += f" (filtrado por nivel {nivel_filtro})"
        programa_sel = st.selectbox(label, opciones_programa)
        if programa_sel != "Todos":
            programa_filtro = programa_sel.split(" - ")[0]

        if programa_filtro:
            carreras_res = client.table("carreras").select("id, nivel_id").eq("programa_clave", programa_filtro).execute()
            if carreras_res.data:
                carrera_ids_filtro = [c['id'] for c in carreras_res.data]
                # Guardar el nivel del programa para también incluir multicarrera de ese nivel
                niveles_programa = list({c['nivel_id'] for c in carreras_res.data if c.get('nivel_id')})
                if niveles_programa:
                    nivel_del_programa = niveles_programa[0]
                    if nivel_del_programa == "B6":
                        nivel_del_programa = "6B"
                if len(carrera_ids_filtro) > 1:
                    st.caption(f"ℹ️ El programa tiene {len(carrera_ids_filtro)} versiones en Banner; se filtra por todas.")
            else:
                sin_carreras_vinculadas = True
                st.warning(
                    f"⚠️ El programa **{programa_filtro}** está en el catálogo pero NO tiene carreras vinculadas en Banner. "
                    f"Probablemente la clave del Excel oficial no coincide con la de Banner. "
                    f"No habrá resultados para este filtro."
                )

    st.divider()

    # Filtro temporal (radio con 4 opciones) + toggle de agrupar
    col_t1, col_t2 = st.columns([2.5, 1.2])
    with col_t1:
        estado_temporal = st.radio(
            "Mostrar:",
            ["todas_activas_futuras", "activas_hoy", "futuras", "archivadas"],
            format_func=lambda k: {
                "todas_activas_futuras": "🌐 Activas + futuras",
                "activas_hoy":           "🟢 Solo activas hoy",
                "futuras":               "📅 Solo futuras",
                "archivadas":            "📦 Solo archivadas (histórico)",
            }[k],
            horizontal=True,
            key="estado_temporal_clases",
        )
    with col_t2:
        ver_agrupado = st.toggle(
            "🔗 Ver clases agrupadas",
            value=False,
            help="Junta automáticamente los grupos divididos (ej: 17A + 17B = una sola clase)"
        )

    st.divider()

    # Botón de búsqueda
    col_btn1, col_btn2 = st.columns([1, 5])
    with col_btn1:
        buscar = st.button("🔍 Buscar", type="primary", use_container_width=True)
    with col_btn2:
        if st.button("🔄 Limpiar filtros", use_container_width=False):
            st.rerun()

    # ===== EJECUTAR BÚSQUEDA =====
    if buscar:
        if sin_carreras_vinculadas:
            st.error("❌ No se realiza la búsqueda porque el filtro de nivel/programa no tiene carreras vinculadas en Banner.")
            st.session_state.pop("busq_raw", None)
        else:
            with st.spinner("Buscando..."):
                filtros = {
                    "periodo_id": periodo_id, "clave_periodo": clave_periodo,
                    "crn": crn_filter,
                    "maestro_clave": maestro_clave, "materia_id": materia_id,
                    "carrera_ids": carrera_ids_filtro,
                    "nivel": nivel_filtro,
                    "nivel_del_programa": nivel_del_programa,
                    "estado_temporal": estado_temporal,
                }
                resultados = buscar_clases_avanzado(filtros)

            st.session_state["busq_raw"] = resultados
            st.session_state["busq_sel"] = "— Ninguna —"

    # ===== MOSTRAR RESULTADOS (persisten aunque hagas clic en algo) =====
    raw = st.session_state.get("busq_raw")
    if raw is None:
        st.info("👆 Selecciona filtros y haz clic en **Buscar** para ver las clases")
        return
    if len(raw) == 0:
        st.warning("⚠️ No se encontraron clases con esos filtros")
        return

    # Filtro por fecha según estado_temporal (para 'activas_hoy' y 'futuras').
    # 'todas_activas_futuras' y 'archivadas' NO filtran aquí porque ya viene filtrado.
    hoy_iso = date.today().isoformat()
    if estado_temporal == "activas_hoy":
        raw_filtrado = [r for r in raw
                        if r.get("fecha_inicio") and r.get("fecha_fin")
                        and str(r["fecha_inicio"]) <= hoy_iso <= str(r["fecha_fin"])]
    elif estado_temporal == "futuras":
        raw_filtrado = [r for r in raw
                        if r.get("fecha_inicio") and str(r["fecha_inicio"]) > hoy_iso]
    elif estado_temporal == "todas_activas_futuras":
        # Excluye vencidas (por si alguna se coló)
        raw_filtrado = [r for r in raw
                        if not r.get("fecha_fin") or str(r["fecha_fin"]) >= hoy_iso]
    else:
        # 'archivadas': ya vienen filtradas
        raw_filtrado = raw

    # Agrupar (o no) según el interruptor ACTUAL, para que responda al instante
    agrupado = ver_agrupado
    if agrupado:
        resultados_mostrar = agrupar_resultados([dict(r) for r in raw_filtrado])
    else:
        resultados_mostrar = []
        for r in raw_filtrado:
            rr = dict(r)
            rr["es_agrupada"] = False
            rr["crns"] = [rr["crn"]]
            rr["grupos_lista"] = [rr.get("grupo") or ""]
            resultados_mostrar.append(rr)

    total = len(resultados_mostrar)
    total_originales = len(raw_filtrado)
    con_inscritos = sum(1 for r in resultados_mostrar if r.get("inscritos", 0) > 0)
    total_inscritos = sum(r.get("inscritos", 0) for r in resultados_mostrar)

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        if agrupado:
            st.metric("🔗 Clases (agrupadas)", total, delta=f"{total - total_originales}")
        else:
            st.metric("📝 Clases encontradas", total)
    with col_m2:
        st.metric("✅ Con inscritos", con_inscritos)
    with col_m3:
        st.metric("👥 Total estudiantes", total_inscritos)
    with col_m4:
        if agrupado:
            agrupadas_count = sum(1 for r in resultados_mostrar if r.get("es_agrupada"))
            st.metric("🔗 Filas agrupadas", agrupadas_count)

    st.divider()

    filas = []
    for c in resultados_mostrar:
        materia = c.get("materias") or {}
        maestro = c.get("maestros") or {}
        carrera = c.get("carreras") or {}
        programa_info = (carrera.get("programas") or {}) if carrera else {}
        if c.get("es_agrupada"):
            crns_str = f"🔗 {', '.join(str(x) for x in c['crns'])}"
            grupos_str = ", ".join(c["grupos_lista"])
        else:
            crns_str = str(c["crns"][0]) if c.get("crns") else str(c.get("crn", ""))
            grupos_str = c["grupos_lista"][0] if c.get("grupos_lista") else c.get("grupo", "")
        inscritos_str = f"{c.get('inscritos', 0)}/{c.get('capacidad_materia', 0)}"
        if c.get("es_agrupada") and c.get("inscritos_inconsistentes"):
            inscritos_str = f"⚠️ {inscritos_str}"
        filas.append({
            "CRN(s)": crns_str, "Periodo": c["periodo_id"],
            "Clave": c.get("clave_periodo") or "", "Grupo(s)": grupos_str,
            "Materia": materia.get("descripcion") or "(multi)",
            "Maestro": maestro.get("nombre_completo") or "Sin asignar",
            "Programa": programa_info.get("nombre") or "(multi-carrera)",
            "Nivel": programa_info.get("nivel_codigo") or "—",
            "Inscritos/Cap": inscritos_str,
            "F. Inicio": c.get("fecha_inicio") or "", "F. Fin": c.get("fecha_fin") or "",
        })
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True, height=460)
    st.caption(f"Mostrando {total} resultado(s).")

    st.divider()
    st.subheader("🔎 Ver el horario de una clase")
    opciones = ["— Ninguna —"]
    mapa = {}
    for c in resultados_mostrar:
        crn0 = c["crns"][0] if c.get("crns") else c.get("crn")
        mat = (c.get("materias") or {}).get("descripcion") or "(multi)"
        grp = c["grupos_lista"][0] if c.get("grupos_lista") else (c.get("grupo") or "")
        etq = f"CRN {crn0} · {grp} · {mat}"
        opciones.append(etq)
        mapa[etq] = c
    sel = st.selectbox("Elige una clase para ver su horario", opciones, key="busq_sel")
    if sel and sel != "— Ninguna —":
        _mostrar_detalle_clase(mapa[sel])


main()