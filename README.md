# Gestor de Clases UVM

Sistema web para administrar los horarios académicos del Campus UVM Querétaro. Permite cargar los reportes de Banner, detectar conflictos de salones, gestionar la carga docente y exportar la información en el mismo formato del sistema oficial.

**URL en producción:** https://universidad-clases-uvm.streamlit.app

---

## Índice

1. [Descripción general](#descripción-general)
2. [Stack tecnológico](#stack-tecnológico)
3. [Arquitectura](#arquitectura)
4. [Requisitos previos](#requisitos-previos)
5. [Instalación local](#instalación-local)
6. [Estructura del proyecto](#estructura-del-proyecto)
7. [Base de datos (Supabase)](#base-de-datos-supabase)
8. [Autenticación y roles](#autenticación-y-roles)
9. [Cron jobs automáticos](#cron-jobs-automáticos)
10. [Cómo desplegar cambios](#cómo-desplegar-cambios)
11. [Cómo agregar nuevas funcionalidades](#cómo-agregar-nuevas-funcionalidades)
12. [Troubleshooting común](#troubleshooting-común)
13. [Handoff a nuevos desarrolladores](#handoff-a-nuevos-desarrolladores)

---

## Descripción general

El sistema replica y extiende la funcionalidad del reporte "Detalle Mega Figpos" de Banner. Sus objetivos son:

- **Centralizar** en una sola interfaz la información de clases, maestros, salones, materias y periodos académicos
- **Detectar** automáticamente choques de horarios entre salones
- **Facilitar** la edición manual de asignaciones (por ejemplo, cuando la coordinadora necesita reasignar un salón)
- **Archivar** históricos de clases vencidas para consulta posterior
- **Exportar** los datos actualizados en el mismo formato de Banner

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Frontend/UI | [Streamlit](https://streamlit.io/) (Python) |
| Base de datos | [Supabase](https://supabase.com/) (PostgreSQL + Auth + Realtime) |
| Análisis de datos | Pandas, NumPy |
| Visualizaciones | Plotly Express, Plotly Graph Objects |
| Manipulación de Excel | openpyxl, pandas |
| Hosting | [Streamlit Community Cloud](https://streamlit.io/cloud) (gratis) |
| Control de versiones | Git + GitHub |

---

## Arquitectura

```
┌─────────────────┐        ┌────────────────────┐        ┌─────────────────┐
│    Navegador    │───────▶│  Streamlit Cloud   │───────▶│    Supabase     │
│  (usuario web)  │◀───────│  (streamlit_app)   │◀───────│  (PostgreSQL)   │
└─────────────────┘        └────────────────────┘        └─────────────────┘
                                     │
                                     │ Vía service_role key
                                     ▼
                           ┌────────────────────┐
                           │   Cron jobs cada   │
                           │  noche (3:00 AM)   │
                           └────────────────────┘
```

- El navegador del usuario habla con Streamlit Cloud (donde corre el código Python).
- Streamlit habla con Supabase usando la `service_role` key (guardada como secret).
- Supabase corre cron jobs internos cada noche para archivar clases vencidas.

---

## Requisitos previos

Para trabajar en el proyecto localmente necesitas:

- **Python 3.11 o superior** ([python.org](https://www.python.org/downloads/))
- **Git** ([git-scm.com](https://git-scm.com/downloads))
- **Visual Studio Code** (recomendado) o cualquier editor de código
- **Cuenta de GitHub** con acceso al repo `CarlosVeneRu/universidad-clases`
- **Cuenta de Supabase** con acceso al proyecto `ndyndjmzdinerttxgedm` (para modificar la BD)
- **Cuenta de Streamlit Community Cloud** vinculada a GitHub (para deploy)

---

## Instalación local

### 1. Clonar el repositorio

```bash
git clone https://github.com/CarlosVeneRu/universidad-clases.git
cd universidad-clases
```

### 2. Crear entorno virtual

```bash
python -m venv venv
```

**En Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
```

**En macOS/Linux:**
```bash
source venv/bin/activate
```

Si en Windows te da error de política de ejecución, corre una vez:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Crea un archivo `.env` en la raíz del proyecto con este contenido:

```
SUPABASE_URL=https://ndyndjmzdinerttxgedm.supabase.co
SUPABASE_ANON_KEY=[la service_role key del proyecto Supabase]
```

**IMPORTANTE:** El archivo `.env` NO se sube a GitHub (está en `.gitignore`). Cada dev debe tenerlo local.

Para obtener la `SUPABASE_ANON_KEY`:
1. Ve al [dashboard de Supabase](https://supabase.com/dashboard/project/ndyndjmzdinerttxgedm)
2. Settings → API
3. Copia la key `service_role` (la que dice "secret")

### 5. Correr el sistema

```bash
streamlit run streamlit_app.py
```

Se abre automáticamente en `http://localhost:8501`.

---

## Estructura del proyecto

```
universidad-clases/
├── streamlit_app.py           ← Punto de entrada (login + navegación)
├── requirements.txt            ← Dependencias de Python
├── .env                        ← Variables locales (NO se sube a Git)
├── .gitignore                  ← Archivos ignorados por Git
├── README.md                   ← Este archivo
│
├── .streamlit/
│   └── config.toml             ← Config de Streamlit (tema, colores)
│
├── assets/
│   └── uvm_logo.png            ← Logo institucional
│
├── paginas/                    ← Páginas del sistema (una por archivo)
│   ├── inicio.py               ← Página de inicio con métricas
│   ├── buscar_clases.py        ← Búsqueda avanzada de clases
│   ├── maestros.py             ← Vista de maestros y carga docente
│   ├── salones.py              ← Vista de salones y uso
│   ├── materias.py             ← Catálogo de materias
│   ├── choques.py              ← Detección de choques de salones
│   ├── reportes.py             ← Reportes con gráficas
│   ├── exportar.py             ← Exportación a Excel
│   ├── editar_clases.py        ← Editor de clases individuales
│   ├── agregar_clase.py        ← Crear una clase manualmente
│   ├── archivar_eliminar.py    ← Gestión de archivado y eliminación
│   ├── subir_excel.py          ← Carga masiva desde Excel de Banner
│   └── administrar_usuarios.py ← Admin de cuentas (solo rol admin)
│
└── app/
    ├── loaders/
    │   └── cargar_clases_web.py  ← Lógica de análisis y carga del Excel
    │
    └── utils/
        ├── queries.py           ← Funciones que hablan con Supabase
        ├── supabase_client.py   ← Cliente Supabase con .env
        ├── ui.py                ← Utilidades de interfaz (encabezado, etc.)
        └── horarios.py          ← Utilidades de horarios y cuadrículas
```

### Convenciones

- **Cada página** es un archivo `.py` independiente en `paginas/`
- Las páginas se registran en `streamlit_app.py` como `st.Page(...)`
- Las **consultas a Supabase** están centralizadas en `app/utils/queries.py`
- Las **RPCs custom** de Supabase se llaman desde `queries.py` con `client.rpc("nombre_rpc", {...})`

---

## Base de datos (Supabase)

### Proyecto Supabase

**Correo asociado a Supabase:**
uvmqueretarooculus@gmail.com
Juriquilla_2026_XD

**Contraseña de Supabase:**
Arrow_011

- **URL:** https://supabase.com/dashboard/project/ndyndjmzdinerttxgedm
- **Región:** us-west-2
- **Plan:** Free
- **Nombre:** Organización Salones (dentro de organización "UVM DATABASES")

### Tablas principales

| Tabla | Descripción |
|---|---|
| `clases` | Clases activas del sistema (las que están en curso o futuras) |
| `clases_archivadas` | Histórico de clases vencidas (con snapshot de sus horarios en JSON) |
| `horarios` | Horarios de cada clase (día, hora, salón). Se borran en cascada al archivar |
| `maestros` | Docentes con su clave (docente_id) y nombre |
| `materias` | Catálogo de materias con descripción |
| `salones` | Catálogo de salones físicos con capacidad |
| `carreras` | Programas académicos (con FK a `programas` y `niveles`) |
| `programas` | Programas de estudio (Lic, Bachillerato, etc.) |
| `niveles_academicos` | Niveles como L6, LS, LX, 6B, NC, PT |
| `periodos` | Periodos administrativos (ej. 202680) |
| `usuarios` | Cuentas del sistema con hash bcrypt |
| `campus` | Sedes universitarias |

### Vistas

- `v_clases_con_nivel` — Clases con su nivel resuelto (vía carrera→programa)
- `v_horarios_con_nivel` — Horarios enriquecidos con nivel académico
- `clases_agrupadas` — Agrupa clases divididas (mismos maestro/materia con grupos A/B)
- `periodos_con_estado` — Periodos con estado "activo" o "concluido"

### RPCs importantes (funciones SQL custom)

| RPC | Uso |
|---|---|
| `verificar_login(p_usuario, p_password)` | Login con bcrypt |
| `buscar_clases_con_detalle(...)` | Búsqueda con filtros y paginación |
| `buscar_archivadas_con_detalle(...)` | Igual pero sobre archivadas |
| `archivar_clases_vencidas()` | Mueve clases con `fecha_fin < hoy` a archivadas |
| `archivar_clase(crn, periodo, usuario)` | Archiva UNA clase específica |
| `restaurar_clase(crn, periodo)` | Regresa una archivada a activa |
| `uso_salones_por_rango(fi, ff, incluir_archivadas)` | Estadísticas de uso de salones |
| `disponibilidad_de_salon(salon, fi, ff)` | Qué horas están ocupadas |
| `clasificar_choque(...)` | Categoriza choques de salones |
| `conflictos_agrupados_salon()` | Choques agrupados con union-find |
| `borrar_periodos_vacios()` | Elimina periodos sin clases |
| `limpiar_archivadas_viejas()` | Borra archivadas de +30 días |
| `listar_usuarios()` | Lista usuarios sin exponer hash |
| `crear_usuario(usuario, nombre, password, rol)` | Nuevo usuario con bcrypt |
| `actualizar_usuario(...)` | Actualiza datos (con reglas de seguridad) |
| `cambiar_password_usuario(id, password)` | Reset password (bcrypt) |
| `eliminar_usuario(id, usuario_actual)` | Elimina usuario (con validaciones) |
| `archivar_por_nivel(nivel)` | Archivado masivo por nivel |
| `archivar_por_programa(programa)` | Archivado masivo por programa |

### Cómo modificar la BD

**NUNCA modifiques tablas manualmente en producción.** Todo cambio debe:

1. Hacerse como **migración SQL** (ver ejemplos en la carpeta `supabase/migrations` del dashboard)
2. Probarse en un branch de desarrollo si es posible
3. Documentarse en este README

Para aplicar una migración desde el dashboard:
- Ve a **SQL Editor** en Supabase
- Escribe el SQL
- Presiona "Run"

---

## Autenticación y roles

El sistema usa **autenticación propia** (tabla `usuarios`), NO el sistema de Auth de Supabase.

### Roles disponibles

| Rol | Permisos |
|---|---|
| `admin` | Todo: crear/editar/eliminar usuarios, cargar Excel, ver todo |
| `moderador` | Editar clases, agregar clases, archivar. NO gestiona usuarios ni sube Excel |
| `viewer` | Solo lectura: puede ver todas las páginas de consulta |

### Contraseñas

- Se hashean con **bcrypt** (`crypt() + gen_salt('bf')` en pgcrypto)
- Mínimo 6 caracteres (validado en la RPC `crear_usuario`)
- **NUNCA** se almacenan en texto plano

### Reglas de seguridad implementadas

- No puedes eliminar tu propia cuenta
- No puedes cambiar tu propio rol
- No se puede eliminar/desactivar al último admin activo del sistema

---

## Cron jobs automáticos

Configurados en Supabase (extensión `pg_cron`). Ver con:

```sql
SELECT jobid, jobname, schedule, active FROM cron.job;
```

| Job | Horario | Función |
|---|---|---|
| `archivar-vencidas-diario` | 03:00 AM diario | Archiva clases con `fecha_fin < CURRENT_DATE` |
| `limpiar_archivadas_viejas` | 03:00 AM diario | Borra archivadas de más de 30 días |
| `borrar-periodos-vacios-diario` | 03:15 AM diario | Elimina periodos sin clases |

Historial de ejecuciones:
```sql
SELECT * FROM cron.job_run_details ORDER BY start_time DESC LIMIT 20;
```

---

## Cómo desplegar cambios

El sistema tiene **auto-deploy** vinculado a GitHub. Cualquier `git push` a la rama `main` se despliega automáticamente en 1-2 minutos.

### Flujo estándar

```bash
# 1. Hacer cambios en el código (con VS Code)

# 2. Verificar que compilen
python -m py_compile paginas/tu_archivo.py

# 3. Probar local
streamlit run streamlit_app.py

# 4. Si todo funciona, subir a GitHub
git add .
git commit -m "Descripción clara del cambio"
git push
```

### Ver estado del deploy

- Dashboard: https://share.streamlit.io/
- Ahí sale el log en vivo y errores si algo falla

### Rollback si algo se rompe

```bash
# Ver los últimos commits
git log --oneline -10

# Revertir al commit anterior
git revert HEAD
git push
```

Streamlit Cloud redesplega automáticamente con la versión revertida.

---

## Cómo agregar nuevas funcionalidades

### Ejemplo: crear una nueva página

1. **Crear el archivo** en `paginas/nueva_pagina.py`:

```python
"""
Descripción de la nueva página.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from app.utils.ui import encabezado
from app.utils.queries import get_client

encabezado("Título de la Página", "Subtítulo descriptivo", "📊")

client = get_client()

# Tu lógica aquí
st.subheader("Sección de ejemplo")
datos = client.table("clases").select("crn").limit(10).execute().data
st.write(f"Hay {len(datos)} clases mostradas.")
```

2. **Registrar la página** en `streamlit_app.py`:

Busca el bloque de `st.Page(...)` y agrega:

```python
nueva = st.Page("paginas/nueva_pagina.py", title="Nueva Página", icon="📊")
```

3. **Añadirla al menú** según el rol:

```python
menu = {
    "Principal": [inicio, buscar, maestros, salones, nueva],  # ← aquí
    ...
}
```

4. **Probar local** con `streamlit run streamlit_app.py`, y si funciona, hacer push.

### Ejemplo: agregar una nueva RPC en Supabase

1. Ve al **SQL Editor** de Supabase
2. Escribe la función con `CREATE OR REPLACE FUNCTION ...`
3. Ejecuta con "Run"
4. Desde Python, llámala:

```python
resultado = client.rpc("nombre_rpc", {"p_param1": valor1}).execute().data
```

### Ejemplo: agregar una nueva variable de entorno

1. Local: agregarla al `.env`
2. Producción: agregarla en el dashboard de Streamlit Cloud:
   - https://share.streamlit.io/
   - Tu app → menu (⋮) → Settings → Secrets
   - Formato TOML: `NUEVA_VAR = "valor"`

---

## Troubleshooting común

### "No se pudo verificar el login: Legacy API keys are disabled"

**Causa:** Alguien desactivó las legacy keys en Supabase.

**Solución:**
1. Ve a Settings → API Keys → pestaña "Legacy anon, service_role API keys"
2. Presiona **"Re-enable JWT-based API keys"**
3. Escribe `re-enable` y confirma

### "ModuleNotFoundError: No module named 'X'"

**Causa:** Falta instalar dependencias.

**Solución:**
```bash
venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
```

### El deploy en Streamlit Cloud falla

**Solución:**
1. Ver el log en https://share.streamlit.io/
2. Errores comunes:
   - Falta una librería en `requirements.txt` → agrégala
   - Python version incompatible → cambiar en Advanced Settings a 3.11 o 3.12
   - Secrets mal configurados → verificar formato TOML

### El cron no está ejecutando

**Solución:**
```sql
-- Ver últimas ejecuciones
SELECT * FROM cron.job_run_details 
ORDER BY start_time DESC LIMIT 10;
```

Si hay errores, revisar el mensaje y corregir la función correspondiente.

### Las clases archivadas están duplicadas

**Causa:** Se ejecutó `archivar_clases_vencidas()` manualmente sin verificar duplicados.

**Solución:** Ejecutar en SQL Editor:
```sql
DELETE FROM clases_archivadas a
USING clases_archivadas b
WHERE a.ctid < b.ctid
  AND a.crn = b.crn
  AND a.periodo_id = b.periodo_id;
```

### Un usuario olvidó su contraseña

**Solución:** Como admin, ve a **Administrar cuentas → Cambiar contraseña**, selecciona al usuario y ponle una temporal. Dile que la cambie al entrar.

---

## Handoff a nuevos desarrolladores

Si vas a transferir el proyecto a otra persona, esta es la lista de qué darle:

### Acceso a compartir

1. **GitHub:**
   - Invítalo al repo como colaborador: https://github.com/CarlosVeneRu/universidad-clases/settings/access
   - O transfiere la propiedad: Settings → Danger Zone → Transfer ownership

2. **Supabase:**
   - Dashboard → Settings → Team → Invite member
   - Ponerle rol "Owner" o "Administrator"

3. **Streamlit Cloud:**
   - Streamlit Cloud usa la sesión de GitHub. Si le pasas el repo, solo tendrá que loguearse con su GitHub y él puede reclamar el deploy.
   - O transferir ownership: Settings de la app → Add owner

### Documentación clave

- **Este README** (léelo completo)
- **Manual de usuario** (`MANUAL_USUARIO.md`) — para saber qué espera el usuario final
- **Historial de commits** — cada commit tiene una descripción de qué cambió

### Checklist de "primer día"

- [ ] Clonar el repo
- [ ] Crear venv e instalar dependencias
- [ ] Configurar `.env` local con las keys de Supabase
- [ ] Correr `streamlit run streamlit_app.py` y verificar que arranca
- [ ] Entrar con usuario admin y explorar todas las páginas
- [ ] Revisar el dashboard de Supabase (tablas, RPCs, cron jobs)
- [ ] Leer los últimos 20 commits para entender qué se ha cambiado recientemente
- [ ] Hacer un cambio pequeño de prueba (ej. cambiar el título de una página), commit y push, y verificar que se deploya

### Pendientes al día del handoff (Julio 2026)

Preguntas para aclarar con la coordinadora institucional:
- Códigos raros de `clave_periodo`: 1TU, 5CD, ECD, HCD, QCD, VCD, YCD, WQ, ALS, ILS, DNC, INC, HNC, ANC, ONC, 1NL, 3NL, OL6, OLS
- Qué representan los grupos 97A, 97B en materias del periodo 202680
- Confirmar tratamiento de materias duplicadas legítimas (mismo nombre, distintos IDs por versión/carrera)

Ya confirmado con coordinadora:
- Figpos = SEMESTRAL, C3YC2 = CUATRIMESTRAL
- Borrado automático de periodos vacíos aprobado

### Contacto original

- **Desarrollador original:** Carlos Venegas
- **Correo:** Carlos_Venegas_01@Outlook.com
- **LinkedIn:** https://www.linkedin.com/in/carlosmaximilianovenegasrubio/
- **Institución:** UVM Campus Querétaro
- **Repo:** https://github.com/CarlosVeneRu/universidad-clases

---