# -*- coding: utf-8 -*-
"""
==============================================================================
 APP DE OPTIMIZACIÓN LOGÍSTICA - REGIÓN METROPOLITANA (ZONA SUR)
==============================================================================
"""

import streamlit as st
from config import COLUMNAS_REQUERIDAS
from utils.datos import inicializar_estado
from components.mapa import fragmento_mapa
from components.panel_control import renderizar_sidebar, renderizar_panel_derecho

st.set_page_config(
    page_title="Optimización Logística RM Zona Sur",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inicializar estado global
inicializar_estado()

# Cargar barra lateral
renderizar_sidebar()

# Cuerpo principal
st.title("Optimización Logística — Región Metropolitana (Zona Sur)")

if st.session_state.df_pedidos.empty:
    st.info(
        "👋 Comienza cargando un archivo de pedidos (.xlsx o .csv) desde la "
        "barra lateral. El archivo debe incluir las columnas: "
        f"{', '.join(COLUMNAS_REQUERIDAS)}."
    )

col_mapa, col_panel = st.columns([2.2, 1])

with col_mapa:
    fragmento_mapa()

with col_panel:
    renderizar_panel_derecho()