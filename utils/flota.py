# -*- coding: utf-8 -*-
import io
from datetime import datetime
import pandas as pd
import streamlit as st
from config import FLOTA_CONFIG

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

def generar_excel_exportacion():
    df = st.session_state.df_pedidos.copy()
    df["unidad_asignada"] = df["id_pedido"].map(st.session_state.asignaciones)
    df["unidad_asignada"] = df["unidad_asignada"].fillna("SIN ASIGNAR")
    df["fecha_exportacion"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Plan_Despacho", index=False)
    buffer.seek(0)
    return buffer