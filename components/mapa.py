# -*- coding: utf-8 -*-
import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import shape, Point

def rerun_app():
    try:
        st.rerun(scope="app")
    except TypeError:
        st.rerun()

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

def aplicar_seleccion_por_dibujos(dibujos_actuales):
    ids_en_figuras = set(obtener_ids_dentro_de_geometrias(dibujos_actuales))
    seleccion_actual = set(st.session_state.pedidos_seleccionados)

    if st.session_state.modo_seleccion.startswith("Agregar"):
        nueva_seleccion = seleccion_actual | ids_en_figuras
    else:
        nueva_seleccion = ids_en_figuras

    st.session_state.pedidos_seleccionados = sorted(nueva_seleccion)

def alternar_seleccion_pedido(id_pedido):
    seleccion_actual = set(st.session_state.pedidos_seleccionados)
    if id_pedido in seleccion_actual:
        seleccion_actual.discard(id_pedido)
    else:
        seleccion_actual.add(id_pedido)
    st.session_state.pedidos_seleccionados = sorted(seleccion_actual)

@st.fragment
def fragmento_mapa():
    st.subheader("🗺️ Mapa de Pedidos")

    col_modo, col_info = st.columns([1.3, 1])
    with col_modo:
        st.radio(
            "Modo de selección al dibujar",
            options=["Agregar a la selección", "Reemplazar selección"],
            key="modo_seleccion",
            horizontal=True,
        )
    with col_info:
        st.metric("Pedidos seleccionados", len(st.session_state.pedidos_seleccionados))

    mapa = construir_mapa()

    salida_mapa = st_folium(
        mapa,
        width="100%",
        height=620,
        key="mapa_principal",
        returned_objects=[
            "last_active_drawing",
            "all_drawings",
            "center",
            "zoom",
            "last_object_clicked_tooltip",
        ],
    )

    if salida_mapa.get("center"):
        st.session_state.mapa_center = [salida_mapa["center"]["lat"], salida_mapa["center"]["lng"]]
    if salida_mapa.get("zoom"):
        st.session_state.mapa_zoom = salida_mapa["zoom"]

    dibujos_actuales = salida_mapa.get("all_drawings") or []
    if dibujos_actuales and dibujos_actuales != st.session_state.geometrias_dibujadas:
        st.session_state.geometrias_dibujadas = dibujos_actuales
        aplicar_seleccion_por_dibujos(dibujos_actuales)
        rerun_app()

    tooltip_clickeado = salida_mapa.get("last_object_clicked_tooltip")
    if tooltip_clickeado and tooltip_clickeado != st.session_state.ultimo_click_procesado:
        st.session_state.ultimo_click_procesado = tooltip_clickeado
        if tooltip_clickeado in set(st.session_state.df_pedidos["id_pedido"]):
            alternar_seleccion_pedido(tooltip_clickeado)
            rerun_app()

    if st.button("🧹 Limpiar selección y figuras", use_container_width=True):
        st.session_state.pedidos_seleccionados = []
        st.session_state.geometrias_dibujadas = []
        st.session_state.ultimo_click_procesado = None
        rerun_app()

    st.caption("🟡 Seleccionado · 🟢 Asignado o pre-cargado en vehículo · ⚪ Sin asignar.")