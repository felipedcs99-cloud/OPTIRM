# -*- coding: utf-8 -*-
import io
import pandas as pd
import streamlit as st
from config import COLUMNAS_REQUERIDAS, CENTRO_DEFECTO, ZOOM_DEFECTO

def inicializar_estado():
    if "df_pedidos" not in st.session_state:
        st.session_state.df_pedidos = pd.DataFrame(columns=COLUMNAS_REQUERIDAS)
    if "asignaciones" not in st.session_state:
        st.session_state.asignaciones = {}
    if "mapa_center" not in st.session_state:
        st.session_state.mapa_center = CENTRO_DEFECTO
    if "mapa_zoom" not in st.session_state:
        st.session_state.mapa_zoom = ZOOM_DEFECTO
    if "geometrias_dibujadas" not in st.session_state:
        st.session_state.geometrias_dibujadas = []
    if "pedidos_seleccionados" not in st.session_state:
        st.session_state.pedidos_seleccionados = []
    if "modo_seleccion" not in st.session_state:
        st.session_state.modo_seleccion = "Agregar a la selección"
    if "ultimo_click_procesado" not in st.session_state:
        st.session_state.ultimo_click_procesado = None
    if "vehiculo_activo_tipo" not in st.session_state:
        st.session_state.vehiculo_activo_tipo = "Camioneta"
    if "vehiculo_activo_num" not in st.session_state:
        st.session_state.vehiculo_activo_num = 1
    if "ultimo_error_carga" not in st.session_state:
        st.session_state.ultimo_error_carga = None

def leer_archivo_pedidos(archivo_subido):
    if archivo_subido is None:
        return None, {}, "No se seleccionó ningún archivo."

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
            return None, {}, "Formato no soportado. Usa .xlsx o .csv."
    except Exception as e:
        return None, {}, f"Error al leer el archivo: {e}"

    if df is None or df.empty:
        return None, {}, "El archivo está vacío."

    df.columns = [str(c).strip().lower() for c in df.columns]

    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        return None, {}, f"Faltan columnas obligatorias: {', '.join(faltantes)}"

    # Detectar columna precargada de vehículo si existe en el archivo
    columna_vehiculo_encontrada = None
    for posible in ["vehiculo", "unidad", "unidad_asignada", "transporte_asignado"]:
        if posible in df.columns:
            columna_vehiculo_encontrada = posible
            break

    df_limpio = df[COLUMNAS_REQUERIDAS].copy()

    for col in ["lat", "lon", "peso_kg"]:
        df_limpio[col] = pd.to_numeric(df_limpio[col], errors="coerce")

    df_limpio = df_limpio.dropna(subset=["lat", "lon", "peso_kg"])
    df_limpio = df_limpio[(df_limpio["lat"].between(-90, 90)) & (df_limpio["lon"].between(-180, 180))]

    if df_limpio.empty:
        return None, {}, "No hay pedidos con coordenadas válidas."

    df_limpio["id_pedido"] = df_limpio["id_pedido"].astype(str)
    df_limpio = df_limpio.reset_index(drop=True)

    asignaciones_precargadas = {}
    if columna_vehiculo_encontrada:
        for _, row in df.iterrows():
            pid = str(row["id_pedido"])
            veh = str(row[columna_vehiculo_encontrada]).strip()
            if veh and veh.lower() != "nan" and veh != "Sin asignar":
                asignaciones_precargadas[pid] = veh

    return df_limpio, asignaciones_precargadas, None