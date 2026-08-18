import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
from shapely.geometry import Point, Polygon

# Configuración de la página en ancho completo
st.set_page_config(layout="wide", page_title="Optimizador Logístico RM - Selección Avanzada")

st.title("🗺️ Planificador y Reasignador de Transporte - Región Metropolitana")
st.markdown("Selecciona puntos haciendo clic individualmente o dibujando múltiples figuras en el mapa. ¡Las selecciones se acumulan!")

# Paleta de 12 colores altamente distinguibles para los 12 vehículos
COLORES_TRANSPORTE = {
    "TR-01": "#E6194B",  # Rojo fuerte
    "TR-02": "#3CB44B",  # Verde brillante
    "TR-03": "#4363D8",  # Azul fuerte
    "TR-04": "#F58231",  # Naranja
    "TR-05": "#911EB4",  # Morado
    "TR-06": "#42D4F4",  # Celeste
    "TR-07": "#F032E6",  # Magenta
    "TR-08": "#BFEF45",  # Lima
    "TR-09": "#FABEBE",  # Salmón
    "TR-10": "#469990",  # Verde oscuro / Teal
    "TR-11": "#E6BEFF",  # Lavanda
    "TR-12": "#9A6324"   # Marrón
}

# Carga de archivo CSV
uploaded_file = st.file_uploader("Sube tu archivo CSV (Estructura: id_pedido, cliente, direccion, lat, lon, codigo_transporte_sap)", type="csv")

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    
    if 'codigo_transporte_sap' not in df.columns:
        st.error("El archivo CSV no contiene la columna 'codigo_transporte_sap'. Por favor, revísalo.")
    else:
        # Inicializar estados en la sesión de Streamlit
        if 'asignaciones' not in st.session_state:
            st.session_state['asignaciones'] = dict(zip(df['id_pedido'], df['codigo_transporte_sap']))
        
        if 'puntos_seleccionados' not in st.session_state:
            st.session_state['puntos_seleccionados'] = set()

        # Para evitar procesar el mismo dibujo varias veces al refrescar
        if 'last_drawing_sig' not in st.session_state:
            st.session_state['last_drawing_sig'] = None

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Mapa Interactivo - Región Metropolitana")
            
            # Centrado fijo en Santiago (RM)
            m = folium.Map(location=[-33.4489, -70.6693], zoom_start=11, tiles="CartoDB positron")

            # Dibujar los puntos en el mapa
            for _, row in df.iterrows():
                pid = row['id_pedido']
                transporte_actual = st.session_state['asignaciones'].get(pid, row['codigo_transporte_sap'])
                
                # Definir color del marcador:
                # Si está seleccionado (en proceso), se muestra en Naranja brillante o Negro temporal.
                # Si ya fue asignado a un transporte, usa el color único de ese transporte.
                # Si es original sin tocar, usa un gris/azul base.
                if pid in st.session_state['puntos_seleccionados']:
                    color_marker = "#FF4500" # Naranja rojizo brillante para indicar selección activa
                    fill_opacity = 1.0
                    radius = 8
                elif transporte_actual in COLORES_TRANSPORTE:
                    color_marker = COLORES_TRANSPORTE[transporte_actual]
                    fill_opacity = 0.8
                    radius = 6
                else:
                    color_marker = "#1f77b4" # Color por defecto
                    fill_opacity = 0.6
                    radius = 6

                tooltip_text = f"ID: {pid} | Cliente: {row['cliente']} | Transp: {transporte_actual}"
                
                folium.CircleMarker(
                    location=[row['lat'], row['lon']],
                    radius=radius,
                    color=color_marker,
                    fill=True,
                    fill_color=color_marker,
                    fill_opacity=fill_opacity,
                    tooltip=tooltip_text,
                    popup=f"<b>{row['cliente']}</b><br>ID: {pid}<br>Dir: {row['direccion']}<br>Transp. Actual: {transporte_actual}"
                ).add_to(m)

            # Herramientas de dibujo (Polígonos, Rectángulos, Círculos)
            draw = Draw(
                export=False,
                draw_options={
                    'polyline': False, 
                    'marker': False, 
                    'circlemarker': False,
                    'polygon': True,
                    'rectangle': True,
                    'circle': True
                }
            )
            draw.add_to(m)

            # Capturar interacciones del mapa
            map_output = st_folium(m, width=700, height=550, returned_objects=["last_object_clicked", "last_active_drawing"])

        with col2:
            st.subheader("Panel de Reasignación")
            
            # 1. Procesar clic individual (acumulativo)
            if map_output and map_output.get('last_object_clicked'):
                clicked_tooltip = map_output['last_object_clicked'].get('tooltip')
                if clicked_tooltip and "ID: " in clicked_tooltip:
                    clicked_id = clicked_tooltip.split(" | ")[0].replace("ID: ", "").strip()
                    
                    # Alternar selección individual
                    if clicked_id in st.session_state['puntos_seleccionados']:
                        st.session_state['puntos_seleccionados'].remove(clicked_id)
                    else:
                        st.session_state['puntos_seleccionados'].add(clicked_id)
                    st.rerun()

            # 2. Procesar figuras geométricas dibujadas (acumulativo)
            if map_output and map_output.get('last_active_drawing'):
                drawing = map_output['last_active_drawing']
                drawing_str = str(drawing) # Firma para evitar bucles infinitos
                
                if drawing_str != st.session_state['last_drawing_sig']:
                    st.session_state['last_drawing_sig'] = drawing_str
                    geom_type = drawing['geometry']['type']
                    coords = drawing['geometry']['coordinates']

                    nuevos_capturados = 0
                    if geom_type == 'Polygon':
                        polygon = Polygon(coords[0])
                        for _, row in df.iterrows():
                            if polygon.contains(Point(row['lon'], row['lat'])):
                                if row['id_pedido'] not in st.session_state['puntos_seleccionados']:
                                    st.session_state['puntos_seleccionados'].add(row['id_pedido'])
                                    nuevos_capturados += 1
                        st.rerun()
                    elif geom_type == 'Point':
                        # Para círculos dibujados en Leaflet.draw, el centro es un Point y el radio viene en propiedades
                        # (Opcional: si se usa polígono cubre casi todo, pero esto maneja la base)
                        pass

            # Mostrar cuántos puntos están seleccionados en total
            cant_sel = len(st.session_state['puntos_seleccionados'])
            st.info(f"📍 **{cant_sel} puntos seleccionados en total** (acumulados de figuras y clics).")

            if st.button("Limpiar selección actual"):
                st.session_state['puntos_seleccionados'] = set()
                st.session_state['last_drawing_sig'] = None
                st.rerun()

            st.divider()

            # Opciones de los 12 vehículos de transporte
            lista_vehiculos = [f"TR-0{i}" if i < 10 else f"TR-{i}" for i in range(1, 13)]
            nuevo_transporte = st.selectbox("Asignar al código de transporte:", lista_vehiculos)

            if st.button("Aplicar nuevo transporte a selección", type="primary"):
                if cant_sel > 0:
                    for pid in st.session_state['puntos_seleccionados']:
                        st.session_state['asignaciones'][pid] = nuevo_transporte
                    
                    # Limpiar selección temporal y dejar el color fijo del nuevo transporte
                    st.session_state['puntos_seleccionados'] = set()
                    st.session_state['last_drawing_sig'] = None
                    st.success(f"¡Asignado exitosamente a {nuevo_transporte}!")
                    st.rerun()
                else:
                    st.warning("No hay puntos seleccionados. Dibuja figuras o haz clic en los puntos.")

            st.divider()
            
            # Estadísticas y exportación final
            df_resultado = df.copy()
            df_resultado['codigo_transporte_nuevo'] = df_resultado['id_pedido'].map(st.session_state['asignaciones'])
            
            modificados = (df_resultado['codigo_transporte_sap'] != df_resultado['codigo_transporte_nuevo']).sum()
            st.write(f"**Total pedidos:** {len(df)}")
            st.write(f"**Pedidos reubicados:** {modificados}")
            
            if st.button("Restablecer transportes originales de SAP"):
                st.session_state['asignaciones'] = dict(zip(df['id_pedido'], df['codigo_transporte_sap']))
                st.session_state['puntos_seleccionados'] = set()
                st.session_state['last_drawing_sig'] = None
                st.rerun()

            # Botón de descarga para SAP
            csv_data = df_resultado[['id_pedido', 'codigo_transporte_nuevo']].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Descargar CSV definitivo para SAP",
                data=csv_data,
                file_name="carga_masiva_transporte_sap.csv",
                mime="text/csv"
            )