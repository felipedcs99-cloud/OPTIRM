import io
import json
import pandas as pd
import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import shape, Point

# Configuración inicial
st.set_page_config(page_title="Optimización Logística", layout="wide")

# --- CONFIGURACIÓN DE FLOTA ---
FLOTA_CONFIG = {
    "Camioneta": {"cantidad": 15, "capacidad_kg": 1300, "color": "#2E86C1"},
    "Camión": {"cantidad": 12, "capacidad_kg": 5500, "color": "#C0392B"},
}

# --- INICIALIZACIÓN DE ESTADO ---
if "df_pedidos" not in st.session_state:
    st.session_state.df_pedidos = pd.DataFrame(columns=["id_pedido", "cliente", "lat", "lon", "direccion", "peso_kg", "codigo_transporte_sap"])
if "asignaciones" not in st.session_state:
    st.session_state.asignaciones = {}
if "pedidos_seleccionados" not in st.session_state:
    st.session_state.pedidos_seleccionados = []
if "geometrias_dibujadas" not in st.session_state:
    st.session_state.geometrias_dibujadas = []

# --- LÓGICA DE MAPA (FRAGMENTO) ---
@st.fragment
def render_map():
    st.subheader("🗺️ Mapa de Pedidos")
    
    # Crear mapa
    m = folium.Map(location=[-33.5975, -70.5789], zoom_start=11, tiles="CartoDB positron")
    
    # Herramientas de dibujo
    Draw(
        export=False,
        draw_options={"polyline": False, "polygon": True, "rectangle": True, "circle": True, "marker": False},
        edit_options={"edit": True, "remove": True}
    ).add_to(m)

    # Dibujar pedidos
    df = st.session_state.df_pedidos
    for _, fila in df.iterrows():
        pid = fila["id_pedido"]
        color = "#F1C40F" if pid in st.session_state.pedidos_seleccionados else ("#27AE60" if pid in st.session_state.asignaciones else "#7F8C8D")
        
        folium.CircleMarker(
            location=[fila["lat"], fila["lon"]],
            radius=7,
            color=color,
            fill=True,
            fill_opacity=0.9,
            tooltip=str(pid)
        ).add_to(m)

    # Renderizado del mapa
    output = st_folium(m, width="100%", height=500, key="main_map")

    # --- PROCESAMIENTO DE INTERACCIONES (SIN RERUN) ---
    if output:
        # Procesar dibujos
        drawings = output.get("all_drawings", [])
        if drawings != st.session_state.geometrias_dibujadas:
            st.session_state.geometrias_dibujadas = drawings
            # Lógica para seleccionar pedidos dentro de figuras
            if drawings:
                ids_seleccionados = []
                for feat in drawings:
                    geom = shape(feat["geometry"])
                    for _, row in df.iterrows():
                        if geom.contains(Point(row["lon"], row["lat"])):
                            ids_seleccionados.append(row["id_pedido"])
                st.session_state.pedidos_seleccionados = list(set(ids_seleccionados))
        
        # Procesar clics
        clicked_id = output.get("last_object_clicked_tooltip")
        if clicked_id and clicked_id in df["id_pedido"].astype(str).tolist():
            if clicked_id in st.session_state.pedidos_seleccionados:
                st.session_state.pedidos_seleccionados.remove(clicked_id)
            else:
                st.session_state.pedidos_seleccionados.append(clicked_id)

# --- LAYOUT PRINCIPAL ---
col1, col2 = st.columns([2, 1])

with col1:
    render_map()
    if st.button("Limpiar selección"):
        st.session_state.pedidos_seleccionados = []
        st.session_state.geometrias_dibujadas = []
        st.rerun() # Solo aquí se permite el rerun porque borramos el mapa

with col2:
    st.subheader("📦 Asignación de Flota")
    
    if not st.session_state.df_pedidos.empty:
        # Selector de asignación
        ids_to_assign = st.multiselect("Pedidos seleccionados", 
                                      options=st.session_state.df_pedidos["id_pedido"].tolist(),
                                      default=st.session_state.pedidos_seleccionados)
        
        tipo_vehiculo = st.selectbox("Tipo de Vehículo", list(FLOTA_CONFIG.keys()))
        num_vehiculo = st.number_input("N° Unidad", 1, FLOTA_CONFIG[tipo_vehiculo]["cantidad"])
        
        unidad_id = f"{tipo_vehiculo}-{num_vehiculo:02d}"
        
        if st.button("Asignar"):
            for pid in ids_to_assign:
                st.session_state.asignaciones[pid] = unidad_id
            st.success(f"Asignado a {unidad_id}")
            st.rerun()

    # Panel de Control (Visualización de capacidad)
    st.divider()
    st.subheader("📊 Estado de Carga")
    for tipo, cfg in FLOTA_CONFIG.items():
        st.write(f"**{tipo}s (Capacidad: {cfg['capacidad_kg']} kg)**")
        # Aquí iría la lógica de cálculo de carga acumulada por unidad
        # (puedes reutilizar la función calcular_carga_por_unidad que ya tenías)
