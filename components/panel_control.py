# -*- coding: utf-8 -*-
from datetime import datetime
import pandas as pd
import streamlit as st
from config import COLUMNAS_REQUERIDAS, FLOTA_CONFIG
from utils.datos import leer_archivo_pedidos
from utils.flota import (
    calcular_carga_por_unidad, listar_unidades_flota,
    asignar_pedidos_a_vehiculo, liberar_pedidos,
    generar_excel_exportacion
)

def renderizar_sidebar():
    st.sidebar.title("🚚 Panel de Control")

    with st.sidebar.expander("📂 Carga de datos", expanded=st.session_state.df_pedidos.empty):
        archivo_pedidos = st.file_uploader(
            "Archivo de pedidos (.xlsx / .csv)",
            type=["xlsx", "xls", "csv"],
            key="uploader_pedidos",
        )

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if st.button("Cargar pedidos", use_container_width=True, disabled=archivo_pedidos is None):
                df_nuevo, asignaciones_iniciales, error = leer_archivo_pedidos(archivo_pedidos)
                if error:
                    st.session_state.ultimo_error_carga = error
                else:
                    st.session_state.df_pedidos = df_nuevo
                    st.session_state.asignaciones = asignaciones_iniciales
                    st.session_state.pedidos_seleccionados = []
                    st.session_state.geometrias_dibujadas = []
                    st.session_state.ultimo_error_carga = None
                    st.session_state.mapa_center = [float(df_nuevo["lat"].mean()), float(df_nuevo["lon"].mean())]
                    st.rerun()

        with col_c2:
            if st.button("Limpiar datos", use_container_width=True):
                st.session_state.df_pedidos = pd.DataFrame(columns=COLUMNAS_REQUERIDAS)
                st.session_state.asignaciones = {}
                st.session_state.pedidos_seleccionados = []
                st.session_state.geometrias_dibujadas = []
                st.rerun()

        if st.session_state.ultimo_error_carga:
            st.error(st.session_state.ultimo_error_carga)

    if not st.session_state.df_pedidos.empty:
        st.sidebar.caption(f"✅ {len(st.session_state.df_pedidos)} pedidos · {len(st.session_state.asignaciones)} asignados")

    st.sidebar.subheader("📦 Estado de Capacidad")
    df_capacidad = calcular_carga_por_unidad()

    for tipo, cfg in FLOTA_CONFIG.items():
        subset = df_capacidad[df_capacidad["tipo"] == tipo]
        en_uso = subset[subset["n_pedidos"] > 0]
        with st.sidebar.expander(f"{tipo}s ({cfg['cantidad']} un. · {cfg['capacidad_kg']:,} kg c/u)".replace(",", "."), expanded=False):
            if en_uso.empty:
                st.caption("Sin unidades en uso.")
            else:
                for _, fila in en_uso.sort_values("unidad").iterrows():
                    st.markdown(f"**{fila['unidad']}** — {fila['peso_total_kg']:,.0f} / {fila['capacidad_kg']:,.0f} kg ({fila['n_pedidos']} ped.)".replace(",", "."))
                    st.progress(min(fila['porcentaje_uso'] / 100, 1.0))

    st.sidebar.subheader("📤 Exportación")
    if not st.session_state.df_pedidos.empty:
        st.sidebar.download_button(
            label="Exportar plan de despacho (.xlsx)",
            data=generar_excel_exportacion(),
            file_name=f"plan_despacho_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

def renderizar_panel_derecho():
    df_capacidad = calcular_carga_por_unidad()
    st.subheader("🚐 Asignar selección")

    if not st.session_state.df_pedidos.empty:
        ids_para_asignar = st.multiselect(
            "Pedidos a asignar",
            options=st.session_state.df_pedidos["id_pedido"].tolist(),
            default=[pid for pid in st.session_state.pedidos_seleccionados if pid in set(st.session_state.df_pedidos["id_pedido"])],
            key="multiselect_pedidos",
        )

        if set(ids_para_asignar) != set(st.session_state.pedidos_seleccionados):
            st.session_state.pedidos_seleccionados = ids_para_asignar

        col_t, col_n = st.columns(2)
        with col_t:
            tipo_v = st.selectbox("Tipo", options=list(FLOTA_CONFIG.keys()), key="vehiculo_activo_tipo")
        with col_n:
            num_v = st.number_input("N°", min_value=1, max_value=FLOTA_CONFIG[tipo_v]["cantidad"], step=1, key="vehiculo_activo_num")

        unidad_activa = f"{tipo_v}-{int(num_v):02d}"
        capacidad_activa = FLOTA_CONFIG[tipo_v]["capacidad_kg"]

        ids_ya_asignados = [pid for pid, u in st.session_state.asignaciones.items() if u == unidad_activa]
        peso_proyectado = st.session_state.df_pedidos[st.session_state.df_pedidos["id_pedido"].isin(ids_ya_asignados + ids_para_asignar)]["peso_kg"].sum()

        st.markdown(f"**Carga proyectada: {unidad_activa}**")
        st.progress(min(peso_proyectado / capacidad_activa, 1.0) if capacidad_activa else 0)
        st.caption(f"{peso_proyectado:,.1f} / {capacidad_activa:,.0f} kg".replace(",", "."))

        if peso_proyectado > capacidad_activa:
            st.error("⚠️ Excede la capacidad máxima del vehículo.")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Asignar", use_container_width=True, disabled=not ids_para_asignar, type="primary"):
                asignar_pedidos_a_vehiculo(ids_para_asignar, unidad_activa)
                st.session_state.pedidos_seleccionados = []
                st.session_state.geometrias_dibujadas = []
                st.rerun()
        with c2:
            if st.button("🗑️ Quitar", use_container_width=True, disabled=not ids_para_asignar):
                liberar_pedidos(ids_para_asignar)
                st.rerun()

    st.divider()
    st.subheader("🚛 Edición por vehículo")

    unidades_en_uso = df_capacidad[df_capacidad["n_pedidos"] > 0]["unidad"].tolist() if not df_capacidad.empty else []

    if not unidades_en_uso:
        st.caption("Sin vehículos con pedidos asignados.")
    else:
        unidad_detalle = st.selectbox("Vehículo a editar", options=unidades_en_uso)
        ids_unidad = [pid for pid, u in st.session_state.asignaciones.items() if u == unidad_detalle]
        df_unidad = st.session_state.df_pedidos[st.session_state.df_pedidos["id_pedido"].isin(ids_unidad)].copy()

        opciones_mover = ["(mantener)"] + [u for u in listar_unidades_flota() if u != unidad_detalle]
        df_unidad["quitar"] = False
        df_unidad["mover_a"] = "(mantener)"

        df_editado = st.data_editor(
            df_unidad[["id_pedido", "cliente", "peso_kg", "direccion", "quitar", "mover_a"]],
            column_config={
                "id_pedido": st.column_config.TextColumn("Pedido", disabled=True),
                "cliente": st.column_config.TextColumn("Cliente", disabled=True),
                "peso_kg": st.column_config.NumberColumn("Peso (kg)", disabled=True),
                "direccion": st.column_config.TextColumn("Dirección", disabled=True),
                "quitar": st.column_config.CheckboxColumn("Quitar"),
                "mover_a": st.column_config.SelectboxColumn("Mover a", options=opciones_mover),
            },
            hide_index=True,
            use_container_width=True,
            key=f"editor_{unidad_detalle}",
        )

        if st.button("💾 Aplicar cambios de este vehículo", key=f"btn_aplica_{unidad_detalle}"):
            for _, fila in df_editado.iterrows():
                pid = fila["id_pedido"]
                if fila["quitar"]:
                    liberar_pedidos([pid])
                elif fila["mover_a"] != "(mantener)":
                    asignar_pedidos_a_vehiculo([pid], fila["mover_a"])
            st.success("Cambios aplicados.")
            st.rerun()