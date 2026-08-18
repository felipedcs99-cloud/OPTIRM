# utils.py
import io
import json
import hashlib
from datetime import datetime

import pandas as pd
import streamlit as st
from shapely.geometry import shape, Point

# ============================================================================
# CONSTANTES Y CONFIGURACIÓN
# ============================================================================

COLUMNAS_REQUERIDAS = [
    "id_pedido",
    "cliente",
    "lat",
    "lon",
    "direccion",
    "peso_kg",
    "codigo_transporte_sap",
]

FLOTA_CONFIG = {
    "Camioneta": {"cantidad": 15, "capacidad_kg": 1300, "color": "#2E86C1"},
    "Camión": {"cantidad": 12, "capacidad_kg": 5500, "color": "#C0392B"},
}

CENTRO_DEFECTO = [-33.5975, -70.5789]
ZOOM_DEFECTO = 11

# ============================================================================
# INICIALIZACIÓN DEL ESTADO
# ============================================================================

def inicializar_estado():
    """Crea todas las claves de session_state con valores por defecto."""
    defaults = {
        "df_pedidos": pd.DataFrame(columns=COLUMNAS_REQUERIDAS),
        "asignaciones": {},
        "mapa_center": CENTRO_DEFECTO,
        "mapa_zoom": ZOOM_DEFECTO,
        "geometrias_dibujadas": [],
        "hash_dibujos": "",
        "seleccion_por_clics": set(),
        "seleccion_por_figuras": set(),
        "pedidos_seleccionados": [],
        "modo_seleccion": "Agregar a la selección",
        "ultimo_tooltip_clickeado": None,
        "vehiculo_activo_tipo": "Camioneta",
        "vehiculo_activo_num": 1,
        "geojson_comunas": None,
        "ultimo_error_carga": None,
        "df_editor_actual": pd.DataFrame(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# ============================================================================
# CARGA Y VALIDACIÓN DE ARCHIVOS
# ============================================================================

def leer_archivo_pedidos(archivo_subido):
    if archivo_subido is None:
        return None, "No se seleccionó ningún archivo."

    nombre = archivo_subido.name.lower()
    try:
        if nombre.endswith((".xlsx", ".xls")):
            df = pd.read_excel(archivo_subido, engine="openpyxl")
        elif nombre.endswith(".csv"):
            contenido = archivo_subido.read()
            try:
                df = pd.read_csv(io.BytesIO(contenido), sep=";")
                if df.shape[1] == 1:
                    raise ValueError("Separador incorrecto")
            except Exception:
                df = pd.read_csv(io.BytesIO(contenido), sep=",")
        else:
            return None, "Formato no soportado. Usa .xlsx o .csv."
    except Exception as e:
        return None, f"Error al leer: {e}"

    if df is None or df.empty:
        return None, "El archivo está vacío."

    df.columns = [str(c).strip().lower() for c in df.columns]
    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        return None, f"Faltan columnas: {', '.join(faltantes)}."

    df = df[COLUMNAS_REQUERIDAS].copy()
    for col in ["lat", "lon", "peso_kg"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["lat", "lon", "peso_kg"])
    df = df[(df["lat"].between(-90, 90)) & (df["lon"].between(-180, 180))]
    if df.empty:
        return None, "No hay pedidos con coordenadas válidas."
    df["id_pedido"] = df["id_pedido"].astype(str)
    return df.reset_index(drop=True), None

@st.cache_data
def cargar_geojson(contenido_bytes):
    try:
        return json.loads(contenido_bytes)
    except Exception as e:
        return None

# ============================================================================
# LÓGICA DE FLOTA Y CAPACIDAD
# ============================================================================

def listar_unidades_flota():
    unidades = []
    for tipo, cfg in FLOTA_CONFIG.items():
        for n in range(1, cfg["cantidad"] + 1):
            unidades.append(f"{tipo}-{n:02d}")
    return unidades

def obtener_capacidad_unidad(clave_unidad):
    tipo = clave_unidad.split("-")[0]
    return FLOTA_CONFIG.get(tipo, {}).get("capacidad_kg", 0)

def calcular_carga_por_unidad():
    df = st.session_state.df_pedidos
    asignaciones = st.session_state.asignaciones
    filas = []
    for unidad in listar_unidades_flota():
        ids_asignados = [pid for pid, u in asignaciones.items() if u == unidad]
        peso_total = df[df["id_pedido"].isin(ids_asignados)]["peso_kg"].sum() if ids_asignados else 0.0
        capacidad = obtener_capacidad_unidad(unidad)
        porcentaje = (peso_total / capacidad * 100) if capacidad else 0
        filas.append({
            "unidad": unidad,
            "tipo": unidad.split("-")[0],
            "peso_total_kg": round(float(peso_total), 1),
            "capacidad_kg": capacidad,
            "porcentaje_uso": round(porcentaje, 1),
            "n_pedidos": len(ids_asignados),
        })
    return pd.DataFrame(filas)

def asignar_pedidos_a_vehiculo(ids_pedidos, unidad):
    for pid in ids_pedidos:
        st.session_state.asignaciones[pid] = unidad

def liberar_pedidos(ids_pedidos):
    for pid in ids_pedidos:
        st.session_state.asignaciones.pop(pid, None)

# ============================================================================
# EXPORTACIÓN
# ============================================================================

def generar_excel_exportacion():
    df = st.session_state.df_pedidos.copy()
    df["unidad_asignada"] = df["id_pedido"].map(st.session_state.asignaciones).fillna("SIN ASIGNAR")
    df["fecha_exportacion"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    resumen = calcular_carga_por_unidad()
    resumen = resumen[resumen["n_pedidos"] > 0]
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Plan_Despacho", index=False)
        resumen.to_excel(writer, sheet_name="Resumen_Flota", index=False)
    buffer.seek(0)
    return buffer

# ============================================================================
# SELECCIÓN POR GEOMETRÍAS
# ============================================================================

def obtener_ids_dentro_de_geometrias(geometrias):
    df = st.session_state.df_pedidos
    if df.empty or not geometrias:
        return []
    ids_dentro = set()
    for feature in geometrias:
        try:
            geom = shape(feature["geometry"])
        except Exception:
            continue
        for _, fila in df.iterrows():
            punto = Point(fila["lon"], fila["lat"])
            if geom.contains(punto):
                ids_dentro.add(fila["id_pedido"])
    return list(ids_dentro)

def actualizar_seleccion_por_figuras(dibujos_actuales):
    """Actualiza la selección basada en figuras, respetando el modo."""
    ids_figuras = set(obtener_ids_dentro_de_geometrias(dibujos_actuales))
    if st.session_state.modo_seleccion.startswith("Agregar"):
        st.session_state.seleccion_por_figuras |= ids_figuras
    else:
        st.session_state.seleccion_por_figuras = ids_figuras
    # Recalcular la selección total
    st.session_state.pedidos_seleccionados = sorted(
        st.session_state.seleccion_por_clics | st.session_state.seleccion_por_figuras
    )

def alternar_seleccion_pedido(id_pedido):
    """Alterna la selección por clic individual."""
    if id_pedido in st.session_state.seleccion_por_clics:
        st.session_state.seleccion_por_clics.discard(id_pedido)
    else:
        st.session_state.seleccion_por_clics.add(id_pedido)
    st.session_state.pedidos_seleccionados = sorted(
        st.session_state.seleccion_por_clics | st.session_state.seleccion_por_figuras
    )

def limpiar_seleccion_y_figuras():
    st.session_state.seleccion_por_clics.clear()
    st.session_state.seleccion_por_figuras.clear()
    st.session_state.pedidos_seleccionados = []
    st.session_state.geometrias_dibujadas = []
    st.session_state.hash_dibujos = ""
    st.session_state.ultimo_tooltip_clickeado = None
