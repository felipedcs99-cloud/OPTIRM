import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import math
import json
import io

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
if 'drawn_features' not in st.session_state: st.session_state['drawn_features'] = []
if 'map_center' not in st.session_state: st.session_state['map_center'] = [-33.45, -70.65]
if 'map_zoom' not in st.session_state: st.session_state['map_zoom'] = 11

# --- Carga de Archivos ---
col_u1, col_u2 = st.columns(2)
with col_u1: 
    uploaded_file = st.file_uploader("📂 Sube archivo de pedidos (XLSX o CSV)", type=["csv", "xlsx", "xls"])
with col_u2: 
    uploaded_geo = st.file_uploader("📍 Sube GeoJSON de Zonas (Opcional)", type=["geojson"])

if uploaded_file:
    file_name = uploaded_file.name.lower()
    if file_name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    if not st.session_state['asignaciones']: 
        st.session_state['asignaciones'] = dict(zip(df['id_pedido'], df['codigo_transporte_sap']))

    col_mapa, col_panel = st.columns([2, 1])

    with col_mapa:
        modo_multi = st.checkbox("🟢 Activar Modo Selección Múltiple (para clics individuales)", value=False)
        
        m = folium.Map(location=st.session_state['map_center'], zoom_start=st.session_state['map_zoom'], tiles="CartoDB positron")
        
        # 1. Dibujar Zonas (GeoJSON)
        if uploaded_geo:
            geo_data = json.load(uploaded_geo)
            folium.GeoJson(
                geo_data, 
                style_function=lambda x: {'fillColor': '#0078A8', 'color': '#0078A8', 'fillOpacity': 0.1},
                tooltip=folium.GeoJsonTooltip(fields=['nombre']) if 'nombre' in geo_data.get('features', [{}])[0].get('properties', {}) else None
            ).add_to(m)

        # 2. Dibujar puntos de pedidos
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

        # 3. Redibujar geometrías de usuario previas (Protegido contra None)
        features_a_dibujar = st.session_state.get('drawn_features')
        if features_a_dibujar:
            for feature in features_a_dibujar:
                folium.GeoJson(feature).add_to(m)

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

        map_output = st_folium(
            m, 
            width=750, 
            height=500, 
            key="mapa_principal",
            returned_objects=["last_object_clicked", "all_drawings", "center", "zoom"]
        )

        if map_output and 'center' in map_output and map_output['center']:
            st.session_state['map_center'] = [map_output['center']['lat'], map_output['center']['lng']]
        if map_output and 'zoom' in map_output and map_output['zoom']:
            st.session_state['map_zoom'] = map_output['zoom']

        hubo_cambio = False

        if map_output and map_output.get('last_object_clicked'):
            click_obj = map_output['last_object_clicked']
            click_sig = str(click_obj)
            if click_sig != st.session_state.get('last_click_sig'):
                st.session_state['last_click_sig'] = click_sig
                tooltip = click_obj.get('tooltip', '')
                if "ID: " in tooltip:
                    pid = tooltip.split(" | ")[0].replace("ID: ", "").strip()
                    if not modo_multi: 
                        st.session_state['puntos_seleccionados'] = {str(pid)}
                    else:
                        if str(pid) in st.session_state['puntos_seleccionados']: 
                            st.session_state['puntos_seleccionados'].remove(str(pid))
                        else: 
                            st.session_state['puntos_seleccionados'].add(str(pid))
                    hubo_cambio = True

        if map_output and 'all_drawings' in map_output:
            current_drawings = map_output['all_drawings'] or []
            if current_drawings != st.session_state.get('drawn_features'):
                st.session_state['drawn_features'] = current_drawings
                
                nuevos_seleccionados = set(st.session_state['puntos_seleccionados'])
                for feature in current_drawings:
                    geom = feature.get('geometry', {})
                    geom_type = geom.get('type')
                    coords = geom.get('coordinates')
                    props = feature.get('properties', {})
                    
                    if geom_type == 'Polygon' and coords:
                        poly_coords = coords[0]
                        for _, row in df.iterrows():
                            if punto_en_poligono(row['lon'], row['lat'], poly_coords):
                                nuevos_seleccionados.add(str(row['id_pedido']))
                    elif geom_type == 'Point' and 'radius' in props and coords:
                        center_lon, center_lat = coords
                        radius_m = props['radius']
                        for _, row in df.iterrows():
                            if distancia_haversine(row['lat'], row['lon'], center_lat, center_lon) <= radius_m:
                                nuevos_seleccionados.add(str(row['id_pedido']))
                
                st.session_state['puntos_seleccionados'] = nuevos_seleccionados
                hubo_cambio = True

        if hubo_cambio:
            st.rerun()

    with col_panel:
        st.subheader("📊 Resumen de Flota")
        df_res = df.copy()
        df_res['codigo_transporte_nuevo'] = df_res['id_pedido'].astype(str).map(st.session_state['asignaciones'])
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_res[['id_pedido', 'lat', 'lon', 'cliente', 'codigo_transporte_nuevo', 'direccion']].to_excel(writer, index=False, sheet_name='Pedidos')
        
        st.download_button(
            label="📊 Exportar XLSX para SAP / Google Maps",
            data=buffer.getvalue(),
            file_name='pedidos_optimizados.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            help="Descarga el archivo Excel listo para reingresar a SAP o subir a Google My Maps."
        )

        resumen = df_res.groupby('codigo_transporte_nuevo')['id_pedido'].count().reset_index()
        resumen.columns = ['Transporte', 'Cant. Pedidos']
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        
        trans_sel = st.selectbox("Selecciona un transporte para ver detalle:", resumen['Transporte'].unique())
        detalle = df_res[df_res['codigo_transporte_nuevo'] == trans_sel][['id_pedido', 'cliente', 'direccion']]
        st.write(f"📦 Pedidos asignados a **{trans_sel}** ({len(detalle)}):")
        st.dataframe(detalle, height=200, use_container_width=True)

        st.divider()
        st.metric("Total pedidos seleccionados", len(st.session_state['puntos_seleccionados']))
        
        if st.button("🗑️ Limpiar selección y formas"):
            st.session_state['puntos_seleccionados'] = set()
            st.session_state['drawn_features'] = []
            st.session_state['last_click_sig'] = None
            st.rerun()

        st.divider()
        nuevo = st.selectbox("Asignar seleccionados a:", [f"TR-{str(i).zfill(2)}" for i in range(1, 13)])
        if st.button("✅ Aplicar transporte a selección"):
            for pid in st.session_state['puntos_seleccionados']:
                st.session_state['asignaciones'][str(pid)] = nuevo
            st.success("¡Asignación realizada!")
            st.rerun()
