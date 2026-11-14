import json
from pathlib import Path

import nido_core as nc


def cargar_configuracion(ruta: str | Path | None = None) -> nc.Configuracion:
    archivo = Path(ruta) if ruta else Path(__file__).with_name("config.json")
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"No se encontró la configuración: {archivo}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON de configuración inválido: {archivo}") from error

    try:
        holguras = {
            int(fragilidad): (float(valores[0]), float(valores[1]))
            for fragilidad, valores in datos["holguras"].items()
        }
        flautas = [
            (str(flauta["codigo"]).upper(), float(flauta["espesor"]), float(flauta["peso_max"]))
            for flauta in datos["flautas"]
        ]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ValueError("La configuración debe incluir holguras y flautas válidas") from error

    if set(holguras) != {1, 2, 3, 4} or not flautas:
        raise ValueError("La configuración debe incluir fragilidades 1 a 4 y una flauta")
    if any(g < 0 or d < 0 for g, d in holguras.values()):
        raise ValueError("Las holguras no pueden ser negativas")
    if any(t <= 0 or peso_max <= 0 for _, t, peso_max in flautas):
        raise ValueError("Los espesores y pesos máximos deben ser positivos")

    return nc.Configuracion(holguras=holguras, flautas=flautas)
