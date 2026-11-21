from fastapi import FastAPI, HTTPException #type: ignore[import-not-found]
from fastapi.middleware.cors import CORSMiddleware #type: ignore[import-not-found]
from pydantic import BaseModel #type: ignore[import-not-found]
from typing import Literal

import nido_core as nc
from config import cargar_configuracion


app = FastAPI(title="NIDO", description="Generador de troqueles de embalaje")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
CONFIG = cargar_configuracion()


class TroquelRequest(BaseModel):
    tipo: str
    material: str
    unidad: Literal["mm", "cm"] = "mm"
    largo: float
    ancho: float
    alto: float
    peso: float | None = None
    g: float | None = None
    d: float | None = None
    flauta: str | None = None
    ancho_hoja: float | None = None
    alto_hoja: float | None = None
    encastre: bool = True
    debug_coordenadas: bool = False


def crear_entrada(request: TroquelRequest) -> nc.Entrada:
    convertir = lambda valor: nc.convertir_a_mm(valor, request.unidad) if valor is not None else None
    return nc.Entrada(
        tipo=request.tipo,
        material=request.material,
        largo=nc.convertir_a_mm(request.largo, request.unidad),
        ancho=nc.convertir_a_mm(request.ancho, request.unidad),
        alto=nc.convertir_a_mm(request.alto, request.unidad),
        peso_kg=request.peso,
        g=convertir(request.g),
        d=convertir(request.d),
        flauta=request.flauta,
        encastre=request.encastre,
        ancho_hoja=convertir(request.ancho_hoja),
        alto_hoja=convertir(request.alto_hoja),
    )


@app.get("/opciones")
def opciones() -> dict[str, list[str]]:
    return {
        "tipos": list(nc.TIPO_PRODUCTO),
        "materiales": list(nc.MATERIAL_PRODUCTO),
        "flautas": [flauta[0] for flauta in CONFIG.flautas],
    }


@app.post("/troquel")
def troquel(request: TroquelRequest) -> dict:
    try:
        resultado = nc.calcular(crear_entrada(request), CONFIG)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    respuesta = {
        "medidas": {
            "fragilidad": resultado.fragilidad,
            "flauta": resultado.flauta,
            "espesor": resultado.t,
            "holgura": resultado.g,
            "profundidad_panal": resultado.d,
            "largo_base": resultado.Lb,
            "ancho_base": resultado.Wb,
            "alto_pared": resultado.Hw,
            "alto_solapa": resultado.Hs,
            "encastre": resultado.encastre,
            "tiras_panal": nc.tiras_panal(resultado),
            "tapa": {
                "off_encastre": resultado.encastre_datos.get("off_encastre"),
                "tab_trasera": resultado.encastre_datos.get("tab_trasera"),
                "tab_frontal": resultado.encastre_datos.get("tab_frontal"),
                "tab_izquierda": resultado.encastre_datos.get("tab_izquierda"),
                "tab_derecha": resultado.encastre_datos.get("tab_derecha"),
                "tab_alto": resultado.encastre_datos.get("tab_alto"),
                "tab_chaflan": resultado.encastre_datos.get("tab_chaflan"),
            } if resultado.encastre else None,
            "ancho_total": resultado.ancho_total,
            "alto_total": resultado.alto_total,
            "hoja_disponible": {
                "ancho": resultado.entrada.ancho_hoja,
                "alto": resultado.entrada.alto_hoja,
            },
            "advertencias": resultado.advertencias,
        },
        "pasos": nc.pasos(resultado),
        "svg": nc.svg(resultado),
    }
    if request.debug_coordenadas:
        respuesta["pasos"] = nc.pasos(resultado)
    return respuesta
