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


def etiqueta_periodo(pid, desc):
    cods = []
    for clave in str(desc or "").split(","):
        clave = clave.strip().upper()
        for cod in NIVELES_LEGIBLES:
            if cod in clave and cod not in cods:
                cods.append(cod)
                break
    return f"{pid} · {NIVELES_LEGIBLES[cods[0]]} ({', '.join(sorted(cods))})" if cods else str(pid)


encabezado("Archivar / Eliminar", "Archiva (recuperable) o elimina (permanente)", "🗑️")

client = get_client()
usuario = st.session_state.get("usuario", "editor_web")


@st.cache_data(ttl=300)
def cargar_catalogos():
    periodos = client.table("periodos").select("id, descripcion").order("id", desc=True).execute().data
    materias = client.table("materias").select("id, descripcion").execute().data
    maestros = client.table("maestros").select("clave, nombre_completo").order("nombre_completo").execute().data
    return periodos, materias, maestros


periodos, materias, maestros = cargar_catalogos()
materias_dict = {m["id"]: m["descripcion"] for m in materias}
maestros_dict = {m["clave"]: m["nombre_completo"] for m in maestros}
periodo_label = {p["id"]: etiqueta_periodo(p["id"], p.get("descripcion")) for p in periodos}


def elegir_clase(prefijo):
    """Selector de clase: periodo + filtro + lista. Devuelve (periodo, crn) o (None, None)."""
    periodo = st.selectbox("Periodo", [p["id"] for p in periodos],
                           format_func=lambda x: periodo_label.get(x, str(x)), key=f"{prefijo}_per")
    filtro = st.text_input("Filtrar por CRN, materia o grupo (opcional)", key=f"{prefijo}_f").strip().upper()
    clases = (client.table("clases").select("crn, grupo, materia_id")
              .eq("periodo_id", periodo).order("crn").execute().data)

    def etq(c):
        return f"CRN {c['crn']} · {c.get('grupo') or '—'} · {materias_dict.get(c['materia_id'], c['materia_id'] or '—')}"

    opciones = [c for c in clases if not filtro or filtro in etq(c).upper() or filtro in str(c["crn"])]
    opciones.sort(key=lambda c: (materias_dict.get(c["materia_id"], c["materia_id"] or "").upper(), c["crn"]))
    if not opciones:
        st.info("No hay clases que coincidan con el filtro.")
        return None, None

    st.caption(f"🔎 {len(opciones)} clase(s) encontrada(s). Elige una de la lista.")
    indices = [None] + list(range(len(opciones)))
    i = st.selectbox("Clase", indices,
                     format_func=lambda j: "— Elige una clase —" if j is None else etq(opciones[j]),
                     key=f"{prefijo}_sel")
    if i is None:
        return None, None
    return periodo, opciones[i]["crn"]


tab_arch, tab_del, tab_maestro, tab_materia, tab_bulk = st.tabs(
    ["📦 Archivar / Recuperar clases", "🗑️ Eliminar clase", "🗑️ Eliminar maestro",
     "🗑️ Eliminar materia", "📚 Archivar por nivel/programa"])

# ============================================
# ARCHIVAR / RECUPERAR
# ============================================
with tab_arch:
    st.markdown("**Archivar una clase** (se quita del sistema pero se puede recuperar)")
    per, crn = elegir_clase("arch")
    if crn and st.button("📦 Archivar esta clase", type="primary", key="btn_arch"):
        try:
            client.rpc("archivar_clase", {"p_crn": crn, "p_periodo": per, "p_usuario": usuario}).execute()
            st.success(f"📦 Clase {crn} archivada. Ya no aparece en el sistema, pero puedes recuperarla abajo.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"❌ No se pudo archivar: {e}")

    st.divider()
    st.markdown("**Clases archivadas**")
    st.info("Las clases archivadas se quitan del sistema (no aparecen en reportes, choques ni búsquedas), "
            "pero puedes recuperarlas aquí. Si pasan **30 días archivadas, se borran solas** de forma permanente.")
    archivadas = (client.table("clases_archivadas")
                  .select("crn, periodo_id, materia_id, archivado_por, archivado_en")
                  .order("archivado_en", desc=True).execute().data)
    if not archivadas:
        st.caption("No hay clases archivadas.")
    for a in archivadas:
        mat = materias_dict.get(a.get("materia_id"), a.get("materia_id") or "—")
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"CRN **{a['crn']}** · periodo {a['periodo_id']} · {mat} "
                    f"— archivada por {a.get('archivado_por') or '?'}")
        if c2.button("Recuperar", key=f"rec_{a['crn']}_{a['periodo_id']}"):
            try:
                client.rpc("recuperar_clase", {"p_crn": a["crn"], "p_periodo": a["periodo_id"]}).execute()
                st.success(f"✅ Clase {a['crn']} recuperada.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"❌ No se pudo recuperar: {e}")

# ============================================
# ELIMINAR CLASE (permanente)
# ============================================
with tab_del:
    st.warning("⚠️ Eliminar es **permanente**. Si quieres poder recuperarla, mejor archívala.")
    per, crn = elegir_clase("del")
    if crn:
        ok = st.checkbox("Entiendo que se borra para siempre", key="del_ok")
        if st.button("🗑️ Eliminar definitivamente", type="primary", disabled=not ok, key="btn_del"):
            try:
                client.table("clases").delete().eq("crn", crn).eq("periodo_id", per).execute()
                st.success(f"🗑️ Clase {crn} eliminada permanentemente.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ No se pudo eliminar: {e}")

# ============================================
# ELIMINAR MAESTRO (permanente, con candado)
# ============================================
with tab_maestro:
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

# ============================================
# ELIMINAR MATERIA (permanente, con candado)
# ============================================
with tab_materia:
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
                     "No se puede eliminar hasta que esas clases se reasignen a otra materia, se eliminen, "
                     "o se quiten del archivo.")
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
                    
