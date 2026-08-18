# -*- coding: utf-8 -*-
"""
==============================================================================
 APP DE OPTIMIZACIÓN LOGÍSTICA - REGIÓN METROPOLITANA (ZONA SUR)
==============================================================================
Aplicación Streamlit para planificación de despachos:
    - Carga de pedidos geolocalizados (.xlsx / .csv, formato SAP)
    - Visualización en mapa interactivo (Folium) con capas GeoJSON de comunas
    - Selección de pedidos mediante herramientas de dibujo (polígono/rectángulo/círculo)
    - Asignación de pedidos a unidades de flota (camionetas / camiones)
    - Control de capacidad en tiempo real (kg) con alertas visuales
    - Exportación del plan de despacho a .xlsx compatible con SAP

Autor: Desarrollo interno - Logística RM Zona Sur
==============================================================================
"""

import io
import json
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import shape, Point

# ==============================================================================
# 1. CONFIGURACIÓN GENERAL DE LA PÁGINA
# ==============================================================================

st.set_page_config(
    page_title="Optimización Logística RM Zona Sur",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Columnas obligatorias que debe traer el archivo de pedidos ---
COLUMNAS_REQUERIDAS = [
    "id_pedido",
    "cliente",
    "lat",
    "lon",
    "direccion",
    "peso_kg",
    "codigo_transporte_sap",
]

# --- Definición de la flota disponible (fija, según requerimiento) ---
FLOTA_CONFIG = {
    "Camioneta": {"cantidad": 15, "capacidad_kg": 1300, "color": "#2E86C1"},
    "Camión": {"cantidad": 12, "capacidad_kg": 5500, "color": "#C0392B"},
}

# --- Centro por defecto del mapa: Zona Sur de la Región Metropolitana ---
CENTRO_DEFECTO = [-33.5975, -70.5789]  # aprox. Puente Alto / La Florida
ZOOM_DEFECTO = 11


# ==============================================================================
# 2. INICIALIZACIÓN DE session_state
# ==============================================================================
# Todo el estado persistente de la app vive acá para sobrevivir a los
# reruns automáticos de Streamlit (cada interacción del usuario).

def inicializar_estado():
    """Crea las claves de session_state si todavía no existen."""

    # --- Datos de pedidos cargados ---
    if "df_pedidos" not in st.session_state:
        st.session_state.df_pedidos = pd.DataFrame(columns=COLUMNAS_REQUERIDAS)

    # --- Asignación pedido -> vehículo (dict: id_pedido -> "Tipo-N°Unidad") ---
    if "asignaciones" not in st.session_state:
        st.session_state.asignaciones = {}

    # --- Estado del mapa: centro, zoom y geometrías dibujadas ---
    if "mapa_center" not in st.session_state:
        st.session_state.mapa_center = CENTRO_DEFECTO
    if "mapa_zoom" not in st.session_state:
        st.session_state.mapa_zoom = ZOOM_DEFECTO
    if "geometrias_dibujadas" not in st.session_state:
        st.session_state.geometrias_dibujadas = []  # lista de features GeoJSON

    # --- Pedidos actualmente seleccionados (por dibujo o por tabla) ---
    if "pedidos_seleccionados" not in st.session_state:
        st.session_state.pedidos_seleccionados = []

    # --- Vehículo activo elegido en el panel derecho ---
    if "vehiculo_activo_tipo" not in st.session_state:
        st.session_state.vehiculo_activo_tipo = "Camioneta"
    if "vehiculo_activo_num" not in st.session_state:
        st.session_state.vehiculo_activo_num = 1

    # --- GeoJSON de comunas (opcional, cargado por el usuario) ---
    if "geojson_comunas" not in st.session_state:
        st.session_state.geojson_comunas = None

    # --- Mensajes de error / validación de la última carga ---
    if "ultimo_error_carga" not in st.session_state:
        st.session_state.ultimo_error_carga = None


inicializar_estado()


# ==============================================================================
# 3. FUNCIONES DE CARGA Y VALIDACIÓN DE ARCHIVOS
# ==============================================================================

def leer_archivo_pedidos(archivo_subido):
    """
    Lee un archivo .xlsx o .csv subido por el usuario y lo valida.

    Retorna:
        (DataFrame o None, mensaje_error o None)
    """
    if archivo_subido is None:
        return None, "No se seleccionó ningún archivo."

    nombre = archivo_subido.name.lower()

    try:
        if nombre.endswith(".xlsx") or nombre.endswith(".xls"):
            df = pd.read_excel(archivo_subido, engine="openpyxl")
        elif nombre.endswith(".csv"):
            # Se prueba primero con separador ';' (común en exportes SAP en español)
            # y si falla, se reintenta con ',' estándar.
            contenido = archivo_subido.read()
            try:
                df = pd.read_csv(io.BytesIO(contenido), sep=";")
                if df.shape[1] == 1:
                    raise ValueError("Separador incorrecto")
            except Exception:
                df = pd.read_csv(io.BytesIO(contenido), sep=",")
        else:
            return None, "Formato de archivo no soportado. Usa .xlsx o .csv."
    except Exception as e:
        return None, f"No se pudo leer el archivo. Detalle técnico: {e}"

    # --- Validación: archivo vacío ---
    if df is None or df.empty:
        return None, "El archivo está vacío o no contiene filas de datos."

    # --- Normalización de nombres de columnas (espacios, mayúsculas) ---
    df.columns = [str(c).strip().lower() for c in df.columns]

    # --- Validación: columnas requeridas presentes ---
    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        return None, (
            "Faltan columnas obligatorias en el archivo: "
            f"{', '.join(faltantes)}. "
            f"Se esperaban: {', '.join(COLUMNAS_REQUERIDAS)}."
        )

    df = df[COLUMNAS_REQUERIDAS].copy()

    # --- Validación de tipos numéricos (lat, lon, peso_kg) ---
    for col in ["lat", "lon", "peso_kg"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    filas_invalidas = df[df[["lat", "lon", "peso_kg"]].isna().any(axis=1)]
    if not filas_invalidas.empty:
        df = df.dropna(subset=["lat", "lon", "peso_kg"])
        if df.empty:
            return None, (
                "Ninguna fila tiene datos numéricos válidos en "
                "lat, lon o peso_kg."
            )

    # --- Validación de rango de coordenadas (sanity check para Chile/RM) ---
    df = df[(df["lat"].between(-90, 90)) & (df["lon"].between(-180, 180))]

    if df.empty:
        return None, "No quedaron pedidos con coordenadas válidas tras la limpieza."

    df["id_pedido"] = df["id_pedido"].astype(str)
    df = df.reset_index(drop=True)

    return df, None


def leer_geojson_comunas(archivo_subido):
    """Lee un archivo GeoJSON de comunas subido por el usuario."""
    if archivo_subido is None:
        return None, "No se seleccionó ningún archivo GeoJSON."
    try:
        contenido = json.load(archivo_subido)
        if "features" not in contenido and contenido.get("type") != "FeatureCollection":
            return None, "El archivo no tiene una estructura GeoJSON válida (FeatureCollection)."
        return contenido, None
    except json.JSONDecodeError as e:
        return None, f"El archivo no es un JSON válido. Detalle: {e}"
    except Exception as e:
        return None, f"No se pudo procesar el GeoJSON. Detalle: {e}"


# ==============================================================================
# 4. FUNCIONES DE LÓGICA DE FLOTA Y CAPACIDAD
# ==============================================================================

def listar_unidades_flota():
    """Genera la lista completa de unidades disponibles: ej. 'Camioneta-01'."""
    unidades = []
    for tipo, cfg in FLOTA_CONFIG.items():
        for n in range(1, cfg["cantidad"] + 1):
            unidades.append(f"{tipo}-{n:02d}")
    return unidades


def obtener_capacidad_unidad(clave_unidad):
    """Dada una clave 'Tipo-N°', retorna su capacidad máxima en kg."""
    tipo = clave_unidad.split("-")[0]
    return FLOTA_CONFIG.get(tipo, {}).get("capacidad_kg", 0)


def calcular_carga_por_unidad():
    """
    Recorre las asignaciones actuales y calcula el peso total (kg)
    acumulado por cada unidad de flota.

    Retorna un DataFrame con: unidad, tipo, peso_total_kg, capacidad_kg,
    porcentaje_uso, n_pedidos.
    """
    df = st.session_state.df_pedidos
    asignaciones = st.session_state.asignaciones

    filas = []
    for unidad in listar_unidades_flota():
        ids_asignados = [pid for pid, u in asignaciones.items() if u == unidad]
        if ids_asignados:
            peso_total = df[df["id_pedido"].isin(ids_asignados)]["peso_kg"].sum()
        else:
            peso_total = 0.0

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
    """Asigna una lista de id_pedido a una unidad de flota específica."""
    for pid in ids_pedidos:
        st.session_state.asignaciones[pid] = unidad


def liberar_pedidos(ids_pedidos):
    """Quita la asignación de flota de los pedidos indicados."""
    for pid in ids_pedidos:
        st.session_state.asignaciones.pop(pid, None)


# ==============================================================================
# 5. FUNCIONES DE EXPORTACIÓN
# ==============================================================================

def generar_excel_exportacion():
    """
    Construye el archivo .xlsx final para SAP, con dos hojas:
        - 'Plan_Despacho': detalle de cada pedido con la unidad asignada.
        - 'Resumen_Flota': carga total y porcentaje de uso por unidad.
    """
    df = st.session_state.df_pedidos.copy()
    df["unidad_asignada"] = df["id_pedido"].map(st.session_state.asignaciones)
    df["unidad_asignada"] = df["unidad_asignada"].fillna("SIN ASIGNAR")
    df["fecha_exportacion"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    resumen = calcular_carga_por_unidad()
    resumen = resumen[resumen["n_pedidos"] > 0]

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Plan_Despacho", index=False)
        resumen.to_excel(writer, sheet_name="Resumen_Flota", index=False)
    buffer.seek(0)
    return buffer


# ==============================================================================
# 6. CONSTRUCCIÓN DEL MAPA (FOLIUM)
# ==============================================================================

def construir_mapa():
    """Construye el objeto folium.Map con capas, marcadores y herramientas de dibujo."""

    m = folium.Map(
        location=st.session_state.mapa_center,
        zoom_start=st.session_state.mapa_zoom,
        tiles="CartoDB positron",
        control_scale=True,
    )

    # --- Capa GeoJSON de comunas (si fue cargada) ---
    if st.session_state.geojson_comunas is not None:
        folium.GeoJson(
            st.session_state.geojson_comunas,
            name="Comunas - Zona Sur RM",
            style_function=lambda feature: {
                "fillColor": "#7FB3D5",
                "color": "#2E4053",
                "weight": 1.5,
                "fillOpacity": 0.08,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=list(
                    (st.session_state.geojson_comunas.get("features", [{}])[0]
                     .get("properties", {}) or {"nombre": ""}).keys()
                )[:1]
            ) if st.session_state.geojson_comunas.get("features") else None,
        ).add_to(m)

    # --- Herramienta de dibujo: polígono, rectángulo, círculo ---
    Draw(
        export=False,
        position="topleft",
        draw_options={
            "polyline": False,
            "polygon": True,
            "rectangle": True,
            "circle": True,
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(m)

    # --- Marcadores de pedidos ---
    df = st.session_state.df_pedidos
    asignaciones = st.session_state.asignaciones
    seleccionados = set(st.session_state.pedidos_seleccionados)

    capa_pedidos = folium.FeatureGroup(name="Pedidos")

    for _, fila in df.iterrows():
        pid = fila["id_pedido"]
        asignado = pid in asignaciones
        es_seleccionado = pid in seleccionados

        if es_seleccionado:
            color = "#F1C40F"  # amarillo: seleccionado en este momento
        elif asignado:
            color = "#27AE60"  # verde: ya asignado a un vehículo
        else:
            color = "#7F8C8D"  # gris: sin asignar

        popup_html = (
            f"<b>Pedido:</b> {pid}<br>"
            f"<b>Cliente:</b> {fila['cliente']}<br>"
            f"<b>Dirección:</b> {fila['direccion']}<br>"
            f"<b>Peso:</b> {fila['peso_kg']} kg<br>"
            f"<b>Cód. Transporte SAP:</b> {fila['codigo_transporte_sap']}<br>"
            f"<b>Unidad asignada:</b> {asignaciones.get(pid, 'Sin asignar')}"
        )

        folium.CircleMarker(
            location=[fila["lat"], fila["lon"]],
            radius=7 if es_seleccionado else 5,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            weight=2,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{pid} · {fila['peso_kg']} kg",
        ).add_to(capa_pedidos)

    capa_pedidos.add_to(m)

    # --- Redibujar geometrías previamente guardadas (persistencia) ---
    for geometria in st.session_state.geometrias_dibujadas:
        try:
            folium.GeoJson(
                geometria,
                style_function=lambda f: {
                    "color": "#8E44AD",
                    "weight": 2,
                    "fillOpacity": 0.05,
                },
            ).add_to(m)
        except Exception:
            pass  # Se ignora geometría corrupta sin interrumpir el render

    folium.LayerControl(collapsed=True).add_to(m)

    return m


def procesar_pedidos_dentro_de_geometrias(geometrias):
    """
    Dado un listado de features GeoJSON dibujadas por el usuario,
    retorna la lista de id_pedido cuyos puntos caen dentro de al
    menos una de esas geometrías.
    """
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


# ==============================================================================
# 7. BARRA LATERAL: CARGA DE ARCHIVOS
# ==============================================================================

st.sidebar.title("🚚 Panel de Control")

with st.sidebar.expander("📂 Carga de datos", expanded=st.session_state.df_pedidos.empty):
    archivo_pedidos = st.file_uploader(
        "Archivo de pedidos (.xlsx / .csv)",
        type=["xlsx", "xls", "csv"],
        key="uploader_pedidos",
    )

    col_carga_1, col_carga_2 = st.columns(2)
    with col_carga_1:
        if st.button("Cargar pedidos", use_container_width=True, disabled=archivo_pedidos is None):
            df_nuevo, error = leer_archivo_pedidos(archivo_pedidos)
            if error:
                st.session_state.ultimo_error_carga = error
            else:
                st.session_state.df_pedidos = df_nuevo
                st.session_state.asignaciones = {}
                st.session_state.pedidos_seleccionados = []
                st.session_state.ultimo_error_carga = None
                # Recentrar el mapa en el promedio de los pedidos cargados
                st.session_state.mapa_center = [
                    float(df_nuevo["lat"].mean()),
                    float(df_nuevo["lon"].mean()),
                ]
                st.rerun()

    with col_carga_2:
        if st.button("Limpiar datos", use_container_width=True):
            st.session_state.df_pedidos = pd.DataFrame(columns=COLUMNAS_REQUERIDAS)
            st.session_state.asignaciones = {}
            st.session_state.pedidos_seleccionados = []
            st.session_state.ultimo_error_carga = None
            st.rerun()

    if st.session_state.ultimo_error_carga:
        st.error(st.session_state.ultimo_error_carga)

    st.divider()

    archivo_geojson = st.file_uploader(
        "GeoJSON de comunas (opcional)",
        type=["geojson", "json"],
        key="uploader_geojson",
    )
    if st.button("Cargar capa de comunas", use_container_width=True, disabled=archivo_geojson is None):
        geojson_data, error = leer_geojson_comunas(archivo_geojson)
        if error:
            st.error(error)
        else:
            st.session_state.geojson_comunas = geojson_data
            st.success("Capa de comunas cargada correctamente.")
            st.rerun()

if not st.session_state.df_pedidos.empty:
    st.sidebar.caption(
        f"✅ {len(st.session_state.df_pedidos)} pedidos cargados · "
        f"{len(st.session_state.asignaciones)} asignados a flota"
    )


# ==============================================================================
# 8. BARRA LATERAL: PANEL DE CONTROL DE CAPACIDAD DE FLOTA
# ==============================================================================

st.sidebar.subheader("📦 Panel de Control de Capacidad")

df_capacidad = calcular_carga_por_unidad()

for tipo, cfg in FLOTA_CONFIG.items():
    subset = df_capacidad[df_capacidad["tipo"] == tipo]
    en_uso = subset[subset["n_pedidos"] > 0]

    with st.sidebar.expander(
        f"{tipo}s ({cfg['cantidad']} unidades · {cfg['capacidad_kg']:,} kg c/u)".replace(",", "."),
        expanded=False,
    ):
        if en_uso.empty:
            st.caption("Sin unidades en uso todavía.")
        else:
            for _, fila in en_uso.sort_values("unidad").iterrows():
                supera_limite = fila["peso_total_kg"] > fila["capacidad_kg"]
                etiqueta = (
                    f"{fila['unidad']} — {fila['peso_total_kg']:,.0f} / "
                    f"{fila['capacidad_kg']:,.0f} kg ({fila['n_pedidos']} pedidos)"
                ).replace(",", ".")
                st.markdown(f"**{etiqueta}**")
                progreso = min(fila["porcentaje_uso"] / 100, 1.0)
                st.progress(progreso)
                if supera_limite:
                    st.warning(
                        f"⚠️ {fila['unidad']} supera su capacidad máxima en "
                        f"{fila['peso_total_kg'] - fila['capacidad_kg']:.1f} kg."
                    )
                elif fila["porcentaje_uso"] >= 90:
                    st.info(f"🟡 {fila['unidad']} está cerca del límite de capacidad.")


# ==============================================================================
# 9. BARRA LATERAL: EXPORTACIÓN
# ==============================================================================

st.sidebar.subheader("📤 Exportación")

if st.session_state.df_pedidos.empty:
    st.sidebar.caption("Carga pedidos para habilitar la exportación.")
else:
    excel_bytes = generar_excel_exportacion()
    st.sidebar.download_button(
        label="Exportar plan de despacho (.xlsx)",
        data=excel_bytes,
        file_name=f"plan_despacho_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


# ==============================================================================
# 10. CUERPO PRINCIPAL: LAYOUT EN DOS COLUMNAS
# ==============================================================================

st.title("Optimización Logística — Región Metropolitana (Zona Sur)")

if st.session_state.df_pedidos.empty:
    st.info(
        "👋 Comienza cargando un archivo de pedidos (.xlsx o .csv) desde la "
        "barra lateral. El archivo debe incluir las columnas: "
        f"{', '.join(COLUMNAS_REQUERIDAS)}."
    )

col_mapa, col_panel = st.columns([2.2, 1])

# ------------------------------------------------------------------------
# COLUMNA IZQUIERDA: MAPA INTERACTIVO
# ------------------------------------------------------------------------
with col_mapa:
    st.subheader("🗺️ Mapa de Pedidos")

    mapa = construir_mapa()

    salida_mapa = st_folium(
        mapa,
        width="100%",
        height=620,
        key="mapa_principal",
        returned_objects=["last_active_drawing", "all_drawings", "center", "zoom"],
    )

    # --- Persistencia de centro y zoom del mapa ---
    if salida_mapa.get("center"):
        st.session_state.mapa_center = [
            salida_mapa["center"]["lat"],
            salida_mapa["center"]["lng"],
        ]
    if salida_mapa.get("zoom"):
        st.session_state.mapa_zoom = salida_mapa["zoom"]

    # --- Persistencia de geometrías dibujadas ---
    dibujos_actuales = salida_mapa.get("all_drawings") or []
    if dibujos_actuales and dibujos_actuales != st.session_state.geometrias_dibujadas:
        st.session_state.geometrias_dibujadas = dibujos_actuales
        # Al detectar un nuevo set de geometrías, se recalculan los pedidos
        # que caen dentro de ellas y se marcan como seleccionados.
        ids_dentro = procesar_pedidos_dentro_de_geometrias(dibujos_actuales)
        if ids_dentro:
            st.session_state.pedidos_seleccionados = ids_dentro
            st.rerun()

    col_btn_1, col_btn_2 = st.columns(2)
    with col_btn_1:
        if st.button("🧹 Limpiar selección", use_container_width=True):
            st.session_state.pedidos_seleccionados = []
            st.session_state.geometrias_dibujadas = []
            st.rerun()
    with col_btn_2:
        st.caption(
            f"Pedidos seleccionados: **{len(st.session_state.pedidos_seleccionados)}**"
        )

    st.caption(
        "🟡 Seleccionado ahora · 🟢 Ya asignado a flota · ⚪ Sin asignar. "
        "Usa las herramientas de dibujo (esquina superior izquierda del mapa) "
        "para seleccionar grupos de pedidos por zona."
    )


# ------------------------------------------------------------------------
# COLUMNA DERECHA: PANEL DE ASIGNACIÓN
# ------------------------------------------------------------------------
with col_panel:
    st.subheader("📋 Resumen de Flota")

    if not df_capacidad.empty:
        resumen_tipo = df_capacidad.groupby("tipo").agg(
            unidades_en_uso=("n_pedidos", lambda x: (x > 0).sum()),
            unidades_totales=("unidad", "count"),
            peso_total_kg=("peso_total_kg", "sum"),
        ).reset_index()

        for _, fila in resumen_tipo.iterrows():
            st.metric(
                label=f"{fila['tipo']}s en uso",
                value=f"{int(fila['unidades_en_uso'])} / {int(fila['unidades_totales'])}",
                delta=f"{fila['peso_total_kg']:.0f} kg totales",
                delta_color="off",
            )

    st.divider()
    st.subheader("🚐 Asignar pedidos a vehículo")

    if st.session_state.df_pedidos.empty:
        st.caption("No hay pedidos cargados todavía.")
    else:
        tabla_seleccion = st.session_state.df_pedidos[
            st.session_state.df_pedidos["id_pedido"].isin(
                st.session_state.pedidos_seleccionados
            )
        ] if st.session_state.pedidos_seleccionados else st.session_state.df_pedidos

        ids_para_asignar = st.multiselect(
            "Pedidos a asignar",
            options=st.session_state.df_pedidos["id_pedido"].tolist(),
            default=st.session_state.pedidos_seleccionados,
            help="Se precargan los pedidos seleccionados en el mapa. Puedes ajustar la lista manualmente.",
        )

        peso_seleccion = st.session_state.df_pedidos[
            st.session_state.df_pedidos["id_pedido"].isin(ids_para_asignar)
        ]["peso_kg"].sum()

        col_tipo, col_num = st.columns(2)
        with col_tipo:
            tipo_vehiculo = st.selectbox(
                "Tipo de vehículo",
                options=list(FLOTA_CONFIG.keys()),
                key="vehiculo_activo_tipo",
            )
        with col_num:
            numero_vehiculo = st.number_input(
                "N° de unidad",
                min_value=1,
                max_value=FLOTA_CONFIG[tipo_vehiculo]["cantidad"],
                step=1,
                key="vehiculo_activo_num",
            )

        unidad_activa = f"{tipo_vehiculo}-{int(numero_vehiculo):02d}"
        capacidad_activa = FLOTA_CONFIG[tipo_vehiculo]["capacidad_kg"]

        # --- Carga actual del vehículo activo (ya asignada) + selección propuesta ---
        ids_ya_asignados = [
            pid for pid, u in st.session_state.asignaciones.items() if u == unidad_activa
        ]
        peso_ya_asignado = st.session_state.df_pedidos[
            st.session_state.df_pedidos["id_pedido"].isin(ids_ya_asignados)
        ]["peso_kg"].sum()

        # Pedidos nuevos a sumar (evitando doble conteo si ya estaban en esa unidad)
        ids_nuevos = [pid for pid in ids_para_asignar if pid not in ids_ya_asignados]
        peso_nuevo = st.session_state.df_pedidos[
            st.session_state.df_pedidos["id_pedido"].isin(ids_nuevos)
        ]["peso_kg"].sum()

        peso_proyectado = peso_ya_asignado + peso_nuevo
        porcentaje_proyectado = min(peso_proyectado / capacidad_activa, 1.0) if capacidad_activa else 0

        st.markdown(f"**Carga proyectada — {unidad_activa}**")
        st.progress(porcentaje_proyectado)
        st.caption(f"{peso_proyectado:,.1f} kg / {capacidad_activa:,.0f} kg".replace(",", "."))

        if peso_proyectado > capacidad_activa:
            st.error(
                f"⚠️ La asignación excede la capacidad de {unidad_activa} en "
                f"{peso_proyectado - capacidad_activa:.1f} kg. "
                "Ajusta la selección o elige otra unidad."
            )

        col_asig_1, col_asig_2 = st.columns(2)
        with col_asig_1:
            if st.button(
                "✅ Asignar a vehículo",
                use_container_width=True,
                disabled=len(ids_para_asignar) == 0,
                type="primary",
            ):
                asignar_pedidos_a_vehiculo(ids_para_asignar, unidad_activa)
                st.session_state.pedidos_seleccionados = []
                st.session_state.geometrias_dibujadas = []
                st.rerun()
        with col_asig_2:
            if st.button(
                "🗑️ Quitar asignación",
                use_container_width=True,
                disabled=len(ids_para_asignar) == 0,
            ):
                liberar_pedidos(ids_para_asignar)
                st.rerun()

    st.divider()
    st.subheader("📑 Detalle de pedidos")

    if not st.session_state.df_pedidos.empty:
        df_detalle = st.session_state.df_pedidos.copy()
        df_detalle["unidad_asignada"] = df_detalle["id_pedido"].map(
            st.session_state.asignaciones
        ).fillna("Sin asignar")

        st.dataframe(
            df_detalle[
                ["id_pedido", "cliente", "peso_kg", "codigo_transporte_sap", "unidad_asignada"]
            ],
            use_container_width=True,
            height=280,
            hide_index=True,
        )
    else:
        st.caption("Sin pedidos para mostrar.")
