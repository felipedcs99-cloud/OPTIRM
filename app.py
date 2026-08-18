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
if 'map_center' not in st.session_state: st.session_state['map_center'] = [-33.45, -70.65]
if 'map_zoom' not in st.session_state: st.session_state['map_zoom'] = 11

# --- Carga de Archivo ---
uploaded_file = st.file_uploader("📂 Sube tu archivo CSV de pedidos", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    if not st.session_state['asignaciones']: 
        st.session_state['asignaciones'] = dict(zip(df['id_pedido'], df['codigo_transporte_sap']))

    col_mapa, col_panel = st.columns([2, 1])

    with col_mapa:
        modo_multi = st.checkbox("🟢 Activar Modo Selección Múltiple", value=False)
        
        # Crear mapa manteniendo la posición actual (evita reinicios y saltos de zoom)
        m = folium.Map(location=st.session_state['map_center'], zoom_start=st.session_state['map_zoom'], tiles="CartoDB positron")
        
        for _, row in df.iterrows():
            pid = row['id_pedido']
            transporte = st.session_state['asignaciones'].get(pid, row['codigo_transporte_sap'])
            is_sel = str(pid) in st.session_state['puntos_seleccionados']
            
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

        # Herramientas de dibujo traducidas al español
        Draw(
            draw_options={
                'polygon': {'title': 'Dibujar un polígono'},
                'rectangle': {'title': 'Dibujar un rectángulo'},
                'circle': {'title': 'Dibujar un círculo'},
                'circlemarker': False,
                'polyline': False,
                'marker': False
            },
            edit_options={
                'edit': {'title': 'Editar formas dibujadas'},
                'remove': {'title': 'Eliminar formas'}
            }
        ).add_to(m)

        # Renderizar mapa capturando objetos y posición de navegación
        map_output = st_folium(
            m, 
            width=750, 
            height=500, 
            key="mapa_principal",
            returned_objects=["last_object_clicked", "last_active_drawing", "center", "zoom"]
        )

        # Guardar la posición actual del mapa para evitar saltos
        if map_output and 'center' in map_output and map_output['center']:
            st.session_state['map_center'] = [map_output['center']['lat'], map_output['center']['lng']]
            st.session_state['map_zoom'] = map_output['zoom']

        hubo_cambio = False

        # 1. Lógica de clics individuales con control de firma (evita bucles)
        if map_output.get('last_object_clicked'):
            click_obj = map_output['last_object_clicked']
            click_sig = str(click_obj)
            if click_sig != st.session_state.get('last_click_sig'):
                st.session_state['last_click_sig'] = click_sig
                pid = click_obj.get('tooltip', '').split(" | ")[0].replace("ID: ", "").strip()
                if not modo_multi: 
                    st.session_state['puntos_seleccionados'] = {str(pid)}
                else:
                    if str(pid) in st.session_state['puntos_seleccionados']: 
                        st.session_state['puntos_seleccionados'].remove(str(pid))
                    else: 
                        st.session_state['puntos_seleccionados'].add(str(pid))
                hubo_cambio = True

        # 2. Lógica de figuras geométricas (Polígonos, Rectángulos, Círculos)
        if map_output.get('last_active_drawing'):
            drawing = map_output['last_active_drawing']
            drawing_str = str(drawing)
            if drawing_str != st.session_state.get('last_drawing_sig'):
                st.session_state['last_drawing_sig'] = drawing_str
                geom_type = drawing['geometry']['type']
                coords = drawing['geometry']['coordinates']
                props = drawing.get('properties', {})
                
                if geom_type == 'Polygon':
                    poly_coords = coords[0]
                    for _, row in df.iterrows():
                        if punto_en_poligono(row['lon'], row['lat'], poly_coords):
                            st.session_state['puntos_seleccionados'].add(str(row['id_pedido']))
                elif geom_type == 'Point' and 'radius' in props:
                    for _, row in df.iterrows():
                        if distancia_haversine(row['lat'], row['lon'], coords[1], coords[0]) <= props['radius']:
                            st.session_state['puntos_seleccionados'].add(str(row['id_pedido']))
                hubo_cambio = True

        if hubo_cambio:
            st.rerun()

    with col_panel:
        st.subheader("📊 Resumen de Flota")
        df_res = df.copy()
        df_res['codigo_transporte_nuevo'] = df_res['id_pedido'].astype(str).map(st.session_state['asignaciones'])
        
        resumen = df_res.groupby('codigo_transporte_nuevo')['id_pedido'].count().reset_index()
        resumen.columns = ['Transporte', 'Cant. Pedidos']
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        
        trans_sel = st.selectbox("Selecciona un transporte para ver detalle:", resumen['Transporte'].unique())
        detalle = df_res[df_res['codigo_transporte_nuevo'] == trans_sel][['id_pedido', 'cliente', 'direccion']]
        st.write(f"📦 Pedidos asignados a **{trans_sel}** ({len(detalle)}):")
        st.dataframe(detalle, height=200, use_container_width=True)

        st.divider()
        st.metric("Total pedidos seleccionados", len(st.session_state['puntos_seleccionados']))
        
        if st.button("🗑️ Limpiar selección"):
            st.session_state['puntos_seleccionados'] = set()
            st.session_state['last_click_sig'] = None
            st.session_state['last_drawing_sig'] = None
            st.rerun()

        st.divider()
        nuevo = st.selectbox("Asignar seleccionados a:", [f"TR-{str(i).zfill(2)}" for i in range(1, 13)])
        if st.button("✅ Aplicar transporte a selección"):
            for pid in st.session_state['puntos_seleccionados']:
                st.session_state['asignaciones'][str(pid)] = nuevo
            st.success("¡Asignación realizada!")
            st.rerun()
