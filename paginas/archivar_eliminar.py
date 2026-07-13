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
    # Streamlit no deja modificar el valor de un widget ya instanciado en la misma corrida,
    # pero sí deja borrar su key. Al borrarla, en el siguiente rerun el checkbox nace limpio.
    for crn, per in claves:
        k = f"{prefijo}_chk_{crn}_{per}"
        if k in st.session_state:
            del st.session_state[k]


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
                        st.success(f"🗑️ {n_ok} eliminada(s) permanentemente.")
                    if errs:
                        st.error("; ".join(errs[:5]))
                    st.rerun()

    elif seccion == "maestro":
        st.markdown("### 👨‍🏫 Eliminar maestro")
        st.warning("Al eliminar un maestro, todas sus clases quedan con 'sin_docente = TRUE' (no se borran).")

        opciones = [""] + [f"{m['nombre_completo']} · {m['clave']}" for m in maestros]
        etq = st.selectbox("Maestro a eliminar", opciones, key="del_maestro_sel")
        if etq:
            clave = int(etq.split("·")[-1].strip())
            if st.button(f"🗑️ Eliminar maestro {clave}", type="primary", key="btn_del_maestro"):
                try:
                    # Marcar sus clases como sin docente
                    client.table("clases").update({"maestro_clave": None, "sin_docente": True}).eq("maestro_clave", clave).execute()
                    client.table("maestros").delete().eq("clave", clave).execute()
                    st.success(f"✅ Maestro {clave} eliminado.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ No se pudo eliminar: {e}")

    elif seccion == "materia":
        st.markdown("### 📚 Eliminar materia")
        st.warning("Solo se pueden eliminar materias sin clases asociadas.")

        opciones = [""] + [f"{mat['descripcion']} · {mat['id']}" for mat in materias]
        etq = st.selectbox("Materia a eliminar", opciones, key="del_materia_sel")
        if etq:
            mat_id = etq.split("·")[-1].strip()
            n = client.table("clases").select("crn", count="exact").eq("materia_id", mat_id).execute().count
            if n and n > 0:
                st.error(f"No se puede eliminar: la materia tiene {n} clases activas.")
            else:
                if st.button(f"🗑️ Eliminar materia {mat_id}", type="primary", key="btn_del_materia"):
                    try:
                        client.table("materias").delete().eq("id", mat_id).execute()
                        st.success(f"✅ Materia {mat_id} eliminada.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ No se pudo eliminar: {e}")

    elif seccion == "masivo":
        st.markdown("### 📦 Archivado masivo")
        st.warning("⚠️ Estas herramientas afectan MUCHAS clases de una sola vez. "
                   "Las de archivado se pueden recuperar; las de eliminar del archivo NO.")

        rol = st.session_state.get("rol", "viewer")
        if rol != "admin":
            st.info("🔒 Solo el administrador puede usar el archivado masivo.")
        elif not st.session_state.get("bulk_activo", False):
            st.info("Por seguridad, esta sección necesita que la actives manualmente.")
            if st.button("🔓 Activar herramientas de archivado masivo"):
                st.session_state["bulk_activo"] = True
                st.rerun()
        else:
            # Elegir sobre qué tabla operar
            modo_op = st.radio(
                "¿Sobre qué quieres operar?",
                ["Clases activas (archivar)", "Clases archivadas (eliminar o recuperar)"],
                key="masivo_operacion",
                horizontal=True,
            )

            # ============================================================
            # A) SOBRE CLASES ACTIVAS — Archivar
            # ============================================================
            if modo_op.startswith("Clases activas"):
                st.markdown("#### 📂 Origen: clases activas")
                por_nivel = client.rpc("conteo_por_nivel", {}).execute().data or []
                programas = client.rpc("conteo_programas", {}).execute().data or []

                submodo = st.radio(
                    "¿Qué quieres archivar?",
                    ["Un nivel académico", "Un programa (carrera)"],
                    key="masivo_act_submodo",
                )

                if submodo == "Un nivel académico":
                    if not por_nivel:
                        st.info("No hay clases activas para archivar.")
                    else:
                        opciones_niv = [row["nivel"] for row in por_nivel]
                        detalle = {row["nivel"]: row for row in por_nivel}

                        def _etq_niv(cod):
                            d = detalle[cod]
                            partes = []
                            if d["con_carrera"]:
                                partes.append(f"{d['con_carrera']} con carrera")
                            if d["multicarrera"]:
                                partes.append(f"{d['multicarrera']} multicarrera")
                            desglose = " + ".join(partes) if partes else "sin desglose"
                            return f"{NIVELES_LEGIBLES.get(cod, cod)} ({cod}) — {d['total']} clases ({desglose})"

                        nivel_sel = st.selectbox("Nivel a archivar", opciones_niv,
                                                 format_func=_etq_niv, key="masivo_act_niv")
                        d = detalle[nivel_sel]
                        st.error(f"Vas a archivar **{d['total']} clases** del nivel "
                                 f"**{NIVELES_LEGIBLES.get(nivel_sel, nivel_sel)}** "
                                 f"({d['con_carrera']} con carrera + {d['multicarrera']} multicarrera).")
                        conf = st.text_input("Para confirmar, escribe:  ARCHIVAR", key="conf_act_niv")
                        if st.button("📦 Archivar este nivel", type="primary",
                                     disabled=(conf.strip().upper() != "ARCHIVAR"), key="btn_act_niv"):
                            try:
                                n = client.rpc("archivar_por_nivel",
                                               {"p_nivel": nivel_sel, "p_usuario": usuario}).execute().data
                                st.success(f"✅ Se archivaron {n} clases del nivel {nivel_sel}. "
                                           "Puedes recuperarlas en '♻️ Clases archivadas'.")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ No se pudo archivar: {e}")

                else:  # Por programa
                    if not programas:
                        st.info("No hay programas con clases activas.")
                    else:
                        mapa = {f"{pr['nombre']} · {pr['nivel']} — {pr['clases']} clases": pr for pr in programas}
                        etq = st.selectbox("Programa a archivar", list(mapa.keys()), key="masivo_act_prog")
                        prog = mapa[etq]
                        st.error(f"Vas a archivar **{prog['clases']} clases** del programa **{prog['nombre']}**.")
                        conf = st.text_input("Para confirmar, escribe:  ARCHIVAR", key="conf_act_prog")
                        if st.button("📦 Archivar este programa", type="primary",
                                     disabled=(conf.strip().upper() != "ARCHIVAR"), key="btn_act_prog"):
                            try:
                                n = client.rpc("archivar_por_programa",
                                               {"p_carrera_id": prog["carrera_id"], "p_usuario": usuario}).execute().data
                                st.success(f"✅ Se archivaron {n} clases del programa {prog['nombre']}. "
                                           "Puedes recuperarlas en '♻️ Clases archivadas'.")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ No se pudo archivar: {e}")

            # ============================================================
            # B) SOBRE CLASES ARCHIVADAS — Eliminar del archivo o Recuperar
            # ============================================================
            else:
                st.markdown("#### ♻️ Origen: clases archivadas")
                por_nivel_arch = client.rpc("conteo_archivadas_por_nivel", {}).execute().data or []
                programas_arch = client.rpc("conteo_archivadas_por_programa", {}).execute().data or []

                accion = st.radio(
                    "¿Qué acción?",
                    ["🗑️ Eliminar del archivo (permanente)",
                     "♻️ Recuperar (volver a clases activas)"],
                    key="masivo_arch_accion",
                )
                es_eliminar = accion.startswith("🗑️")

                agrupar = st.radio(
                    "¿Agrupar por?",
                    ["Un nivel académico", "Un programa (carrera)"],
                    key="masivo_arch_agrupar",
                )

                if agrupar == "Un nivel académico":
                    if not por_nivel_arch:
                        st.info("No hay clases archivadas.")
                    else:
                        opciones_niv = [row["nivel"] for row in por_nivel_arch]
                        detalle = {row["nivel"]: row for row in por_nivel_arch}

                        def _etq_niv_arch(cod):
                            d = detalle[cod]
                            partes = []
                            if d["con_carrera"]:
                                partes.append(f"{d['con_carrera']} con carrera")
                            if d["multicarrera"]:
                                partes.append(f"{d['multicarrera']} multicarrera")
                            desglose = " + ".join(partes) if partes else "sin desglose"
                            return f"{NIVELES_LEGIBLES.get(cod, cod)} ({cod}) — {d['total']} clases ({desglose})"

                        nivel_sel = st.selectbox("Nivel", opciones_niv,
                                                 format_func=_etq_niv_arch, key="masivo_arch_niv")
                        d = detalle[nivel_sel]

                        if es_eliminar:
                            st.error(f"⚠️ Vas a **ELIMINAR PERMANENTEMENTE** {d['total']} clases del archivo "
                                     f"del nivel **{NIVELES_LEGIBLES.get(nivel_sel, nivel_sel)}**. "
                                     f"NO se pueden recuperar.")
                            conf = st.text_input("Para confirmar, escribe:  ELIMINAR", key="conf_arch_niv_del")
                            if st.button("🗑️ Eliminar del archivo", type="primary",
                                         disabled=(conf.strip().upper() != "ELIMINAR"), key="btn_arch_niv_del"):
                                try:
                                    n = client.rpc("eliminar_archivadas_por_nivel",
                                                   {"p_nivel": nivel_sel}).execute().data
                                    st.success(f"✅ Se eliminaron {n} clases del archivo.")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ No se pudo eliminar: {e}")
                        else:
                            st.warning(f"Vas a recuperar **{d['total']} clases** del archivo "
                                       f"al sistema activo (nivel **{NIVELES_LEGIBLES.get(nivel_sel, nivel_sel)}**).")
                            conf = st.text_input("Para confirmar, escribe:  RECUPERAR", key="conf_arch_niv_rec")
                            if st.button("♻️ Recuperar todas", type="primary",
                                         disabled=(conf.strip().upper() != "RECUPERAR"), key="btn_arch_niv_rec"):
                                try:
                                    n = client.rpc("recuperar_por_nivel",
                                                   {"p_nivel": nivel_sel}).execute().data
                                    st.success(f"✅ Se recuperaron {n} clases al sistema activo.")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ No se pudo recuperar: {e}")

                else:  # Por programa
                    if not programas_arch:
                        st.info("No hay programas con clases archivadas.")
                    else:
                        mapa = {f"{pr['nombre']} · {pr['nivel']} — {pr['clases']} clases": pr for pr in programas_arch}
                        etq = st.selectbox("Programa", list(mapa.keys()), key="masivo_arch_prog")
                        prog = mapa[etq]

                        if es_eliminar:
                            st.error(f"⚠️ Vas a **ELIMINAR PERMANENTEMENTE** {prog['clases']} clases del archivo "
                                     f"del programa **{prog['nombre']}**. NO se pueden recuperar.")
                            conf = st.text_input("Para confirmar, escribe:  ELIMINAR", key="conf_arch_prog_del")
                            if st.button("🗑️ Eliminar del archivo", type="primary",
                                         disabled=(conf.strip().upper() != "ELIMINAR"), key="btn_arch_prog_del"):
                                try:
                                    n = client.rpc("eliminar_archivadas_por_programa",
                                                   {"p_carrera_id": prog["carrera_id"]}).execute().data
                                    st.success(f"✅ Se eliminaron {n} clases del archivo.")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ No se pudo eliminar: {e}")
                        else:
                            st.warning(f"Vas a recuperar **{prog['clases']} clases** del programa "
                                       f"**{prog['nombre']}** al sistema activo.")
                            conf = st.text_input("Para confirmar, escribe:  RECUPERAR", key="conf_arch_prog_rec")
                            if st.button("♻️ Recuperar todas", type="primary",
                                         disabled=(conf.strip().upper() != "RECUPERAR"), key="btn_arch_prog_rec"):
                                try:
                                    n = client.rpc("recuperar_por_programa",
                                                   {"p_carrera_id": prog["carrera_id"]}).execute().data
                                    st.success(f"✅ Se recuperaron {n} clases al sistema activo.")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ No se pudo recuperar: {e}")

            st.divider()
            if st.button("Cerrar herramientas de archivado masivo"):
                st.session_state["bulk_activo"] = False
                st.rerun()