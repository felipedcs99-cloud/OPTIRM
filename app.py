# -*- coding: utf-8 -*-
"""
==============================================================================
 APP DE OPTIMIZACIÓN LOGÍSTICA - REGIÓN METROPOLITANA (ZONA SUR) [Opción 2]
==============================================================================
"""

import io
import json
from datetime import datetime
import hashlib

import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

# ==============================================================================
# 1. CONFIGURACIÓN GENERAL DE LA PÁGINA
# ==============================================================================

st.set_page_config(
    page_title="Optimización Logística RM Zona Sur",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

def generar_color_transporte(texto):
    """Genera un color hexadecimal estable basado en el código de transporte SAP."""
    if not texto or pd.isna(texto) or str(texto).strip() == "" or str(texto).upper() == "SIN ASIGNAR":
        return "#7F8C8D"  # Gris por defecto
    hash_obj = hashlib.md5(str(texto).encode())
    # Generar un color vibrante asegurando buen contraste
    h = int(hash_obj.hexdigest(), 16)
    r = (h & 0xFF0000) >> 16
    g = (h & 00FF00) >> 8
    b = (h & 0000FF)
    # Evitar colores muy oscuros
    r = max(r, 50)
    g = max(g, 50)
    b = max(b, 50)
    return f"#{r:02x}{g:02x}{b:02x}"

# ==============================================================================
# 2. INICIALIZACIÓN DE session_state
# ==============================================================================

def inicializar_estado():
    if "df_pedidos" not in st.session_state:
        st.session_state.df_pedidos = pd.DataFrame(columns=COLUMNAS_REQUERIDAS)
    if "asignaciones" not in st.session_state:
        st.session_state.asignaciones = {}  # id_pedido -> unidad / transporte
    if "mapa_center" not in st.session_state:
        st.session_state.mapa_center = CENTRO_DEFECTO
    if "mapa_zoom" not in st.session_state:
        st.session_state.mapa_zoom = ZOOM_DEFECTO
    if "geojson_comunas" not in st.session_state:
        st.session_state.geojson_comunas = None
    if "ultimo_error_carga" not in st.session_state:
        st.session_state.ultimo_error_carga = None

inicializar_estado()

# ==============================================================================
# 3. CARGA Y PROCESAMIENTO DE ARCHIVOS
# ==============================================================================

def leer_archivo_pedidos(archivo_subido):
    if archivo_subido is None:
        return None, "No se seleccionó ningún archivo."

    nombre = archivo_subido.name.lower()
    try:
        if nombre.endswith(".xlsx") or nombre.endswith(".xls"):
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
        return None, f"Error al leer el archivo: {e}"

    if df is None or df.empty:
        return None, "El archivo está vacío."

    df.columns = [str(c).strip().lower() for c in df.columns]

    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        return None, f"Faltan columnas obligatorias: {', '.join(faltantes)}"

    df = df[COLUMNAS_REQUERIDAS].copy()

    for col in ["lat", "lon", "peso_kg"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["lat", "lon", "peso_kg"])
    df = df[(df["lat"].between(-90, 90)) & (df["lon"].between(-180, 180))]

    if df.empty:
        return None, "No hay filas con coordenadas válidas."

    df["id_pedido"] = df["id_pedido"].astype(str)
    df["codigo_transporte_sap"] = df["codigo_transporte_sap"].astype(str).fillna("SIN ASIGNAR")
    df = df.reset_index(drop=True)

    return df, None

def leer_geojson_comunas(archivo_subido):
    if archivo_subido is None:
        return None, "No se seleccionó archivo GeoJSON."
    try:
        contenido = json.load(archivo_subido)
        return contenido, None
    except Exception as e:
        return None, f"Error al leer GeoJSON: {e}"

def listar_unidades_flota():
    unidades = []
    for tipo, cfg in FLOTA_CONFIG.items():
        for n in range(1, cfg["cantidad"] + 1):
            unidades.append(f"{tipo}-{n:02d}")
    return unidades

def calcular_carga_por_unidad():
    df = st.session_state.df_pedidos
    asignaciones = st.session_state.asignaciones
    filas = []
    for unidad in listar_unidades_flota():
        ids_asignados = [pid for pid, u in asignaciones.items() if u == unidad]
        peso_total = df[df["id_pedido"].isin(ids_asignados)]["peso_kg"].sum() if ids_asignados else 0.0
        capacidad = FLOTA_CONFIG[unidad.split("-")[0]]["capacidad_kg"]
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

# ==============================================================================
# 4. CONSTRUCCIÓN DEL MAPA ESTABLE
# ==============================================================================

def construir_mapa(ids_seleccionados_tabla):
    m = folium.Map(
        location=st.session_state.mapa_center,
        zoom_start=st.session_state.mapa_zoom,
        tiles="CartoDB positron",
        control_scale=True,
    )

    if st.session_state.geojson_comunas is not None:
        folium.GeoJson(
            st.session_state.geojson_comunas,
            name="Comunas",
            style_function=lambda x: {"fillColor": "#7FB3D5", "color": "#2E4053", "weight": 1.5, "fillOpacity": 0.08},
        ).add_to(m)

    df = st.session_state.df_pedidos
    asignaciones = st.session_state.asignaciones

    capa_pedidos = folium.FeatureGroup(name="Pedidos")

    for _, fila in df.iterrows():
        pid = fila["id_pedido"]
        transporte_sap = fila["codigo_transporte_sap"]
        unidad_asignada = asignaciones.get(pid, transporte_sap)
        
        # Si está seleccionado en la tabla, lo resaltamos en amarillo brillante
        if pid in ids_seleccionados_tabla:
            color = "#F1C40F"
            radio = 9
            weight = 3
        else:
            color = generar_color_transporte(unidad_asignada)
            radio = 6
            weight = 1.5

        popup_html = (
            f"<b>Pedido:</b> {pid}<br>"
            f"<b>Cliente:</b> {fila['cliente']}<br>"
            f"<b>Dirección:</b> {fila['direccion']}<br>"
            f"<b>Peso:</b> {fila['peso_kg']} kg<br>"
            f"<b>Cód. SAP:</b> {transporte_sap}<br>"
            f"<b>Asignado a:</b> {unidad_asignada}"
        )

        folium.CircleMarker(
            location=[fila["lat"], fila["lon"]],
            radius=radio,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            weight=weight,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{pid} - {fila['cliente']}",
        ).add_to(capa_pedidos)

    capa_pedidos.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m

# ==============================================================================
# 5. BARRA LATERAL (CONTROL Y CARGA)
# ==============================================================================

st.sidebar.title("🚚 Panel de Control")

with st.sidebar.expander("📂 Carga de datos", expanded=st.session_state.df_pedidos.empty):
    archivo_pedidos = st.file_uploader("Archivo de pedidos (.xlsx / .csv)", type=["xlsx", "xls", "csv"])
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        if st.button("Cargar pedidos", use_container_width=True, disabled=archivo_pedidos is None):
            df_nuevo, error = leer_archivo_pedidos(archivo_pedidos)
            if error:
                st.session_state.ultimo_error_carga = error
            else:
                st.session_state.df_pedidos = df_nuevo
                # Pre-asignar automáticamente según el código de transporte SAP del archivo
                st.session_state.asignaciones = {
                    row["id_pedido"]: row["codigo_transporte_sap"] for _, row in df_nuevo.iterrows()
                }
                st.session_state.mapa_center = [float(df_nuevo["lat"].mean()), float(df_nuevo["lon"].mean())]
                st.session_state.ultimo_error_carga = None
                st.rerun()
    with col_c2:
        if st.button("Limpiar", use_container_width=True):
            st.session_state.df_pedidos = pd.DataFrame(columns=COLUMNAS_REQUERIDAS)
            st.session_state.asignaciones = {}
            st.rerun()

    if st.session_state.ultimo_error_carga:
        st.error(st.session_state.ultimo_error_carga)

    st.divider()
    archivo_geojson = st.file_uploader("GeoJSON comunas (opc.)", type=["geojson", "json"])
    if st.button("Cargar comunas", use_container_width=True, disabled=archivo_geojson is None):
        geojson_data, error = leer_geojson_comunas(archivo_geojson)
        if error:
            st.error(error)
        else:
            st.session_state.geojson_comunas = geojson_data
            st.success("Capa cargada.")
            st.rerun()

# ==============================================================================
# 6. CUERPO PRINCIPAL: MAPA Y TABLA INTERACTIVA (OPCIÓN 2)
# ==============================================================================

st.title("Optimización Logística — Región Metropolitana (Zona Sur)")

if st.session_state.df_pedidos.empty:
    st.info("👋 Carga un archivo de pedidos para comenzar.")
else:
    col_mapa, col_panel = st.columns([1.8, 1.2])

    # Preparamos el DataFrame enriquecido para la tabla interactiva
    df_principal = st.session_state.df_pedidos.copy()
    df_principal["unidad_asignada"] = df_principal["id_pedido"].map(st.session_state.asignaciones).fillna("SIN ASIGNAR")

    with col_panel:
        st.subheader("📋 Tabla de Pedidos y Selección")
        st.caption("💡 Haz clic en una o varias filas de la tabla para seleccionarlas y resaltarlas instantáneamente en el mapa.")

        # Tabla interactiva con selección de filas nativa de Streamlit
        df_mostrar = df_principal[["id_pedido", "cliente", "peso_kg", "codigo_transporte_sap", "unidad_asignada"]]
        
        evento_seleccion = st.dataframe(
            df_mostrar,
            use_container_width=True,
            height=340,
            hide_index=True,
            selection_mode="multi-row",
            on_select="rerun",
        )

        # Obtener los índices seleccionados en la tabla
        indices_seleccionados = evento_seleccion.selection.rows if hasattr(evento_seleccion, "selection") else []
        ids_seleccionados_tabla = df_mostrar.iloc[indices_seleccionados]["id_pedido"].tolist() if indices_seleccionados else []

        st.divider()
        st.subheader("🚐 Modificar Vehículo para Selección")

        if not ids_seleccionados_tabla:
            st.info("Selecciona uno o más pedidos en la tabla superior para reasignar su vehículo.")
        else:
            st.success(f"**{len(ids_seleccionados_tabla)} pedido(s) seleccionado(s).**")
            
            tipo_vehiculo = st.selectbox("Tipo de vehículo", options=list(FLOTA_CONFIG.keys()), key="sel_tipo_vh")
            num_vehiculo = st.number_input("N° de unidad", min_value=1, max_value=FLOTA_CONFIG[tipo_vehiculo]["cantidad"], step=1, key="sel_num_vh")
            nueva_unidad = f"{tipo_vehiculo}-{int(num_vehiculo):02d}"

            if st.button("✅ Asignar vehículo a selección", type="primary", use_container_width=True):
                for pid in ids_seleccionados_tabla:
                    st.session_state.asignaciones[pid] = nueva_unidad
                st.success(f"¡Asignado correctamente a {nueva_unidad}!")
                st.rerun()

    with col_mapa:
        st.subheader("🗺️ Mapa Interactivo (Estable y Fluido)")
        
        # Construimos y mostramos el mapa sin parpadeos ni reinicios molestos
        mapa_obj = construir_mapa(ids_seleccionados_tabla)
        salida_mapa = st_folium(
            mapa_obj,
            width="100%",
            height=580,
            key="mapa_estatico",
            returned_objects=["center", "zoom"]
        )

        # Guardar posición de zoom/centro sin recargas forzadas
        if salida_mapa.get("center"):
            st.session_state.mapa_center = [salida_mapa["center"]["lat"], salida_mapa["center"]["lng"]]
        if salida_mapa.get("zoom"):
            st.session_state.mapa_zoom = salida_mapa["zoom"]

        st.caption("🎨 Cada color en el mapa representa un código de transporte SAP o vehículo asignado. Los puntos seleccionados en la tabla parpadean en amarillo.")
