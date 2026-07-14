"""
Bot de alertas de vuelos baratos a Europa via Telegram.

Usa la Data API gratuita de Travelpayouts (Aviasales) para buscar los
precios más baratos y manda un mensaje por Telegram cuando encuentra
vuelos ida y vuelta por debajo del precio máximo definido.

Variables de entorno necesarias:
  TRAVELPAYOUTS_TOKEN  -> token de https://www.travelpayouts.com
  TELEGRAM_BOT_TOKEN   -> de @BotFather en Telegram
  TELEGRAM_CHAT_ID     -> tu chat id
"""

import os
import sys
from datetime import date

import requests

# ============================================================
# CONFIGURACIÓN — editá esto a gusto
# ============================================================

ORIGEN = "EZE"  # Buenos Aires Ezeiza. Alternativa: "AEP" o "BUE" (ambos)

# Destinos en Europa a monitorear (código IATA: nombre)
DESTINOS = {
    "MAD": "Madrid",
    "BCN": "Barcelona",
    "ROM": "Roma",
    "PAR": "París",
    "LIS": "Lisboa",
    "AMS": "Ámsterdam",
}

PRECIO_MAXIMO_USD = 900   # alerta si el total ida y vuelta es menor a esto
MONEDA = "usd"

MESES_A_BUSCAR = 3        # buscar en los próximos N meses

# ============================================================

API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


def proximos_meses(cantidad: int) -> list[str]:
    """Devuelve los próximos N meses en formato YYYY-MM (empezando el que viene)."""
    hoy = date.today()
    meses = []
    anio, mes = hoy.year, hoy.month
    for _ in range(cantidad):
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
        meses.append(f"{anio}-{mes:02d}")
    return meses


def buscar_precios(destino: str, mes: str) -> list[dict]:
    """Buscar los vuelos ida y vuelta más baratos para un destino en un mes dado."""
    resp = requests.get(
        API_URL,
        params={
            "origin": ORIGEN,
            "destination": destino,
            "departure_at": mes,        # formato YYYY-MM = todo el mes
            "return_at": mes,
            "one_way": "false",         # ida y vuelta
            "direct": "false",
            "currency": MONEDA,
            "sorting": "price",
            "limit": 5,
            "token": os.environ["TRAVELPAYOUTS_TOKEN"],
        },
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"  ⚠️  Error {resp.status_code} buscando {destino} {mes}: {resp.text[:200]}")
        return []
    return resp.json().get("data", [])


def enviar_telegram(mensaje: str):
    """Mandar un mensaje al chat de Telegram configurado."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": mensaje,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    resp.raise_for_status()


def main():
    faltantes = [
        v for v in ["TRAVELPAYOUTS_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
        if not os.environ.get(v)
    ]
    if faltantes:
        print(f"❌ Faltan variables de entorno: {', '.join(faltantes)}")
        sys.exit(1)

    meses = proximos_meses(MESES_A_BUSCAR)
    ofertas_baratas = []

    for codigo, nombre in DESTINOS.items():
        print(f"🔍 Buscando {ORIGEN} → {codigo} ({nombre})...")
        mejor = None
        for mes in meses:
            for vuelo in buscar_precios(codigo, mes):
                precio = float(vuelo.get("price", 0))
                if precio <= 0:
                    continue
                if mejor is None or precio < mejor["precio"]:
                    mejor = {
                        "precio": precio,
                        "fecha_ida": vuelo.get("departure_at", "")[:10],
                        "fecha_vuelta": vuelo.get("return_at", "")[:10],
                        "aerolinea": vuelo.get("airline", "?"),
                        "escalas": vuelo.get("transfers", 0),
                        "link": vuelo.get("link", ""),
                    }
        if mejor:
            print(f"   Mejor precio: {MONEDA.upper()} {mejor['precio']:.0f}")
            if mejor["precio"] <= PRECIO_MAXIMO_USD:
                mejor["destino"] = f"{nombre} ({codigo})"
                ofertas_baratas.append(mejor)
        else:
            print("   Sin resultados en caché para este destino.")

    if not ofertas_baratas:
        print(f"✅ Sin ofertas por debajo de {MONEDA.upper()} {PRECIO_MAXIMO_USD} hoy.")
        return

    ofertas_baratas.sort(key=lambda o: o["precio"])

    lineas = [f"✈️ <b>¡Vuelos baratos a Europa desde {ORIGEN}!</b>\n"]
    for o in ofertas_baratas:
        if o["escalas"] == 0:
            escalas = "directo"
        else:
            escalas = str(o["escalas"]) + " escala(s)"
