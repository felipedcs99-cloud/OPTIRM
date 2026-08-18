# app.py
import streamlit as st
from utils import inicializar_estado
from mapa import fragmento_mapa
from panel import barra_lateral, panel_control

st.set_page_config(
    page_title="Optimización Logística RM Zona Sur",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

inicializar_estado()

st.title("Optimización Logística — Región Metropolitana (Zona Sur)")

barra_lateral()

if st.session_state.df_pedidos.empty:
    st.info(
        "👋 Comienza cargando un archivo de pedidos (.xlsx o .csv) desde la "
        "barra lateral. El archivo debe incluir las columnas: "
        "id_pedido, cliente, lat, lon, direccion, peso_kg, codigo_transporte_sap."
    )

col_mapa, col_panel = st.columns([2.2, 1])

with col_mapa:
    fragmento_mapa()

with col_panel:
    panel_control()
