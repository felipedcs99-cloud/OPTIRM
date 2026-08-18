# panel.py
import streamlit as st
from utils import (
    FLOTA_CONFIG,
    calcular_carga_por_unidad,
    listar_unidades_flota,
    obtener_capacidad_unidad,
    asignar_pedidos_a_vehiculo,
    liberar_pedidos,
    generar_excel_exportacion,
    leer_archivo_pedidos,
    cargar_geojson,
    limpiar_seleccion_y_figuras,
    COLUMNAS_REQUERIDAS,
)
from datetime import datetime

# ============================================================================
# BARRA LATERAL
# ============================================================================

def barra_lateral():
    st.sidebar.title("🚚 Panel de Control")

    # ---- CARGA DE DATOS ----
    with st.sidebar.expander("📂 Carga de datos", expanded=st.session_state.df_pedidos.empty):
        archivo_pedidos = st.file_uploader(
            "Archivo de pedidos (.xlsx / .csv)",
            type=["xlsx", "xls", "csv"],
            key="uploader_pedidos",
        )

        col_carga_1, col_carga_2 = st.columns(2)
        with col_carga_1:
            if st.button("Cargar pedidos", use_container_width=True, disabled=archivo_pedidos is None):
                with st.spinner("Cargando..."):
                    df_nuevo, error = leer_archivo_pedidos(archivo_pedidos)
                    if error:
                        st.session_state.ultimo_error_carga = error
                    else:
                        st.session_state.df_pedidos = df_nuevo
                        st.session_state.asignaciones = {}
                        limpiar_seleccion_y_figuras()
                        st.session_state.ultimo_error_carga = None
                        st.session_state.mapa_center = [
                            float(df_nuevo["lat"].mean()),
                            float(df_nuevo["lon"].mean()),
                        ]
                        st.rerun()
        with col_carga_2:
            if st.button("Limpiar datos", use_container_width=True):
                st.session_state.df_pedidos = pd.DataFrame(columns=COLUMNAS_REQUERIDAS)
                st.session_state.asignaciones = {}
                limpiar_seleccion_y_figuras()
                st.session_state.ultimo_error_carga = None
                st.rerun()

        if st.session_state.ultimo_error_carga:
            st.error(st.session_state.ultimo_error_carga)

        st.divider()

        archivo_geojson = st.file_uploader(
            "GeoJSON de comunas (opcional)",
            type=["geojson", "json"],
            key="uploader_geojson",
        )
        if st.button("Cargar capa de comunas", use_container_width=True, disabled=archivo_geojson is None):
            if archivo_geojson:
                geojson_data = cargar_geojson(archivo_geojson.read())
                if geojson_data and "features" in geojson_data:
                    st.session_state.geojson_comunas = geojson_data
                    st.success("Capa cargada correctamente.")
                    st.rerun()
                else:
                    st.error("GeoJSON inválido.")

    if not st.session_state.df_pedidos.empty:
        st.sidebar.caption(
            f"✅ {len(st.session_state.df_pedidos)} pedidos · "
            f"{len(st.session_state.asignaciones)} asignados"
        )

    # ---- PANEL DE CAPACIDAD DE FLOTA ----
    st.sidebar.subheader("📦 Capacidad de Flota")
    df_capacidad = calcular_carga_por_unidad()

    # Filtro por tipo de vehículo
    tipo_filtro = st.sidebar.selectbox("Tipo de flota", list(FLOTA_CONFIG.keys()))
    unidades_filtradas = df_capacidad[df_capacidad["tipo"] == tipo_filtro]

    for _, row in unidades_filtradas.iterrows():
        if row["n_pedidos"] == 0:
            continue
        color = "green" if row["porcentaje_uso"] < 80 else "orange" if row["porcentaje_uso"] < 95 else "red"
        st.sidebar.markdown(
            f"<span style='color:{color};'>●</span> {row['unidad']}: "
            f"{row['peso_total_kg']:.0f}/{row['capacidad_kg']:.0f} kg "
            f"({row['n_pedidos']} pedidos)",
            unsafe_allow_html=True,
        )
        st.sidebar.progress(min(row["porcentaje_uso"] / 100, 1.0))

    st.sidebar.caption("👉 Detalle editable en el panel derecho.")

    # ---- EXPORTACIÓN ----
    st.sidebar.subheader("📤 Exportación")
    if not st.session_state.df_pedidos.empty:
        excel_bytes = generar_excel_exportacion()
        st.sidebar.download_button(
            label="Exportar plan (.xlsx)",
            data=excel_bytes,
            file_name=f"plan_despacho_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

# ============================================================================
# PANEL DE CONTROL DERECHO
# ============================================================================

def panel_control():
    st.subheader("📋 Resumen de Flota")

    df_capacidad = calcular_carga_por_unidad()
    if not df_capacidad.empty:
        resumen_tipo = df_capacidad.groupby("tipo").agg(
            unidades_en_uso=("n_pedidos", lambda x: (x > 0).sum()),
            unidades_totales=("unidad", "count"),
            peso_total_kg=("peso_total_kg", "sum"),
        ).reset_index()

        for _, fila in resumen_tipo.iterrows():
            st.metric(
                label=f"{fila['tipo']}s en uso",
                value=f"{int(fila['unidades_en_uso'])} / {int(fila['unidades_totales'])}",
                delta=f"{fila['peso_total_kg']:.0f} kg totales",
                delta_color="off",
            )

    st.divider()
    st.subheader("🚐 Asignar selección a un vehículo")

    if st.session_state.df_pedidos.empty:
        st.caption("No hay pedidos cargados.")
        return

    ids_para_asignar = st.multiselect(
        "Pedidos a asignar",
        options=st.session_state.df_pedidos["id_pedido"].tolist(),
        default=st.session_state.pedidos_seleccionados,
        help="Los pedidos seleccionados en el mapa se precargan aquí.",
        key="multiselect_pedidos",
    )

    # Sincronizar selección desde el multiselect hacia el mapa
    if set(ids_para_asignar) != set(st.session_state.pedidos_seleccionados):
        st.session_state.pedidos_seleccionados = ids_para_asignar
        # También actualizamos los conjuntos de clics/figuras? No es necesario porque el multiselect es el origen final.
        # Pero para mantener consistencia, podríamos resetear las selecciones por figuras/clics.
        # Lo dejamos así: el multiselect tiene la última palabra.

    col_tipo, col_num = st.columns(2)
    with col_tipo:
        tipo_vehiculo = st.selectbox(
            "Tipo de vehículo",
            options=list(FLOTA_CONFIG.keys()),
            key="vehiculo_activo_tipo",
        )
    with col_num:
        numero_vehiculo = st.number_input(
            "N° de unidad",
            min_value=1,
            max_value=FLOTA_CONFIG[tipo_vehiculo]["cantidad"],
            step=1,
            key="vehiculo_activo_num",
        )

    unidad_activa = f"{tipo_vehiculo}-{int(numero_vehiculo):02d}"
    capacidad_activa = FLOTA_CONFIG[tipo_vehiculo]["capacidad_kg"]

    # Peso ya asignado a esa unidad
    ids_ya_asignados = [pid for pid, u in st.session_state.asignaciones.items() if u == unidad_activa]
    peso_ya_asignado = st.session_state.df_pedidos[
        st.session_state.df_pedidos["id_pedido"].isin(ids_ya_asignados)
    ]["peso_kg"].sum()

    # Peso de los nuevos a asignar (los que están en el multiselect y no están ya en la unidad)
    ids_nuevos = [pid for pid in ids_para_asignar if pid not in ids_ya_asignados]
    peso_nuevo = st.session_state.df_pedidos[
        st.session_state.df_pedidos["id_pedido"].isin(ids_nuevos)
    ]["peso_kg"].sum()

    peso_proyectado = peso_ya_asignado + peso_nuevo
    porcentaje_proyectado = min(peso_proyectado / capacidad_activa, 1.0) if capacidad_activa else 0

    st.markdown(f"**Carga proyectada — {unidad_activa}**")
    st.progress(porcentaje_proyectado)
    st.caption(f"{peso_proyectado:,.1f} kg / {capacidad_activa:,.0f} kg".replace(",", "."))

    if peso_proyectado > capacidad_activa:
        st.error(
            f"⚠️ Excede la capacidad en {peso_proyectado - capacidad_activa:.1f} kg. "
            "Ajusta la selección o elige otra unidad."
        )

    col_asig_1, col_asig_2 = st.columns(2)
    with col_asig_1:
        if st.button(
            "✅ Asignar a vehículo",
            use_container_width=True,
            disabled=len(ids_para_asignar) == 0 or peso_proyectado > capacidad_activa,
            type="primary",
        ):
            asignar_pedidos_a_vehiculo(ids_para_asignar, unidad_activa)
            # Limpiar selección después de asignar
            limpiar_seleccion_y_figuras()
            st.rerun()
    with col_asig_2:
        if st.button("🗑️ Quitar asignación", use_container_width=True, disabled=len(ids_para_asignar) == 0):
            liberar_pedidos(ids_para_asignar)
            st.rerun()

    st.divider()
    st.subheader("🚛 Desglose y edición por vehículo")

    unidades_en_uso = (
        df_capacidad[df_capacidad["n_pedidos"] > 0]["unidad"].tolist()
        if not df_capacidad.empty else []
    )

    if not unidades_en_uso:
        st.caption("Aún no hay vehículos con pedidos.")
    else:
        unidad_detalle = st.selectbox(
            "Selecciona un vehículo",
            options=unidades_en_uso,
            key="unidad_detalle_selector",
        )

        # Cargar o actualizar el DataFrame del editor
        ids_unidad = [pid for pid, u in st.session_state.asignaciones.items() if u == unidad_detalle]
        df_temp = st.session_state.df_pedidos[
            st.session_state.df_pedidos["id_pedido"].isin(ids_unidad)
        ].copy()
        df_temp["quitar"] = False
        df_temp["mover_a"] = "(mantener)"

        # Si el DataFrame del editor no corresponde a esta unidad, lo actualizamos
        if st.session_state.df_editor_actual.empty or unidad_detalle not in st.session_state.df_editor_actual["id_pedido"].values:
            st.session_state.df_editor_actual = df_temp

        capacidad_unidad = obtener_capacidad_unidad(unidad_detalle)
        peso_unidad = st.session_state.df_editor_actual["peso_kg"].sum()
        st.caption(
            f"**{unidad_detalle}** · {peso_unidad:,.1f} / {capacidad_unidad:,.0f} kg "
            f"· {len(st.session_state.df_editor_actual)} pedidos".replace(",", ".")
        )

        opciones_mover = ["(mantener)"] + [
            u for u in listar_unidades_flota() if u != unidad_detalle
        ]

        # Editor de datos
        df_editado = st.data_editor(
            st.session_state.df_editor_actual[
                ["id_pedido", "cliente", "peso_kg", "direccion", "quitar", "mover_a"]
            ],
            column_config={
                "id_pedido": st.column_config.TextColumn("Pedido", disabled=True),
                "cliente": st.column_config.TextColumn("Cliente", disabled=True),
                "peso_kg": st.column_config.NumberColumn("Peso (kg)", disabled=True),
                "direccion": st.column_config.TextColumn("Dirección", disabled=True),
                "quitar": st.column_config.CheckboxColumn("Quitar", help="Deja sin asignar"),
                "mover_a": st.column_config.SelectboxColumn(
                    "Mover a", options=opciones_mover, help="Reasigna a otra unidad"
                ),
            },
            hide_index=True,
            use_container_width=True,
            key=f"editor_{unidad_detalle}",
        )

        if st.button("💾 Aplicar cambios de este vehículo", key=f"aplicar_{unidad_detalle}"):
            movimientos = 0
            for _, fila in df_editado.iterrows():
                pid = fila["id_pedido"]
                if fila["quitar"]:
                    liberar_pedidos([pid])
                    movimientos += 1
                elif fila["mover_a"] != "(mantener)":
                    asignar_pedidos_a_vehiculo([pid], fila["mover_a"])
                    movimientos += 1
            if movimientos:
                st.success(f"Se actualizaron {movimientos} pedido(s).")
                # Actualizar el DataFrame del editor
                st.session_state.df_editor_actual = df_editado
            st.rerun()

    st.divider()
    st.subheader("📑 Todos los pedidos")

    if not st.session_state.df_pedidos.empty:
        df_detalle = st.session_state.df_pedidos.copy()
        df_detalle["unidad_asignada"] = df_detalle["id_pedido"].map(
            st.session_state.asignaciones
        ).fillna("Sin asignar")
        st.dataframe(
            df_detalle[
                ["id_pedido", "cliente", "peso_kg", "codigo_transporte_sap", "unidad_asignada"]
            ],
            use_container_width=True,
            height=260,
            hide_index=True,
        )
    else:
        st.caption("Sin pedidos para mostrar.")
