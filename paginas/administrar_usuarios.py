"""
Página de administración de cuentas del sistema.
SOLO accesible por usuarios con rol 'admin'.
Permite: crear, editar (nombre/rol/activo), cambiar contraseña y eliminar usuarios.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.utils.queries import get_client
from app.utils.ui import encabezado


# =========================================================================
# GATE DE ACCESO: doble verificación por si el menú se saltara
# =========================================================================
if st.session_state.get("rol") != "admin":
    st.error("🔒 Esta sección solo está disponible para usuarios con rol **Administrador**.")
    st.stop()


encabezado("Administrar cuentas", "Gestión de usuarios del sistema", "👤")

client = get_client()
USUARIO_ACTUAL = st.session_state.get("usuario", "")

ROLES = ["admin", "moderador", "viewer"]
ROL_LABELS = {
    "admin": "🛡️ Administrador",
    "moderador": "✏️ Moderador",
    "viewer": "👁️ Solo lectura",
}


def _cargar_usuarios():
    return client.rpc("listar_usuarios", {}).execute().data or []


# =========================================================================
# MENÚ LATERAL: elegir acción
# =========================================================================
col_menu, col_contenido = st.columns([1.2, 4])

with col_menu:
    st.markdown("**¿Qué quieres hacer?**")
    accion = st.radio(
        "Acciones",
        ["ver", "crear", "editar", "password", "eliminar"],
        format_func=lambda k: {
            "ver":       "👀 Ver todos los usuarios",
            "crear":     "➕ Crear usuario",
            "editar":    "✏️ Editar usuario",
            "password":  "🔑 Cambiar contraseña",
            "eliminar":  "🗑️ Eliminar usuario",
        }[k],
        label_visibility="collapsed",
        key="acc_admin_usu",
    )


with col_contenido:

    # ==============================================================
    # VER TODOS
    # ==============================================================
    if accion == "ver":
        st.markdown("### 👀 Todos los usuarios")
        usuarios = _cargar_usuarios()

        if not usuarios:
            st.info("No hay usuarios registrados.")
        else:
            filas = []
            for u in usuarios:
                filas.append({
                    "ID": u["id"],
                    "Usuario": u["usuario"],
                    "Nombre": u["nombre"],
                    "Rol": ROL_LABELS.get(u["rol"], u["rol"]),
                    "Estado": "✅ Activo" if u["activo"] else "❌ Inactivo",
                    "Creado": (u.get("created_at") or "")[:10],
                })
            df = pd.DataFrame(filas)
            st.dataframe(df, use_container_width=True, hide_index=True, height=460)

            # Métricas rápidas
            total = len(usuarios)
            admins = sum(1 for u in usuarios if u["rol"] == "admin" and u["activo"])
            moderadores = sum(1 for u in usuarios if u["rol"] == "moderador" and u["activo"])
            viewers = sum(1 for u in usuarios if u["rol"] == "viewer" and u["activo"])
            inactivos = sum(1 for u in usuarios if not u["activo"])

            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            with col_m1:
                st.metric("Total", total)
            with col_m2:
                st.metric("🛡️ Admins activos", admins)
            with col_m3:
                st.metric("✏️ Moderadores activos", moderadores)
            with col_m4:
                st.metric("👁️ Viewers activos", viewers)
            with col_m5:
                st.metric("❌ Inactivos", inactivos)


    # ==============================================================
    # CREAR
    # ==============================================================
    elif accion == "crear":
        st.markdown("### ➕ Crear nuevo usuario")
        st.caption("El nombre de usuario se guarda en minúsculas. La contraseña debe tener mínimo 6 caracteres.")

        with st.form("form_crear_usuario", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                nuevo_usuario = st.text_input("Usuario", placeholder="ej: juan.perez", key="crear_usu")
                nuevo_nombre = st.text_input("Nombre completo", placeholder="ej: Juan Pérez", key="crear_nom")
            with col_b:
                nuevo_password = st.text_input("Contraseña", type="password",
                                                placeholder="Mínimo 6 caracteres", key="crear_pw")
                nuevo_rol = st.selectbox("Rol", ROLES,
                                          format_func=lambda r: ROL_LABELS[r], key="crear_rol")

            enviar = st.form_submit_button("➕ Crear usuario", type="primary", use_container_width=True)

        if enviar:
            if not nuevo_usuario.strip() or not nuevo_nombre.strip():
                st.error("❌ Escribe el usuario y el nombre.")
            elif len(nuevo_password) < 6:
                st.error("❌ La contraseña debe tener al menos 6 caracteres.")
            else:
                try:
                    nid = client.rpc("crear_usuario", {
                        "p_usuario": nuevo_usuario,
                        "p_nombre": nuevo_nombre,
                        "p_password": nuevo_password,
                        "p_rol": nuevo_rol,
                    }).execute().data
                    st.success(f"✅ Usuario creado con ID {nid}: **{nuevo_usuario.lower().strip()}** ({ROL_LABELS[nuevo_rol]})")
                except Exception as e:
                    st.error(f"❌ No se pudo crear: {str(e)[:200]}")


    # ==============================================================
    # EDITAR (nombre / rol / activo)
    # ==============================================================
    elif accion == "editar":
        st.markdown("### ✏️ Editar usuario")

        usuarios = _cargar_usuarios()
        if not usuarios:
            st.info("No hay usuarios registrados.")
        else:
            opciones = [f"{u['usuario']} · {u['nombre']} · {ROL_LABELS.get(u['rol'], u['rol'])}"
                        for u in usuarios]
            idx = st.selectbox("Elige el usuario a editar", range(len(opciones)),
                               format_func=lambda i: opciones[i], key="edit_usu_sel")
            u = usuarios[idx]

            es_yo = (u["usuario"] == USUARIO_ACTUAL)
            if es_yo:
                st.info("ℹ️ Este es **tu propio usuario**. No puedes cambiar tu rol ni desactivarte.")

            with st.form("form_editar_usuario"):
                col_a, col_b = st.columns(2)
                with col_a:
                    nuevo_nombre = st.text_input("Nombre completo", value=u["nombre"], key="edit_nom")
                    if es_yo:
                        st.selectbox("Rol", [u["rol"]],
                                     format_func=lambda r: ROL_LABELS.get(r, r),
                                     disabled=True, key="edit_rol_ro")
                        nuevo_rol = u["rol"]
                    else:
                        nuevo_rol = st.selectbox("Rol", ROLES,
                                                  index=ROLES.index(u["rol"]) if u["rol"] in ROLES else 0,
                                                  format_func=lambda r: ROL_LABELS[r], key="edit_rol")
                with col_b:
                    st.text_input("Usuario (no editable)", value=u["usuario"], disabled=True, key="edit_usuario_ro")
                    if es_yo:
                        st.checkbox("Activo", value=u["activo"], disabled=True, key="edit_act_ro")
                        nuevo_activo = u["activo"]
                    else:
                        nuevo_activo = st.checkbox("Activo", value=u["activo"], key="edit_act")

                guardar = st.form_submit_button("💾 Guardar cambios", type="primary", use_container_width=True)

            if guardar:
                try:
                    client.rpc("actualizar_usuario", {
                        "p_id": u["id"],
                        "p_nombre": nuevo_nombre,
                        "p_rol": nuevo_rol,
                        "p_activo": nuevo_activo,
                        "p_usuario_actual": USUARIO_ACTUAL,
                    }).execute()
                    st.success(f"✅ Usuario **{u['usuario']}** actualizado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ No se pudo actualizar: {str(e)[:200]}")


    # ==============================================================
    # CAMBIAR CONTRASEÑA
    # ==============================================================
    elif accion == "password":
        st.markdown("### 🔑 Cambiar contraseña de un usuario")

        usuarios = _cargar_usuarios()
        if not usuarios:
            st.info("No hay usuarios registrados.")
        else:
            opciones = [f"{u['usuario']} · {u['nombre']} · {ROL_LABELS.get(u['rol'], u['rol'])}"
                        for u in usuarios]
            idx = st.selectbox("Elige el usuario", range(len(opciones)),
                               format_func=lambda i: opciones[i], key="pw_usu_sel")
            u = usuarios[idx]

            st.info(f"Vas a cambiar la contraseña de **{u['usuario']}** ({u['nombre']}).")

            with st.form("form_password"):
                nueva_pw = st.text_input("Nueva contraseña", type="password",
                                          placeholder="Mínimo 6 caracteres", key="pw_new")
                confirmar_pw = st.text_input("Confirma la contraseña", type="password", key="pw_conf")
                cambiar = st.form_submit_button("🔑 Cambiar contraseña",
                                                 type="primary", use_container_width=True)

            if cambiar:
                if len(nueva_pw) < 6:
                    st.error("❌ La contraseña debe tener al menos 6 caracteres.")
                elif nueva_pw != confirmar_pw:
                    st.error("❌ Las contraseñas no coinciden.")
                else:
                    try:
                        client.rpc("cambiar_password_usuario", {
                            "p_id": u["id"],
                            "p_nueva_password": nueva_pw,
                        }).execute()
                        st.success(f"✅ Contraseña de **{u['usuario']}** actualizada.")
                    except Exception as e:
                        st.error(f"❌ No se pudo cambiar: {str(e)[:200]}")


    # ==============================================================
    # ELIMINAR
    # ==============================================================
    elif accion == "eliminar":
        st.markdown("### 🗑️ Eliminar usuario")
        st.warning("⚠️ La eliminación es **permanente**. Si solo quieres desactivar temporalmente, "
                   "usa la opción **Editar usuario** y desmarca **Activo**.")

        usuarios = _cargar_usuarios()
        # Ocultar al usuario actual del selector (para evitar tentaciones)
        usuarios_elim = [u for u in usuarios if u["usuario"] != USUARIO_ACTUAL]

        if not usuarios_elim:
            st.info("No hay usuarios eliminables (aparte del tuyo).")
        else:
            opciones = [f"{u['usuario']} · {u['nombre']} · {ROL_LABELS.get(u['rol'], u['rol'])}"
                        for u in usuarios_elim]
            idx = st.selectbox("Elige el usuario a eliminar", range(len(opciones)),
                               format_func=lambda i: opciones[i], key="del_usu_sel")
            u = usuarios_elim[idx]

            st.error(f"⚠️ Vas a eliminar **permanentemente** al usuario **{u['usuario']}** ({u['nombre']}).")

            confirmo = st.checkbox(
                f"✓ Confirmo que quiero eliminar permanentemente al usuario **{u['usuario']}**.",
                key="conf_del_usu"
            )

            if st.button(f"🗑️ Eliminar {u['usuario']}", type="primary",
                         disabled=not confirmo, key="btn_del_usu"):
                try:
                    client.rpc("eliminar_usuario", {
                        "p_id": u["id"],
                        "p_usuario_actual": USUARIO_ACTUAL,
                    }).execute()
                    st.success(f"✅ Usuario **{u['usuario']}** eliminado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ No se pudo eliminar: {str(e)[:200]}")