# ============================================
# ARCHIVAR POR NIVEL / PROGRAMA (solo admin)
# ============================================
with tab_bulk:
    st.warning("⚠️ Esto archiva MUCHAS clases de una sola vez. Se pueden recuperar "
               "(una por una) desde la pestaña 'Archivar / Recuperar clases', y se "
               "borran solas a los 30 días.")

    rol = st.session_state.get("rol", "viewer")
    if rol != "admin":
        st.info("🔒 Solo el administrador puede archivar por nivel o programa.")
    elif not st.session_state.get("bulk_activo", False):
        st.info("Por seguridad, esta pestaña necesita que la actives manualmente.")
        if st.button("🔓 Activar herramientas de archivado masivo"):
            st.session_state["bulk_activo"] = True
            st.rerun()
    else:
        NIVELES_NOMBRE = {
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
                    format_func=lambda n: f"{NIVELES_NOMBRE.get(n, n)} ({n}) — {por_nivel[n]} clases")
                st.error(f"Vas a archivar **{por_nivel[nivel_sel]} clases** del nivel "
                         f"**{NIVELES_NOMBRE.get(nivel_sel, nivel_sel)}**.")
                conf = st.text_input("Para confirmar, escribe:  ARCHIVAR", key="conf_nivel")
                if st.button("📦 Archivar este nivel", type="primary",
                             disabled=(conf.strip().upper() != "ARCHIVAR"), key="btn_nivel"):
                    try:
                        n = client.rpc("archivar_por_nivel",
                                       {"p_nivel": nivel_sel, "p_usuario": usuario}).execute().data
                        st.success(f"✅ Se archivaron {n} clases del nivel {nivel_sel}. "
                                   "Puedes recuperarlas en la primera pestaña.")
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
                                   "Puedes recuperarlas en la primera pestaña.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ No se pudo archivar: {e}")
                        
        st.divider()
        st.subheader("📚 Archivar clases multi-carrera")
        st.caption("Las clases multi-carrera no tienen una carrera asignada (aparecen "
                   "como '(multi-carrera)' en reportes). No entran en 'nivel/programa' "
                   "de arriba, por eso se archivan aparte.")

        conteo_mc = client.rpc("conteo_multicarrera", {}).execute().data or []
        if not conteo_mc:
            st.info("No hay clases multi-carrera activas.")
        else:
            modo_mc = st.radio(
                "¿Qué quieres archivar?",
                ["Por nivel + periodo (más específico)", "Todo un periodo (más amplio)"],
                key="mc_modo",
            )

            NIVELES_NOMBRE = {
                "LX": "Licenciatura Ejecutiva", "NC": "Ciencias de la Salud",
                "PT": "Posgrado / Maestría", "L6": "Licenciatura",
                "LS": "Licenciatura", "B6": "Bachillerato", "6B": "Bachillerato",
                "(otro)": "Otro / sin nivel claro",
            }

            if modo_mc.startswith("Por nivel"):
                # Nivel + periodo: mostrar solo combinaciones que existen
                opciones = [(row["periodo"], row["nivel"], row["clases"]) for row in conteo_mc]
                etq = st.selectbox(
                    "Nivel y periodo a archivar",
                    range(len(opciones)),
                    format_func=lambda i: (
                        f"{NIVELES_NOMBRE.get(opciones[i][1], opciones[i][1])} "
                        f"({opciones[i][1]}) · periodo {opciones[i][0]} "
                        f"— {opciones[i][2]} clases"
                    ),
                    key="mc_sel_np",
                )
                per, niv, n_cl = opciones[etq]
                st.error(f"Vas a archivar **{n_cl} clases** multi-carrera del nivel "
                         f"**{NIVELES_NOMBRE.get(niv, niv)}** en el periodo **{per}**.")
                conf = st.text_input("Para confirmar, escribe:  ARCHIVAR", key="conf_mc_np")
                if st.button("📦 Archivar", type="primary",
                             disabled=(conf.strip().upper() != "ARCHIVAR"),
                             key="btn_mc_np"):
                    try:
                        n = client.rpc(
                            "archivar_multicarrera_por_nivel_periodo",
                            {"p_nivel": niv, "p_periodo": per, "p_usuario": usuario},
                        ).execute().data
                        st.success(f"✅ Se archivaron {n} clases multi-carrera. "
                                   "Puedes recuperarlas en la primera pestaña.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ No se pudo archivar: {e}")
            else:
                # Solo por periodo: sumar todas las claves por periodo
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
                        nom = NIVELES_NOMBRE.get(cod, cod)
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
                        st.success(f"✅ Se archivaron {n} clases multi-carrera. "
                                   "Puedes recuperarlas en la primera pestaña.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ No se pudo archivar: {e}")
            
            st.divider()
        if st.button("Cerrar herramientas de archivado masivo"):
            st.session_state["bulk_activo"] = False
            st.rerun()