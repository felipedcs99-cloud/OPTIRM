import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import math

st.set_page_config(layout="wide", page_title="Optimizador Logístico RM")
st.title("🗺️ Planificador de Transporte - Región Metropolitana")

# --- Funciones ---
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

# --- Estado ---
if 'asignaciones' not in st.session_state: st.session_state['asignaciones'] = {}
if 'puntos_seleccionados' not in st.session_state: st.session_state['puntos_seleccionados'] = set()

# --- Carga ---
uploaded_file = st.file_uploader("📂 Sube tu archivo CSV", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    if not st.session_state['asignaciones']: 
        st.session_state['asignaciones'] = dict(zip(df['id_pedido'], df['codigo_transporte_sap']))

    col_mapa, col_panel = st.columns([2, 1])

    with col_mapa:
        modo_multi = st.checkbox("🟢 Activar Modo Selección Múltiple", value=False)
        
        # Mapa base (siempre fijo, no depende de variables volátiles)
        m = folium.Map(location=[-33.45, -70.65], zoom_start=11, tiles="CartoDB positron")
        
        for _, row in df.iterrows():
            pid = row['id_pedido']
            transporte = st.session_state['asignaciones'].get(pid, row['codigo_transporte_sap'])
            is_sel = str(pid) in st.session_state['puntos_seleccionados']
            
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=8 if is_sel else 5,
                color="#FF4500" if is_sel else "#1f77b4",
                fill=True,
                fill_opacity=0.8,
                tooltip=f"ID: {pid} | Transp: {transporte}",
                popup=folium.Popup(f"<b>Cliente:</b> {row['cliente']}<br>ID: {pid}<br>Transp: {transporte}", min_width=200)
            ).add_to(m)

        Draw(
            draw_options={
                'polygon': {'title': 'Dibujar un polígono'},
                'rectangle': {'title': 'Dibujar un rectángulo'},
                'circle': {'title': 'Dibujar un círculo'},
                'circlemarker': False, 'polyline': False, 'marker': False
            },
            edit_options={'edit': {'title': 'Editar formas'}, 'remove': {'title': 'Eliminar formas'}}
        ).add_to(m)

        # --- CAMBIO CLAVE ---
        # Quitamos "center" y "zoom" de returned_objects. 
        # Ahora el mapa será fluido y no se reiniciará al moverlo.
        map_output = st_folium(
            m, 
            width=750, 
            height=500, 
            key="mapa_principal",
            returned_objects=["last_object_clicked", "last_active_drawing"]
        )

        hubo_cambio = False

        # Lógica de Clics
        if map_output.get('last_object_clicked'):
            click_sig = str(map_output['last_object_clicked'])
            if click_sig != st.session_state.get('last_click_sig'):
                st.session_state['last_click_sig'] = click_sig
                pid = map_output['last_object_clicked']['tooltip'].split(" | ")[0].replace("ID: ", "").strip()
                if not modo_multi: st.session_state['puntos_seleccionados'] = {str(pid)}
                else:
                    if str(pid) in st.session_state['puntos_seleccionados']: st.session_state['puntos_seleccionados'].remove(str(pid))
                    else: st.session_state['puntos_seleccionados'].add(str(pid))
                hubo_cambio = True

        # Lógica de Figuras
        if map_output.get('last_active_drawing'):
            drawing = map_output['last_active_drawing']
            drawing_str = str(drawing)
            if drawing_str != st.session_state.get('last_drawing_sig'):
                st.session_state['last_drawing_sig'] = drawing_str
                geom_type = drawing['geometry']['type']
                coords = drawing['geometry']['coordinates']
                props = drawing.get('properties', {})
                
                if geom_type == 'Polygon':
                    for _, row in df.iterrows():
                        if punto_en_poligono(row['lon'], row['lat'], coords[0]):
                            st.session_state['puntos_seleccionados'].add(str(row['id_pedido']))
                elif geom_type == 'Point' and 'radius' in props:
                    for _, row in df.iterrows():
                        if distancia_haversine(row['lat'], row['lon'], coords[1], coords[0]) <= props['radius']:
                            st.session_state['puntos_seleccionados'].add(str(row['id_pedido']))
                hubo_cambio = True

        if hubo_cambio:
            st.rerun()

    with col_panel:
        # ... (Tu código de panel se mantiene igual)
        st.subheader("📊 Resumen de Flota")
        df_res = df.copy()
        df_res['codigo_transporte_nuevo'] = df_res['id_pedido'].astype(str).map(st.session_state['asignaciones'])
        resumen = df_res.groupby('codigo_transporte_nuevo')['id_pedido'].count().reset_index()
        resumen.columns = ['Transporte', 'Cant. Pedidos']
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        
        trans_sel = st.selectbox("Selecciona transporte:", resumen['Transporte'].unique())
        detalle = df_res[df_res['codigo_transporte_nuevo'] == trans_sel][['id_pedido', 'cliente', 'direccion']]
        st.dataframe(detalle, height=200, use_container_width=True)
        
        st.divider()
        st.metric("Total seleccionados", len(st.session_state['puntos_seleccionados']))
        
        if st.button("🗑️ Limpiar selección"):
            st.session_state['puntos_seleccionados'] = set()
            st.rerun()

        nuevo = st.selectbox("Asignar a:", [f"TR-{str(i).zfill(2)}" for i in range(1, 13)])
        if st.button("✅ Aplicar transporte"):
            for pid in st.session_state['puntos_seleccionados']:
                st.session_state['asignaciones'][str(pid)] = nuevo
            st.success("¡Asignación realizada!")
            st.rerun()
