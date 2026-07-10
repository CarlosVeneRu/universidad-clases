"""
Archivar (recuperable) o eliminar (permanente) clases, y eliminar maestros.
Nota: el bloqueo por rol (Admin/Moderador) se aplica en el paso del login.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from app.utils.queries import get_client
from app.utils.ui import encabezado

NIVELES_LEGIBLES = {
    "LX": "Licenciatura Ejecutiva", "NC": "Ciencias de la Salud",
    "PT": "Posgrado / Maestría", "L6": "Licenciatura", "LS": "Licenciatura",
    "B6": "Bachillerato", "6B": "Bachillerato",
}
NIVELES_CODIGOS = ["B6", "L6", "LS", "LX", "NC", "PT"]


def etiqueta_periodo(pid, desc):
    cods = []
    for clave in str(desc or "").split(","):
        clave = clave.strip().upper()
        for cod in NIVELES_LEGIBLES:
            if cod in clave and cod not in cods:
                cods.append(cod)
                break
    return f"{pid} · {NIVELES_LEGIBLES[cods[0]]} ({', '.join(sorted(cods))})" if cods else str(pid)


def nivel_de_clave(clave):
    """De 'BL6', '1LX', etc. saca el código de nivel corto."""
    if not clave:
        return "—"
    clave = str(clave).upper()
    for cod in NIVELES_CODIGOS:
        if cod in clave:
            return cod
    return "Otros"


encabezado("Archivar / Eliminar", "Archiva (recuperable) o elimina (permanente)", "🗑️")

client = get_client()
usuario = st.session_state.get("usuario", "editor_web")


@st.cache_data(ttl=300)
def cargar_catalogos():
    # Traer periodos con su estado (activo / concluido / vacio)
    periodos = (client.table("periodos_con_estado")
                .select("id, descripcion, estado")
                .order("id", desc=True).execute().data)
    materias = client.table("materias").select("id, descripcion").execute().data
    maestros = client.table("maestros").select("clave, nombre_completo").order("nombre_completo").execute().data
    return periodos, materias, maestros


periodos, materias, maestros = cargar_catalogos()
materias_dict = {m["id"]: m["descripcion"] for m in materias}
maestros_dict = {m["clave"]: m["nombre_completo"] for m in maestros}
periodo_label = {p["id"]: etiqueta_periodo(p["id"], p.get("descripcion")) for p in periodos}


# =======================================================================
# MENU LATERAL (radio) — decide qué sección se muestra
# =======================================================================
OPCIONES = {
    "clases": "📂 Clases activas (buscar, archivar o eliminar)",
    "archivadas": "♻️ Clases archivadas (recuperar o borrar)",
    "maestro": "👨‍🏫 Eliminar maestro",
    "materia": "📚 Eliminar materia",
    "masivo": "📦 Archivado masivo (por nivel/programa)",
}

col_menu, col_contenido = st.columns([1.2, 4])

with col_menu:
    st.markdown("**¿Qué quieres hacer?**")
    seccion = st.radio(
        "Secciones",
        list(OPCIONES.keys()),
        format_func=lambda k: OPCIONES[k],
        label_visibility="collapsed",
        key="seccion_archeliminar",
    )


# =======================================================================
# HELPERS DE BÚSQUEDA/TABLA
# =======================================================================
def render_filtros(prefijo, incluir_concluidos=False):
    """Devuelve (texto, nivel, periodo) según lo que elija el usuario.
    incluir_concluidos: si es True, en el selector de periodos también aparecen los concluidos."""
    col_f1, col_f2, col_f3 = st.columns([3, 1, 2])
    with col_f1:
        texto = st.text_input(
            "🔎 Buscar por CRN, materia, maestro o grupo",
            key=f"{prefijo}_texto",
            placeholder="Ej: 12345, CALCULO, GARCIA...",
        ).strip()
    with col_f2:
        opciones_nivel = ["Todos"] + NIVELES_CODIGOS
        nivel_sel = st.selectbox(
            "🏷️ Nivel",
            opciones_nivel,
            format_func=lambda v: v if v == "Todos" else f"{v} · {NIVELES_LEGIBLES.get(v, '')}",
            key=f"{prefijo}_nivel"
        )
        nivel = None if nivel_sel == "Todos" else nivel_sel
    with col_f3:
        # Filtrar según sea sección de activas o archivadas
        periodos_filtrados = periodos if incluir_concluidos else [p for p in periodos if p.get("estado") == "activo"]
        opciones_periodo = [None] + [p["id"] for p in periodos_filtrados]

        def _etq_periodo(v):
            if v is None:
                return "Todos los periodos"
            p = next((x for x in periodos if x["id"] == v), None)
            base = periodo_label.get(v, str(v))
            if p and p.get("estado") == "concluido":
                return f"🔒 {base} (Concluido)"
            return base

        periodo_sel = st.selectbox(
            "📅 Periodo",
            opciones_periodo,
            format_func=_etq_periodo,
            key=f"{prefijo}_periodo"
        )
    return texto or None, nivel, periodo_sel
    with col_f1:
        texto = st.text_input(
            "🔎 Buscar por CRN, materia, maestro o grupo",
            key=f"{prefijo}_texto",
            placeholder="Ej: 12345, CALCULO, GARCIA...",
        ).strip()
    with col_f2:
        opciones_nivel = ["Todos"] + NIVELES_CODIGOS
        nivel_sel = st.selectbox(
            "🏷️ Nivel",
            opciones_nivel,
            format_func=lambda v: v if v == "Todos" else f"{v} · {NIVELES_LEGIBLES.get(v, '')}",
            key=f"{prefijo}_nivel"
        )
        nivel = None if nivel_sel == "Todos" else nivel_sel
    with col_f3:
        opciones_periodo = [None] + [p["id"] for p in periodos]
        periodo_sel = st.selectbox(
            "📅 Periodo",
            opciones_periodo,
            format_func=lambda v: "Todos los periodos" if v is None else periodo_label.get(v, str(v)),
            key=f"{prefijo}_periodo"
        )
    return texto or None, nivel, periodo_sel


def render_tabla_seleccion(prefijo, es_archivadas=False):
    """Muestra los filtros + tabla con casillas y devuelve las claves (crn, periodo) seleccionadas."""
    texto, nivel, periodo = render_filtros(prefijo, incluir_concluidos=es_archivadas)

    rpc = "buscar_archivadas_con_detalle" if es_archivadas else "buscar_clases_con_detalle"
    try:
        res = client.rpc(rpc, {
            "p_texto": texto, "p_nivel": nivel, "p_periodo": periodo
        }).execute().data or []
    except Exception as e:
        st.error(f"Error al buscar: {e}")
        return []

    if not res:
        st.info("No hay clases que coincidan con estos filtros.")
        return []

    st.caption(f"🔎 {len(res)} clase(s) encontrada(s).")

    seleccion = []
    cols_head = st.columns([0.5, 1, 1.2, 3, 2, 2, 0.8])
    for col, txt in zip(cols_head, ["☑", "CRN", "Nivel", "Materia", "Maestro", "Salón", "Grupo"]):
        col.markdown(f"**{txt}**")

    for r in res:
        cols = st.columns([0.5, 1, 1.2, 3, 2, 2, 0.8])
        clave = (r["crn"], r["periodo_id"])
        with cols[0]:
            marcado = st.checkbox("", key=f"{prefijo}_chk_{r['crn']}_{r['periodo_id']}", label_visibility="collapsed")
        cols[1].markdown(f"`{r['crn']}`")
        cols[2].markdown(f"**{nivel_de_clave(r.get('clave_periodo'))}** · {r['periodo_id']}")
        cols[3].markdown(r.get("materia_descripcion") or "—")
        cols[4].markdown(r.get("maestro_nombre") or "*sin asignar*")
        cols[5].markdown(f"`{r.get('salones') or '—'}`")
        cols[6].markdown(r.get("grupo") or "—")
        if marcado:
            seleccion.append(clave)

    return seleccion


def limpiar_checkboxes(prefijo, claves):
    for crn, per in claves:
        k = f"{prefijo}_chk_{crn}_{per}"
        if k in st.session_state:
            st.session_state[k] = False


# =======================================================================
# CONTENIDO (según la sección elegida)
# =======================================================================
with col_contenido:

    if seccion == "clases":
        st.markdown("### 📂 Clases activas")
        st.caption("Busca las clases que quieras, márcalas y elige la acción: archivar (reversible) o eliminar (permanente).")

        seleccion = render_tabla_seleccion("clases")

        if seleccion:
            st.divider()
            st.markdown(f"**{len(seleccion)} clase(s) marcada(s).** ¿Qué quieres hacer con ellas?")

            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown("**📦 Archivar** (se pueden recuperar en 30 días)")
                if st.button(f"📦 Archivar {len(seleccion)}", type="primary", key="btn_arch"):
                    n_ok, errs = 0, []
                    for crn, per in seleccion:
                        try:
                            client.rpc("archivar_clase",
                                       {"p_crn": crn, "p_periodo": per, "p_usuario": usuario}).execute()
                            n_ok += 1
                        except Exception as e:
                            errs.append(f"CRN {crn}: {str(e)[:80]}")
                    limpiar_checkboxes("clases", seleccion)
                    if n_ok:
                        st.success(f"📦 {n_ok} clase(s) archivada(s).")
                    if errs:
                        st.error("; ".join(errs[:5]))
                    st.cache_data.clear()
                    st.rerun()

            with col_b:
                st.markdown("**🗑️ Eliminar** (permanente, no se puede deshacer)")
                conf = st.text_input("Escribe:  ELIMINAR", key="conf_del")
                if st.button(f"🗑️ Eliminar {len(seleccion)}", type="primary",
                             disabled=(conf.strip().upper() != "ELIMINAR"), key="btn_del"):
                    n_ok, errs = 0, []
                    for crn, per in seleccion:
                        try:
                            client.table("clases").delete().eq("crn", crn).eq("periodo_id", per).execute()
                            n_ok += 1
                        except Exception as e:
                            errs.append(f"CRN {crn}: {str(e)[:80]}")
                    limpiar_checkboxes("clases", seleccion)
                    if n_ok:
                        st.success(f"🗑️ {n_ok} clase(s) eliminada(s).")
                    if errs:
                        st.error("; ".join(errs[:5]))
                    st.rerun()

    elif seccion == "archivadas":
        st.markdown("### ♻️ Clases archivadas")
        st.caption("Se borran solas a los 30 días. Puedes recuperarlas o eliminarlas antes.")

        seleccion = render_tabla_seleccion("archrec", es_archivadas=True)

        if seleccion:
            st.divider()
            st.markdown(f"**{len(seleccion)} clase(s) marcada(s).** ¿Qué quieres hacer?")

            col_r, col_e = st.columns(2)

            with col_r:
                st.markdown("**♻️ Recuperar** (vuelven al sistema)")
                if st.button(f"♻️ Recuperar {len(seleccion)}", type="primary", key="btn_rec"):
                    n_ok, errs = 0, []
                    for crn, per in seleccion:
                        try:
                            client.rpc("recuperar_clase", {"p_crn": crn, "p_periodo": per}).execute()
                            n_ok += 1
                        except Exception as e:
                            errs.append(f"CRN {crn}: {str(e)[:80]}")
                    limpiar_checkboxes("archrec", seleccion)
                    if n_ok:
                        st.success(f"♻️ {n_ok} recuperada(s).")
                    if errs:
                        st.error("; ".join(errs[:5]))
                    st.cache_data.clear()
                    st.rerun()

            with col_e:
                st.markdown("**🗑️ Eliminar del archivo** (permanente)")
                conf = st.text_input("Escribe:  ELIMINAR", key="conf_elim_arch")
                if st.button(f"🗑️ Eliminar {len(seleccion)}", type="primary",
                             disabled=(conf.strip().upper() != "ELIMINAR"), key="btn_elim_arch"):
                    n_ok, errs = 0, []
                    for crn, per in seleccion:
                        try:
                            client.table("clases_archivadas").delete().eq("crn", crn).eq("periodo_id", per).execute()
                            n_ok += 1
                        except Exception as e:
                            errs.append(f"CRN {crn}: {str(e)[:80]}")
                    limpiar_checkboxes("archrec", seleccion)
                    if n_ok:
                        st.success(f"🗑️ {n_ok} eliminada(s) del archivo.")
                    if errs:
                        st.error("; ".join(errs[:5]))
                    st.rerun()

    elif seccion == "maestro":
        st.markdown("### 👨‍🏫 Eliminar maestro")
        st.warning("⚠️ Eliminar un maestro es **permanente**.")
        claves = [m["clave"] for m in maestros]
        maestro_sel = st.selectbox("Maestro", claves,
                                   format_func=lambda c: maestros_dict.get(c, str(c)), key="delm_sel")
        if maestro_sel:
            n_act = client.table("clases").select("crn", count="exact").eq("maestro_clave", maestro_sel).execute().count or 0
            n_arch = client.table("clases_archivadas").select("crn", count="exact").eq("maestro_clave", maestro_sel).execute().count or 0
            if n_act > 0 or n_arch > 0:
                st.error(f"Este maestro se usa en **{n_act} clases activas** y **{n_arch} archivadas**. "
                         "No se puede eliminar hasta que esas clases se reasignen, se eliminen, o se quiten del archivo.")
            else:
                st.info("Este maestro no tiene clases asignadas, se puede eliminar.")
                ok = st.checkbox("Entiendo que es permanente", key="delm_ok")
                if st.button("🗑️ Eliminar maestro", type="primary", disabled=not ok, key="btn_delm"):
                    try:
                        client.table("maestros").delete().eq("clave", maestro_sel).execute()
                        st.success("🗑️ Maestro eliminado.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ No se pudo eliminar: {e}")

    elif seccion == "materia":
        st.markdown("### 📚 Eliminar materia")
        st.warning("⚠️ Eliminar una materia es **permanente**.")
        mat_ids = [None] + sorted([m["id"] for m in materias],
                                  key=lambda i: materias_dict.get(i, "").upper())
        materia_sel = st.selectbox(
            "Materia", mat_ids,
            format_func=lambda i: "— Elige una materia —" if i is None else f"{i} · {materias_dict.get(i, '')}",
            key="delmat_sel")
        if materia_sel:
            n_act = client.table("clases").select("crn", count="exact").eq("materia_id", materia_sel).execute().count or 0
            n_arch = client.table("clases_archivadas").select("crn", count="exact").eq("materia_id", materia_sel).execute().count or 0
            if n_act > 0 or n_arch > 0:
                st.error(f"Esta materia se usa en **{n_act} clases activas** y **{n_arch} archivadas**. "
                         "No se puede eliminar hasta que esas clases se reasignen, se eliminen, o se quiten del archivo.")
            else:
                st.info("Esta materia no se usa en ninguna clase, se puede eliminar.")
                ok = st.checkbox("Entiendo que es permanente", key="delmat_ok")
                if st.button("🗑️ Eliminar materia", type="primary", disabled=not ok, key="btn_delmat"):
                    try:
                        client.table("materias").delete().eq("id", materia_sel).execute()
                        st.success("🗑️ Materia eliminada.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ No se pudo eliminar: {e}")

    elif seccion == "masivo":
        st.markdown("### 📦 Archivado masivo")
        st.warning("⚠️ Esto archiva MUCHAS clases de una sola vez. Se pueden recuperar "
                   "desde la sección '♻️ Clases archivadas', y se borran solas a los 30 días.")

        rol = st.session_state.get("rol", "viewer")
        if rol != "admin":
            st.info("🔒 Solo el administrador puede archivar por nivel o programa.")
        elif not st.session_state.get("bulk_activo", False):
            st.info("Por seguridad, esta sección necesita que la actives manualmente.")
            if st.button("🔓 Activar herramientas de archivado masivo"):
                st.session_state["bulk_activo"] = True
                st.rerun()
        else:
            _NIVELES_NOMBRE = {
                "LX": "Licenciatura Ejecutiva", "NC": "Ciencias de la Salud",
                "PT": "Posgrado / Maestría", "L6": "Licenciatura", "LS": "Licenciatura",
                "B6": "Bachillerato", "6B": "Bachillerato",
            }
            programas = client.rpc("conteo_programas", {}).execute().data or []

            modo = st.radio("¿Qué quieres archivar?", ["Un nivel académico", "Un programa (carrera)"])

            if modo == "Un nivel académico":
                por_nivel = {}
                for pr in programas:
                    por_nivel[pr["nivel"]] = por_nivel.get(pr["nivel"], 0) + pr["clases"]
                if not por_nivel:
                    st.info("No hay clases activas para archivar.")
                else:
                    niveles = sorted(por_nivel.keys())
                    nivel_sel = st.selectbox(
                        "Nivel a archivar", niveles,
                        format_func=lambda n: f"{_NIVELES_NOMBRE.get(n, n)} ({n}) — {por_nivel[n]} clases")
                    st.error(f"Vas a archivar **{por_nivel[nivel_sel]} clases** del nivel "
                             f"**{_NIVELES_NOMBRE.get(nivel_sel, nivel_sel)}**.")
                    conf = st.text_input("Para confirmar, escribe:  ARCHIVAR", key="conf_nivel")
                    if st.button("📦 Archivar este nivel", type="primary",
                                 disabled=(conf.strip().upper() != "ARCHIVAR"), key="btn_nivel"):
                        try:
                            n = client.rpc("archivar_por_nivel",
                                           {"p_nivel": nivel_sel, "p_usuario": usuario}).execute().data
                            st.success(f"✅ Se archivaron {n} clases del nivel {nivel_sel}. "
                                       "Puedes recuperarlas en '♻️ Clases archivadas'.")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ No se pudo archivar: {e}")
            else:
                if not programas:
                    st.info("No hay programas con clases activas.")
                else:
                    mapa = {f"{pr['nombre']} · {pr['nivel']} — {pr['clases']} clases": pr for pr in programas}
                    etq = st.selectbox("Programa a archivar", list(mapa.keys()))
                    prog = mapa[etq]
                    st.error(f"Vas a archivar **{prog['clases']} clases** del programa **{prog['nombre']}**.")
                    conf = st.text_input("Para confirmar, escribe:  ARCHIVAR", key="conf_prog")
                    if st.button("📦 Archivar este programa", type="primary",
                                 disabled=(conf.strip().upper() != "ARCHIVAR"), key="btn_prog"):
                        try:
                            n = client.rpc("archivar_por_programa",
                                           {"p_carrera_id": prog["carrera_id"], "p_usuario": usuario}).execute().data
                            st.success(f"✅ Se archivaron {n} clases del programa {prog['nombre']}. "
                                       "Puedes recuperarlas en '♻️ Clases archivadas'.")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ No se pudo archivar: {e}")

            st.divider()
            st.subheader("📚 Archivar clases multi-carrera")
            st.caption("Las clases multi-carrera no tienen una carrera asignada. "
                       "No entran en 'nivel/programa' de arriba, por eso se archivan aparte.")

            conteo_mc = client.rpc("conteo_multicarrera", {}).execute().data or []
            if not conteo_mc:
                st.info("No hay clases multi-carrera activas.")
            else:
                modo_mc = st.radio(
                    "¿Qué quieres archivar?",
                    ["Por nivel + periodo (más específico)", "Todo un periodo (más amplio)"],
                    key="mc_modo",
                )
                _NIVELES_NOMBRE_MC = {
                    "LX": "Licenciatura Ejecutiva", "NC": "Ciencias de la Salud",
                    "PT": "Posgrado / Maestría", "L6": "Licenciatura",
                    "LS": "Licenciatura", "B6": "Bachillerato", "6B": "Bachillerato",
                    "(otro)": "Otro / sin nivel claro",
                }

                if modo_mc.startswith("Por nivel"):
                    opciones = [(row["periodo"], row["nivel"], row["clases"]) for row in conteo_mc]
                    etq = st.selectbox(
                        "Nivel y periodo a archivar",
                        range(len(opciones)),
                        format_func=lambda i: (
                            f"{_NIVELES_NOMBRE_MC.get(opciones[i][1], opciones[i][1])} "
                            f"({opciones[i][1]}) · periodo {opciones[i][0]} "
                            f"— {opciones[i][2]} clases"
                        ),
                        key="mc_sel_np",
                    )
                    per, niv, n_cl = opciones[etq]
                    st.error(f"Vas a archivar **{n_cl} clases** multi-carrera del nivel "
                             f"**{_NIVELES_NOMBRE_MC.get(niv, niv)}** en el periodo **{per}**.")
                    conf = st.text_input("Para confirmar, escribe:  ARCHIVAR", key="conf_mc_np")
                    if st.button("📦 Archivar", type="primary",
                                 disabled=(conf.strip().upper() != "ARCHIVAR"),
                                 key="btn_mc_np"):
                        try:
                            n = client.rpc(
                                "archivar_multicarrera_por_nivel_periodo",
                                {"p_nivel": niv, "p_periodo": per, "p_usuario": usuario},
                            ).execute().data
                            st.success(f"✅ Se archivaron {n} clases multi-carrera.")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ No se pudo archivar: {e}")
                else:
                    por_periodo = {}
                    niveles_por_periodo = {}
                    for row in conteo_mc:
                        p = row["periodo"]
                        por_periodo[p] = por_periodo.get(p, 0) + row["clases"]
                        niveles_por_periodo.setdefault(p, []).append(row["nivel"])
                    periodos_mc = sorted(por_periodo.keys(), reverse=True)

                    def _etq_periodo(p):
                        nombres = []
                        for cod in niveles_por_periodo.get(p, []):
                            nom = _NIVELES_NOMBRE_MC.get(cod, cod)
                            if nom not in nombres:
                                nombres.append(nom)
                        niveles_txt = ", ".join(nombres) if nombres else "sin nivel"
                        return f"Periodo {p} · {niveles_txt} — {por_periodo[p]} clases"

                    per = st.selectbox(
                        "Periodo a archivar",
                        periodos_mc,
                        format_func=_etq_periodo,
                        key="mc_sel_p",
                    )
                    st.error(f"Vas a archivar **{por_periodo[per]} clases** multi-carrera del "
                             f"periodo **{per}** (de todos los niveles).")
                    conf = st.text_input("Para confirmar, escribe:  ARCHIVAR", key="conf_mc_p")
                    if st.button("📦 Archivar", type="primary",
                                 disabled=(conf.strip().upper() != "ARCHIVAR"),
                                 key="btn_mc_p"):
                        try:
                            n = client.rpc(
                                "archivar_multicarrera_por_periodo",
                                {"p_periodo": per, "p_usuario": usuario},
                            ).execute().data
                            st.success(f"✅ Se archivaron {n} clases multi-carrera.")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ No se pudo archivar: {e}")

            st.divider()
            if st.button("Cerrar herramientas de archivado masivo"):
                st.session_state["bulk_activo"] = False
                st.rerun()