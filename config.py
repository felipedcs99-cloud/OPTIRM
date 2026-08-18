# -*- coding: utf-8 -*-

COLUMNAS_REQUERIDAS = [
    "id_pedido",
    "cliente",
    "lat",
    "lon",
    "direccion",
    "peso_kg",
    "codigo_transporte_sap",
]

FLOTA_CONFIG = {
    "Camioneta": {"cantidad": 15, "capacidad_kg": 1300, "color": "#2E86C1"},
    "Camión": {"cantidad": 12, "capacidad_kg": 5500, "color": "#C0392B"},
}

CENTRO_DEFECTO = [-33.5975, -70.5789]
ZOOM_DEFECTO = 11