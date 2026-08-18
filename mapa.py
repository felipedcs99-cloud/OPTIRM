# mapa.py
import json
import hashlib
import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from utils import (
    actualizar_seleccion_por_figuras,
    alternar_seleccion_pedido,
    limpiar_seleccion_y_figuras,
    CENTRO_DEFECTO,
    ZOOM_DEFECTO,
)

def construir_mapa():
    """Construye el mapa con marcadores individuales (sin clustering)."""
    m = folium.Map(
        location=st.session_state.mapa_center,
        zoom_start=st.session_state.mapa_zoom,
        tiles="CartoDB positron",
        control_scale=True,
    )

    # Capa de comunas (si existe)
    if st.session_state.geojson_comunas is not None:
        geojson_data = st.session_state.geojson_comunas
        primeras_props = geojson_data.get("features", [{}])[0].get("properties", {})
        campos_tooltip = list(primeras_props.keys())[:1] if primeras_props else None
        folium.GeoJson(
            geojson_data,
            name="Comunas - Zona Sur RM",
            style_function=lambda f: {
                "fillColor": "#7FB3D5",
                "color": "#2E4053",
                "weight": 1.5,
                "fillOpacity": 0.08,
            },
            tooltip=folium.GeoJsonTooltip(fields=campos_tooltip) if campos_tooltip else None,
        ).add_to(m)

    # Herramienta de dibujo
    Draw(
        export=False,
        position="topleft",
        draw_options={
            "polyline": False,
            "polygon": True,
            "rectangle": True,
            "circle": True,
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(m)

    # Marcadores de pedidos (cada punto independiente)
    df = st.session_state.df_pedidos
    asignaciones = st.session_state.asignaciones
    seleccion_total = set(st.session_state.pedidos_seleccionados)

    capa_pedidos = folium.FeatureGroup(name="Pedidos")

    for _, fila in df.iterrows():
        pid = fila["id_pedido"]
        asignado = pid in asignaciones
        es_seleccionado = pid in seleccion_total

        if es_seleccionado:
            color = "#F1C40F"  # amarillo
        elif asignado:
            color = "#27AE60"  # verde
        else:
            color = "#7F8C8D"  # gris

        popup_html = (
            f"<b>Pedido:</b> {pid}<br>"
            f"<b>Cliente:</b> {fila['cliente']}<br>"
            f"<b>Dirección:</b> {fila['direccion']}<br>"
            f"<b>Peso:</b> {fila['peso_kg']} kg<br>"
            f"<b>Cód. SAP:</b> {fila['codigo_transporte_sap']}<br>"
            f"<b>Unidad:</b> {asignaciones.get(pid, 'Sin asignar')}<br>"
            f"<i>Click para seleccionar/deseleccionar</i>"
        )

        marker = folium.CircleMarker(
            location=[fila["lat"], fila["lon"]],
            radius=8 if es_seleccionado else 6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            weight=2,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=pid,  # el tooltip es el id_pedido
        )
        capa_pedidos.add_child(marker)

    capa_pedidos.add_to(m)

    # Redibujar figuras guardadas
    for geometria in st.session_state.geometrias_dibujadas:
        try:
            folium.GeoJson(
                geometria,
                style_function=lambda f: {
                    "color": "#8E44AD",
                    "weight": 2,
                    "fillOpacity": 0.05,
                },
            ).add_to(m)
        except Exception:
            pass

    folium.LayerControl(collapsed=True).add_to(m)
    return m

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
            help="'Agregar' combina figuras y clics; 'Reemplazar' usa solo la última figura dibujada.",
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

    # Actualizar centro y zoom (siempre, pero sin disparar rerun)
    if salida_mapa.get("center"):
        st.session_state.mapa_center = [
            salida_mapa["center"]["lat"],
            salida_mapa["center"]["lng"],
        ]
    if salida_mapa.get("zoom"):
        st.session_state.mapa_zoom = salida_mapa["zoom"]

    # --- Detección de nuevas figuras (por hash) ---
    dibujos_actuales = salida_mapa.get("all_drawings") or []
    hash_actual = hashlib.md5(json.dumps(dibujos_actuales, sort_keys=True).encode()).hexdigest()
    if hash_actual != st.session_state.hash_dibujos:
        st.session_state.hash_dibujos = hash_actual
        st.session_state.geometrias_dibujadas = dibujos_actuales
        actualizar_seleccion_por_figuras(dibujos_actuales)
        # Forzar rerun de toda la app para sincronizar paneles
        try:
            st.rerun(scope="app")
        except TypeError:
            st.rerun()

    # --- Detección de clic en un punto (por tooltip = id_pedido) ---
    tooltip_clickeado = salida_mapa.get("last_object_clicked_tooltip")
    if tooltip_clickeado and tooltip_clickeado != st.session_state.ultimo_tooltip_clickeado:
        st.session_state.ultimo_tooltip_clickeado = tooltip_clickeado
        ids_validos = set(st.session_state.df_pedidos["id_pedido"])
        if tooltip_clickeado in ids_validos:
            alternar_seleccion_pedido(tooltip_clickeado)
            try:
                st.rerun(scope="app")
            except TypeError:
                st.rerun()

    # Botones de limpieza
    col_btn_1, col_btn_2 = st.columns(2)
    with col_btn_1:
        if st.button("🧹 Limpiar selección y figuras", use_container_width=True):
            limpiar_seleccion_y_figuras()
            try:
                st.rerun(scope="app")
            except TypeError:
                st.rerun()
    with col_btn_2:
        st.caption("🖱️ Click en un punto para sumarlo o quitarlo de la selección.")

    st.caption(
        "🟡 Seleccionado ahora · 🟢 Ya asignado a flota · ⚪ Sin asignar. "
        "Combina figuras y clics antes de asignar."
    )
