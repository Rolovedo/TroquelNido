from fastapi import FastAPI, HTTPException #type: ignore[import-not-found]
from fastapi.middleware.cors import CORSMiddleware #type: ignore[import-not-found]
from pydantic import BaseModel #type: ignore[import-not-found]

import nido_core as nc


app = FastAPI(title="NIDO", description="Generador de troqueles de embalaje")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TroquelRequest(BaseModel):
    tipo: str
    material: str
    largo: float
    ancho: float
    alto: float
    peso: float | None = None


def crear_entrada(request: TroquelRequest) -> nc.Entrada:
    return nc.Entrada(
        tipo=request.tipo,
        material=request.material,
        largo=request.largo,
        ancho=request.ancho,
        alto=request.alto,
        peso_kg=request.peso,
    )


@app.get("/opciones")
def opciones() -> dict[str, list[str]]:
    return {
        "tipos": list(nc.TIPO_PRODUCTO),
        "materiales": list(nc.MATERIAL_PRODUCTO),
    }


@app.post("/troquel")
def troquel(request: TroquelRequest) -> dict:
    try:
        resultado = nc.calcular(crear_entrada(request))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
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
            "ancho_total": resultado.ancho_total,
            "alto_total": resultado.alto_total,
            "advertencias": resultado.advertencias,
        },
        "pasos": nc.pasos(resultado),
        "svg": nc.svg(resultado),
    }
