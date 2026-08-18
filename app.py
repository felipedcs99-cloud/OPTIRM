import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import math

# Configuración de página
st.set_page_config(layout="wide", page_title="Optimizador Logístico RM")

st.title("🗺️ Planificador de Transporte - Región Metropolitana")

# --- Funciones Geométricas ---
def punto_en_poligono(lon, lat, poly_coords):
    x, y = lon, lat
    inside = False
    n = len(poly_coords)
    p1x, p1y = poly_coords[0]
    for i in range(n + 1):
        p2x, p2y = poly_coords[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def distancia_haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- Estado Inicial ---
if 'asignaciones' not in st.session_state: st.session_state['asignaciones'] = {}
if 'puntos_seleccionados' not in st.session_state: st.session_state['puntos_seleccionados'] = set()
if 'last_drawing_sig' not in st.session_state: st.session_state['last_drawing_sig'] = None

# --- Carga de Archivo ---
uploaded_file = st.file_uploader("📂 Sube tu archivo CSV de pedidos", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    if not st.session_state['asignaciones']: 
        st.session_state['asignaciones'] = dict(zip(df['id_pedido'], df['codigo_transporte_sap']))

    col_mapa, col_panel = st.columns([2, 1])

    with col_mapa:
        modo_multi = st.checkbox("🟢 Activar Modo Selección Múltiple por Clic (permite sumar/restar puntos individuales)", value=False)
        
        # Crear mapa con ubicación estable
        m = folium.Map(location=[-33.45, -70.65], zoom_start=11, tiles="CartoDB positron")
        
        for _, row in df.iterrows():
            pid = str(row['id_pedido'])
            transporte = st.session_state['asignaciones'].get(pid, row['codigo_transporte_sap'])
            is_sel = pid in st.session_state['puntos_seleccionados']
            
            # Popup en español
            popup_html = f"""
            <div style='min-width: 200px;'>
                <b>Cliente:</b> {row['cliente']}<br>
                <b>ID Pedido:</b> {pid}<br>
                <b>Transporte:</b> {transporte}<br>
                <b>Dirección:</b> {row['direccion']}
            </div>
            """
            
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=8 if is_sel else 5,
                color="#FF4500" if is_sel else "#1f77b4",
                fill=True,
                fill_opacity=0.8,
                tooltip=f"ID: {pid} | Transp: {transporte}",
                popup=folium.Popup(popup_html, min_width=200)
            ).add_to(m)

        Draw(draw_options={'polyline': False, 'marker': False, 'polygon': True, 'rectangle': True, 'circle': True}).add_to(m)

        # Usamos una key única para evitar reinicios al hacer zoom/arrastrar
        map_output = st_folium(m, width=750, height=500, key="mapa_principal")

        # Lógica de interacciones
        hubo_cambio = False
        
        if map_output:
            # 1. Clic individual en un marcador
            if map_output.get('last_object_clicked'):
                tooltip = map_output['last_object_clicked'].get('tooltip', '')
                if "ID: " in tooltip:
                    pid = str(tooltip.split(" | ")[0].replace("ID: ", "").strip())
                    if not modo_multi: 
                        st.session_state['puntos_seleccionados'] = {pid}
                    else:
                        if pid in st.session_state['puntos_seleccionados']: 
                            st.session_state['puntos_seleccionados'].remove(pid)
                        else: 
                            st.session_state['puntos_seleccionados'].add(pid)
                    hubo_cambio = True

            # 2. Figuras geométricas dibujadas (Polígonos, Rectángulos, Círculos - Acumulativas)
            if map_output.get('last_active_drawing'):
                drawing = map_output['last_active_drawing']
                drawing_str = str(drawing)
                
                if drawing_str != st.session_state['last_drawing_sig']:
                    st.session_state['last_drawing_sig'] = drawing_str
                    geom_type = drawing['geometry']['type']
                    coords = drawing['geometry']['coordinates']
                    props = drawing.get('properties', {})

                    # Polígono o Rectángulo
                    if geom_type == 'Polygon':
                        poly_coords = coords[0]
                        for _, row in df.iterrows():
                            if punto_en_poligono(row['lon'], row['lat'], poly_coords):
                                st.session_state['puntos_seleccionados'].add(str(row['id_pedido']))
                        hubo_cambio = True
                    
                    # Círculo
                    elif geom_type == 'Point' and 'radius' in props:
                        center_lon, center_lat = coords
                        radius_m = props['radius']
                        for _, row in df.iterrows():
                            dist = distancia_haversine(row['lat'], row['lon'], center_lat, center_lon)
                            if dist <= radius_m:
                                st.session_state['puntos_seleccionados'].add(str(row['id_pedido']))
                        hubo_cambio = True

        if hubo_cambio:
            st.rerun()

    with col_panel:
        st.subheader("📊 Resumen de Flota")
        df_res = df.copy()
        df_res['codigo_transporte_nuevo'] = df_res['id_pedido'].astype(str).map(st.session_state['asignaciones'])
        
        # Tabla de resumen
        resumen = df_res.groupby('codigo_transporte_nuevo')['id_pedido'].count().reset_index()
        resumen.columns = ['Transporte', 'Cant. Pedidos']
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        
        # Drilldown (Desglose)
        trans_sel = st.selectbox("Selecciona un transporte para ver detalle:", resumen['Transporte'].unique())
        detalle = df_res[df_res['codigo_transporte_nuevo'] == trans_sel][['id_pedido', 'cliente', 'direccion']]
        st.write(f"📦 Pedidos asignados a **{trans_sel}** ({len(detalle)}):")
        st.dataframe(detalle, height=200, use_container_width=True)

        st.divider()
        st.metric("Total pedidos seleccionados", len(st.session_state['puntos_seleccionados']))
        
        if st.button("🗑️ Limpiar selección"):
            st.session_state['puntos_seleccionados'] = set()
            st.session_state['last_drawing_sig'] = None
            st.rerun()

        st.divider()
        nuevo = st.selectbox("Asignar seleccionados a:", [f"TR-{str(i).zfill(2)}" for i in range(1, 13)])
        if st.button("✅ Aplicar transporte a selección"):
            if len(st.session_state['puntos_seleccionados']) > 0:
                for pid in st.session_state['puntos_seleccionados']:
                    st.session_state['asignaciones'][str(pid)] = nuevo
                st.success("¡Asignación realizada exitosamente!")
                st.session_state['puntos_seleccionados'] = set()
                st.session_state['last_drawing_sig'] = None
                st.rerun()
            else:
                st.warning("No hay puntos seleccionados para asignar.")

        if st.button("🔄 Restablecer datos originales"):
            st.session_state['asignaciones'] = {}
            st.session_state['puntos_seleccionados'] = set()
            st.session_state['last_drawing_sig'] = None
            st.rerun()
