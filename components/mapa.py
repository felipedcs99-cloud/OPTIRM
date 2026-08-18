# -*- coding: utf-8 -*-
import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import shape, Point

def construir_mapa():
    m = folium.Map(
        location=st.session_state.mapa_center,
        zoom_start=st.session_state.mapa_zoom,
        tiles="CartoDB positron",
        control_scale=True,
    )

    Draw(
        export=False,
        position="topleft",
        draw_options={
            "polyline": False,
            "polygon": {"shapeOptions": {"color": "#8E44AD"}},
            "rectangle": {"shapeOptions": {"color": "#8E44AD"}},
            "circle": {"shapeOptions": {"color": "#8E44AD"}},
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(m)

    df = st.session_state.df_pedidos
    asignaciones = st.session_state.asignaciones
    seleccionados = set(st.session_state.pedidos_seleccionados)

    capa_pedidos = folium.FeatureGroup(name="Pedidos")

    for _, fila in df.iterrows():
        pid = fila["id_pedido"]
        asignado = pid in asignaciones
        es_seleccionado = pid in seleccionados

        if es_seleccionado:
            color = "#F1C40F"  # Amarillo: seleccionado
        elif asignado:
            color = "#27AE60"  # Verde: pre-cargado / asignado a vehículo
        else:
            color = "#7F8C8D"  # Gris: sin asignar

        popup_html = (
            f"<b>Pedido:</b> {pid}<br>"
            f"<b>Cliente:</b> {fila['cliente']}<br>"
            f"<b>Dirección:</b> {fila['direccion']}<br>"
            f"<b>Peso:</b> {fila['peso_kg']} kg<br>"
            f"<b>Cód. Transporte SAP:</b> {fila['codigo_transporte_sap']}<br>"
            f"<b>Unidad asignada:</b> {asignaciones.get(pid, 'Sin asignar')}"
        )

        folium.CircleMarker(
            location=[fila["lat"], fila["lon"]],
            radius=8 if es_seleccionado else 6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            weight=2,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=pid,
        ).add_to(capa_pedidos)

    capa_pedidos.add_to(m)

    # Mantener visualmente las figuras dibujadas previamente
    for geometria in st.session_state.geometrias_dibujadas:
        try:
            folium.GeoJson(
                geometria,
                style_function=lambda f: {"color": "#8E44AD", "weight": 2, "fillOpacity": 0.05},
            ).add_to(m)
        except Exception:
            pass

    folium.LayerControl(collapsed=True).add_to(m)
    return m

def obtener_ids_dentro_de_geometrias(geometrias):
    df = st.session_state.df_pedidos
    if df.empty or not geometrias:
        return []

    ids_dentro = set()
    for feature in geometrias:
        try:
            geom = shape(feature["geometry"])
        except Exception:
            continue
        for _, fila in df.iterrows():
            if geom.contains(Point(fila["lon"], fila["lat"])):
                ids_dentro.add(fila["id_pedido"])
    return list(ids_dentro)

@st.fragment
def fragmento_mapa():
    st.subheader("🗺️ Mapa de Pedidos (Estable)")

    col_modo, col_info = st.columns([1.3, 1])
    with col_modo:
        st.radio(
            "Modo de selección al procesar figuras",
            options=["Agregar a la selección", "Reemplazar selección"],
            key="modo_seleccion",
            horizontal=True,
        )
    with col_info:
        st.metric("Pedidos seleccionados", len(st.session_state.pedidos_seleccionados))

    mapa = construir_mapa()

    # Renderizamos el mapa de forma completamente fluida y sin bucles de recarga
    salida_mapa = st_folium(
        mapa,
        width="100%",
        height=580,
        key="mapa_principal",
        returned_objects=["all_drawings", "center", "zoom"],
    )

    # Guardamos silenciosamente la posición y el zoom actual del usuario
    if salida_mapa.get("center"):
        st.session_state.mapa_center = [salida_mapa["center"]["lat"], salida_mapa["center"]["lng"]]
    if salida_mapa.get("zoom"):
        st.session_state.mapa_zoom = salida_mapa["zoom"]

    # Botones de control manual (Bajo Demanda)
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("🔍 Procesar pedidos dentro de las figuras", use_container_width=True, type="primary"):
            dibujos = salida_mapa.get("all_drawings") or []
            st.session_state.geometrias_dibujadas = dibujos
            ids_en_figuras = obtener_ids_dentro_de_geometrias(dibujos)

            seleccion_actual = set(st.session_state.pedidos_seleccionados)
            if st.session_state.modo_seleccion.startswith("Agregar"):
                nueva_seleccion = seleccion_actual | set(ids_en_figuras)
            else:
                nueva_seleccion = set(ids_en_figuras)

            st.session_state.pedidos_seleccionados = sorted(nueva_seleccion)
            st.success(f"¡Se seleccionaron {len(ids_en_figuras)} pedidos de las figuras!")
            st.rerun()

    with col_b2:
        if st.button("🧹 Limpiar selección y figuras", use_container_width=True):
            st.session_state.pedidos_seleccionados = []
            st.session_state.geometrias_dibujadas = []
            st.rerun()

    st.caption("💡 Mueve, arrastra o haz zoom con total libertad. Dibuja formas y haz clic en 'Procesar pedidos' para seleccionarlos.")
