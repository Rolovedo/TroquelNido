"""NIDO - núcleo paramétrico (sin dependencias externas).

Entrada : tipo de producto, material, largo, ancho, alto (mm), peso opcional.
Salida  : dimensiones del troquel, pasos de trazado con coordenadas, tiras de
          panal y un SVG del troquel (corte continuo, pliegue punteado).

Todos los valores de holgura/espesor son PUNTOS DE PARTIDA: se calibran con la
prueba de caída (Fase 4 del documento) y se editan en config.json.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from math import sqrt

# ----------------------------------------------------------------- tablas ---
# Fragilidad: 1 baja, 2 media, 3 alta, 4 muy alta
TIPO_PRODUCTO = {
    "prenda / textil": 1,
    "libro / papel": 1,
    "objeto de madera": 2,
    "electrónico pequeño": 3,
    "pieza de arte / marco": 3,
    "cerámica / taza": 4,
    "vidrio / cristal": 4,
}
MATERIAL_PRODUCTO = {
    "tela": 1, "papel": 1, "madera": 2, "plástico": 2, "metal": 2,
    "yeso / resina": 3, "cerámica": 4, "vidrio": 4,
}
HOJA_MAX = (1200.0, 800.0)  # hoja/plancha máxima de la troqueladora (mm), editable


def convertir_a_mm(valor: float, unidad: str) -> float:
    """Convierte una medida de cm o mm a milímetros."""
    if unidad == "mm":
        return valor
    if unidad == "cm":
        return valor * 10
    raise ValueError("La unidad debe ser mm o cm")


def formato_mm(valor: float) -> str:
    """Devuelve una medida en mm sin ceros ni .0 sobrantes."""
    return f"{valor:.2f}".rstrip("0").rstrip(".")


def distancia_puntos(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    from math import hypot
    return hypot(p2[0] - p1[0], p2[1] - p1[1])


@dataclass(frozen=True)
class Cota:
    valor: float
    p1: tuple[float, float]
    p2: tuple[float, float]
    nivel: int = 1
    escala: float = 1.0
    orientacion: str = "auto"

    def validar(self, tolerancia: float = 0.01) -> bool:
        if self.escala <= 0:
            raise ValueError("La escala de una cota debe ser positiva")
        distancia_real = distancia_puntos(self.p1, self.p2) / self.escala
        return abs(self.valor - distancia_real) <= tolerancia

    def texto_mm(self) -> str:
        return formato_mm(self.valor)


def validar_cota(cota: Cota, tolerancia: float = 0.01) -> None:
    if not cota.validar(tolerancia):
        raise ValueError(
            "El valor de la cota no coincide con la distancia real: "
            f"{cota.valor} mm vs {distancia_puntos(cota.p1, cota.p2) / cota.escala:.2f} mm"
        )


@dataclass(frozen=True)
class Panel:
    nombre: str
    p1: tuple[float, float]
    p2: tuple[float, float]
    padre: str | None = None
    linea_pliegue: tuple[tuple[float, float], tuple[float, float]] | None = None
    angulo_final: float = 0.0
    paso: int | None = None

    @property
    def ancho(self) -> float:
        return abs(self.p2[0] - self.p1[0])

    @property
    def alto(self) -> float:
        return abs(self.p2[1] - self.p1[1])


@dataclass(frozen=True)
class Rectangulo:
    x1: float
    y1: float
    x2: float
    y2: float

    def interseca(self, otro: "Rectangulo") -> bool:
        return not (self.x2 <= otro.x1 or otro.x2 <= self.x1 or
                    self.y2 <= otro.y1 or otro.y2 <= self.y1)


@dataclass(frozen=True)
class Configuracion:
    holguras: dict[int, tuple[float, float]]
    flautas: list[tuple[str, float, float]]


@dataclass
class Entrada:
    tipo: str
    material: str
    largo: float   # mm
    ancho: float   # mm
    alto: float    # mm
    peso_kg: float | None = None
    flauta: str | None = None   # forzar E/B/C; None = automático
    g: float | None = None      # override opcional de holgura
    d: float | None = None      # override opcional de profundidad del panal
    encastre: bool = True       # True = cierre completo; False = modo cruz anterior
    ancho_hoja: float | None = None  # mm disponibles por el usuario
    alto_hoja: float | None = None   # mm disponibles por el usuario

    def validar(self):
        if self.tipo not in TIPO_PRODUCTO:
            raise ValueError(f"Tipo no reconocido: {self.tipo}")
        if self.material not in MATERIAL_PRODUCTO:
            raise ValueError(f"Material no reconocido: {self.material}")
        for n, v in (("largo", self.largo), ("ancho", self.ancho), ("alto", self.alto)):
            if not (10 <= v <= 1000):
                raise ValueError(f"{n} fuera de rango (10–1000 mm): {v}")
        if self.peso_kg is not None and self.peso_kg <= 0:
            raise ValueError("El peso debe ser positivo")
        for n, v in (("g", self.g), ("d", self.d)):
            if v is not None and v < 0:
                raise ValueError(f"{n} no puede ser negativo")
        for n, v in (("ancho_hoja", self.ancho_hoja), ("alto_hoja", self.alto_hoja)):
            if v is not None and v <= 0:
                raise ValueError(f"{n} debe ser positiva")


@dataclass
class Resultado:
    entrada: Entrada
    fragilidad: int
    flauta: str
    t: float          # espesor del cartón
    g: float          # holgura
    d: float          # profundidad del panal
    Lb: float         # base: largo exterior
    Wb: float         # base: ancho exterior
    Hw: float         # altura de pared
    Hs: float         # altura de solapa interior (2ª pared)
    tab_w: float
    tab_l: float
    slot_off: float
    ancho_total: float
    alto_total: float
    advertencias: list = field(default_factory=list)
    encastre: bool = True
    encastre_datos: dict = field(default_factory=dict)


def calcular(e: Entrada, config: Configuracion) -> Resultado:
    e.validar()
    frag = max(TIPO_PRODUCTO[e.tipo], MATERIAL_PRODUCTO[e.material])
    try:
        g, d = config.holguras[frag]
    except KeyError as error:
        raise ValueError(f"No hay holgura configurada para fragilidad {frag}") from error
    g = e.g if e.g is not None else g
    d = e.d if e.d is not None else d

    # Selección de flauta por peso (o la forzada)
    adv = []
    if e.flauta:
        flauta = next((f for f in config.flautas if f[0] == e.flauta.upper()), None)
        if not flauta:
            raise ValueError("Flauta debe ser E, B o C")
    else:
        peso = e.peso_kg if e.peso_kg is not None else 1.0
        flauta = next((f for f in config.flautas if peso <= f[2]), config.flautas[-1])
        if e.peso_kg is None:
            adv.append("No se indicó peso: se asumió ≤ 2 kg (flauta E).")
    if e.peso_kg and e.peso_kg > config.flautas[-1][2]:
        adv.append("Peso > 15 kg: usar cartón de pared doble (BC); el modelo no lo cubre.")
    _, t, _ = flauta

    # Base exterior = producto + (holgura + 1 espesor de solapa + panal + 1 espesor de pared) por lado
    margen = g + d + 2 * t
    Lb = e.largo + 2 * margen
    Wb = e.ancho + 2 * margen
    Hw = e.alto + 2 * margen          # misma lógica en vertical (base y tapa suspenden)
    Hs = Hw - 2 * t                   # la 2ª pared entra doblada dentro de la 1ª
    tab_w = min(max(0.25 * Lb, 30.0), 60.0)
    tab_l = 15.0
    slot_off = max(8.0, 2 * t + 4)

    if e.encastre:
        off_encastre = t + d + t / 2
        solapa_trasera_l = max(0.0, Lb - 2 * (t + d))
        solapa_frontal_l = solapa_trasera_l
        solapa_lateral_l = max(0.0, Wb - 2 * (2 * t + d))
        tab_chaflan = 3.0
        tab_alto = 15.0

        def ancho_lengüeta(lado: float) -> float:
            disponible = max(0.0, lado - 2 * tab_chaflan)
            ancho = min(max(0.25 * lado, 30.0), 60.0)
            ancho = min(ancho, disponible)
            return ancho

        tab_trasera = ancho_lengüeta(solapa_trasera_l)
        tab_frontal = tab_trasera
        tab_izquierda = ancho_lengüeta(solapa_lateral_l)
        tab_derecha = tab_izquierda

        if 2 * t > d:
            adv.append(f"Orejas no recomendadas: 2·t ({2*t:.1f} mm) es mayor que d ({d:.1f} mm). "
                       "Aumenta d o reduce la flauta.")
        if solapa_trasera_l < 30 + 2 * tab_chaflan:
            adv.append("La solapa trasera/frontal es demasiado corta para una lengüeta completa de 30 mm; "
                       "se redujo su ancho automáticamente.")
        if solapa_lateral_l < 30 + 2 * tab_chaflan:
            adv.append("La solapa izquierda/derecha es demasiado corta para una lengüeta completa de 30 mm; "
                       "se redujo su ancho automáticamente.")

        resultado_encastre = dict(
            off_encastre=off_encastre,
            solapa_trasera_l=solapa_trasera_l,
            solapa_frontal_l=solapa_frontal_l,
            solapa_lateral_l=solapa_lateral_l,
            tab_trasera=tab_trasera,
            tab_frontal=tab_frontal,
            tab_izquierda=tab_izquierda,
            tab_derecha=tab_derecha,
            tab_alto=tab_alto,
            tab_chaflan=tab_chaflan,
        )
    else:
        resultado_encastre = dict(
            off_encastre=slot_off,
            solapa_trasera_l=Lb,
            solapa_frontal_l=Lb,
            solapa_lateral_l=Wb,
            tab_trasera=tab_w,
            tab_frontal=tab_w,
            tab_izquierda=tab_w,
            tab_derecha=tab_w,
            tab_alto=tab_l,
            tab_chaflan=3.0,
        )

    ancho_total = 2 * (Hs + Hw) + Lb
    alto_total = tab_l + 2 * (Hs + Hw) + Wb
    if e.encastre:
        shift = resultado_encastre["tab_alto"]
        ancho_total = 2 * shift + 2 * (Hs + Hw) + Lb
        alto_total = 2 * shift + 2 * (Hs + Hw) + Wb
    hoja_w = e.ancho_hoja if e.ancho_hoja is not None else HOJA_MAX[0]
    hoja_h = e.alto_hoja if e.alto_hoja is not None else HOJA_MAX[1]
    caben = (ancho_total <= hoja_w and alto_total <= hoja_h) or \
            (ancho_total <= hoja_h and alto_total <= hoja_w)
    if not caben:
        adv.append(f"El troquel ({ancho_total:.0f}×{alto_total:.0f} mm) no cabe en la hoja "
                   f"{hoja_w:.0f}×{hoja_h:.0f} mm.")
    resultado = Resultado(e, frag, flauta[0], t, g, d, Lb, Wb, Hw, Hs, tab_w, tab_l,
                          slot_off, ancho_total, alto_total, adv, e.encastre)
    resultado.encastre_datos = resultado_encastre
    return resultado


# ------------------------------------------------------------- geometría ----
def geometria(r: Resultado):
    """Coordenadas en mm. Origen (0,0) = esquina superior izquierda de la hoja
    (incluye la lengüeta). Eje Y hacia abajo."""
    if r.encastre:
        d = r.encastre_datos
        tab_l = d["tab_alto"]
        chaflan = d["tab_chaflan"]
        tab_t = d["tab_trasera"]
        tab_f = d["tab_frontal"]
        tab_i = d["tab_izquierda"]
        tab_derecha = d["tab_derecha"]
        flap_t = d["solapa_trasera_l"]
        flap_f = d["solapa_frontal_l"]
        flap_l = d["solapa_lateral_l"]
        flap_r = flap_l
        off = d["off_encastre"]

        x0 = 0.0
        xShift = tab_l
        xB0 = xShift + r.Hs + r.Hw
        xB1 = xB0 + r.Lb
        xF = xB1 + r.Hw + r.Hs
        xSolapaIzq = xShift
        xParedIzq = xB0 - r.Hw
        xParedDer = xB1 + r.Hw
        xSolapaDer = xF
        yT = tab_l
        ySw = yT + r.Hs
        yB0 = ySw + r.Hw
        yB1 = yB0 + r.Wb
        yFw = yB1 + r.Hw
        yEnd = yFw + r.Hs

        back_left = xB0 + (r.Lb - flap_t) / 2
        back_right = back_left + flap_t
        back_cx = (back_left + back_right) / 2
        front_left = xB0 + (r.Lb - flap_f) / 2
        front_right = front_left + flap_f
        front_cx = (front_left + front_right) / 2
        left_top = yB0 + (r.Wb - flap_l) / 2
        left_bottom = left_top + flap_l
        left_cy = (left_top + left_bottom) / 2
        right_top = yB0 + (r.Wb - flap_r) / 2
        right_bottom = right_top + flap_r
        right_cy = (right_top + right_bottom) / 2

        contorno = [
            (back_left, yT),
            (back_cx - tab_t / 2, yT),
            (back_cx - tab_t / 2 + chaflan, 0.0),
            (back_cx + tab_t / 2 - chaflan, 0.0),
            (back_cx + tab_t / 2, yT),
            (back_right, yT),
            (back_right, ySw),
            (xB1, ySw),
            (xB1, yB0),
            (xParedDer, yB0),
            (xParedDer, right_top),
            (xSolapaDer, right_top),
            (xSolapaDer + tab_l, right_cy - tab_derecha / 2),
            (xSolapaDer + tab_l, right_cy - tab_derecha / 2 + chaflan),
            (xSolapaDer + tab_l, right_cy + tab_derecha / 2 - chaflan),
            (xSolapaDer + tab_l, right_cy + tab_derecha / 2),
            (xSolapaDer, right_bottom),
            (xParedDer, right_bottom),
            (xParedDer, yB1),
            (xB1, yB1),
            (xB1, yFw),
            (front_right, yFw),
            (front_right, yEnd),
            (front_cx + tab_f / 2, yEnd),
            (front_cx + tab_f / 2 - chaflan, yEnd + tab_l),
            (front_cx - tab_f / 2 + chaflan, yEnd + tab_l),
            (front_cx - tab_f / 2, yEnd),
            (front_left, yEnd),
            (front_left, yFw),
            (xB0, yFw),
            (xB0, yB1),
            (xParedIzq, yB1),
            (xParedIzq, left_bottom),
            (xSolapaIzq, left_bottom),
            (xSolapaIzq - tab_l, left_cy + tab_i / 2),
            (xSolapaIzq - tab_l, left_cy + tab_i / 2 - chaflan),
            (xSolapaIzq - tab_l, left_cy - tab_i / 2 + chaflan),
            (xSolapaIzq - tab_l, left_cy - tab_i / 2),
            (xSolapaIzq, left_top),
            (xParedIzq, left_top),
            (xParedIzq, yB0),
            (xB0, yB0),
            (xB0, ySw),
            (back_left, ySw),
        ]

        pliegues = [
            ((back_cx - tab_t / 2, yT), (back_cx + tab_t / 2, yT)),
            ((back_left, ySw), (back_right, ySw)),
            ((xB0, ySw), (xB1, ySw)),
            ((xB0, yB0), (xB1, yB0)),
            ((xB0, yB1), (xB1, yB1)),
            ((front_left, yFw), (front_right, yFw)),
            ((front_left, yEnd), (front_right, yEnd)),
            ((front_cx - tab_f / 2, yEnd), (front_cx + tab_f / 2, yEnd)),
            ((xB0, yB0), (xB0, yB1)),
            ((xB1, yB0), (xB1, yB1)),
            ((xParedIzq, yB0), (xParedIzq, yB1)),
            ((xParedDer, yB0), (xParedDer, yB1)),
            ((xSolapaIzq, left_top), (xSolapaIzq, left_bottom)),
            ((xSolapaDer, right_top), (xSolapaDer, right_bottom)),
        ]

        ranuras = [
            {"id": "R1", "orientacion": "horizontal",
             "p1": (back_cx - (tab_t + 1) / 2, yB0 + off),
             "p2": (back_cx + (tab_t + 1) / 2, yB0 + off),
             "lengüeta": "L1", "ancho": tab_t + 1},
            {"id": "R2", "orientacion": "vertical",
             "p1": (xB0 + off, left_cy - (tab_i + 1) / 2),
             "p2": (xB0 + off, left_cy + (tab_i + 1) / 2),
             "lengüeta": "L2", "ancho": tab_i + 1},
            {"id": "R3", "orientacion": "horizontal",
             "p1": (front_cx - (tab_f + 1) / 2, yB1 - off),
             "p2": (front_cx + (tab_f + 1) / 2, yB1 - off),
             "lengüeta": "L3", "ancho": tab_f + 1},
            {"id": "R4", "orientacion": "vertical",
             "p1": (xB1 - off, right_cy - (tab_derecha + 1) / 2),
             "p2": (xB1 - off, right_cy + (tab_derecha + 1) / 2),
             "lengüeta": "L4", "ancho": tab_derecha + 1},
        ]

        paneles = [
            ("BASE", (xB0, yB0), (xB1, yB1)),
            ("pared trasera", (xB0, ySw), (xB1, yB0)),
            ("pared frontal", (xB0, yB1), (xB1, yFw)),
            ("pared izquierda", (xParedIzq, yB0), (xB0, yB1)),
            ("pared derecha", (xB1, yB0), (xParedDer, yB1)),
            ("solapa trasera", (back_left, yT), (back_right, ySw)),
            ("solapa frontal", (front_left, yFw), (front_right, yEnd)),
            ("solapa izquierda", (xSolapaIzq, left_top), (xParedIzq, left_bottom)),
            ("solapa derecha", (xParedDer, right_top), (xSolapaDer, right_bottom)),
        ]

        lengüetas = [
            ("L1", [(back_cx-tab_t/2, yT), (back_cx-tab_t/2+chaflan, 0),
                    (back_cx+tab_t/2-chaflan, 0), (back_cx+tab_t/2, yT)], tab_t),
            ("L2", [(xSolapaIzq, left_cy-tab_i/2),
                    (xSolapaIzq-tab_l, left_cy-tab_i/2+chaflan),
                    (xSolapaIzq-tab_l, left_cy+tab_i/2-chaflan),
                    (xSolapaIzq, left_cy+tab_i/2)], tab_i),
            ("L3", [(front_cx-tab_f/2, yEnd),
                    (front_cx-tab_f/2+chaflan, yEnd+tab_l),
                    (front_cx+tab_f/2-chaflan, yEnd+tab_l),
                    (front_cx+tab_f/2, yEnd)], tab_f),
            ("L4", [(xSolapaDer, right_cy-tab_derecha/2),
                    (xSolapaDer+tab_l, right_cy-tab_derecha/2+chaflan),
                    (xSolapaDer+tab_l, right_cy+tab_derecha/2-chaflan),
                    (xSolapaDer, right_cy+tab_derecha/2)], tab_derecha),
        ]

        return dict(
            x0=x0, xB0=xB0, xB1=xB1, xF=xF, yT=yT, ySw=ySw, yB0=yB0, yB1=yB1,
            yFw=yFw, yEnd=yEnd, cx=back_cx, contorno=contorno, pliegues=pliegues,
            ranuras=ranuras, ranura=ranuras[0],
            off_encastre=off, tab_l=tab_l, back_left=back_left, back_right=back_right,
            back_cx=back_cx, front_left=front_left, front_right=front_right, front_cx=front_cx,
            left_top=left_top, left_bottom=left_bottom, left_cy=left_cy,
            right_top=right_top, right_bottom=right_bottom, right_cy=right_cy,
            xSolapaIzq=xSolapaIzq, xParedIzq=xParedIzq,
            xParedDer=xParedDer, xSolapaDer=xSolapaDer,
            paneles=paneles,
            lengüetas=lengüetas,
            tabs={"L1": tab_t, "L2": tab_i, "L3": tab_f, "L4": tab_derecha},
            orden_puntos=[
                (xB0-30, yB0-30),
                (xParedIzq-12, ySw-12),
                (xSolapaIzq+r.Hs-12, left_top+12),
                (back_cx, yT-tab_l/2),
                (ranuras[0]["p1"][0]-120, ranuras[0]["p1"][1]-120),
            ],
        )

    x0, xB0 = 0.0, r.Hs + r.Hw
    xB1 = xB0 + r.Lb
    xF = xB1 + r.Hw + r.Hs
    yT = r.tab_l
    ySw = yT + r.Hs            # fin solapa trasera / inicio pared trasera
    yB0 = ySw + r.Hw           # inicio base
    yB1 = yB0 + r.Wb           # fin base
    yFw = yB1 + r.Hw           # fin pared frontal
    yEnd = yFw + r.Hs          # fin solapa frontal
    cx = (xB0 + xB1) / 2
    tw, tl = r.tab_w, r.tab_l
    taper = 3.0
    slot_y = yB1 - r.slot_off
    contorno = [
        (xB0, yT), (cx - tw / 2, yT), (cx - tw / 2 + taper, yT - tl),
        (cx + tw / 2 - taper, yT - tl), (cx + tw / 2, yT), (xB1, yT),
        (xB1, yB0), (xF, yB0), (xF, yB1), (xB1, yB1), (xB1, yEnd),
        (xB0, yEnd), (xB0, yB1), (x0, yB1), (x0, yB0), (xB0, yB0),
    ]
    pliegues = [
        ((cx - tw / 2, yT), (cx + tw / 2, yT)),            # raíz de la lengüeta
        ((xB0, ySw), (xB1, ySw)),                          # solapa trasera | pared trasera
        ((xB0, yB0), (xB1, yB0)),                          # pared trasera | base
        ((xB0, yB1), (xB1, yB1)),                          # base | pared frontal
        ((xB0, yFw), (xB1, yFw)),                          # pared frontal | solapa frontal
        ((r.Hs, yB0), (r.Hs, yB1)),                        # solapa izq | pared izq
        ((xB0, yB0), (xB0, yB1)),                          # pared izq | base
        ((xB1, yB0), (xB1, yB1)),                          # base | pared der
        ((xB1 + r.Hw, yB0), (xB1 + r.Hw, yB1)),            # pared der | solapa der
    ]
    ranura = ((cx - tw / 2, slot_y), (cx + tw / 2, slot_y))
    return dict(x0=x0, xB0=xB0, xB1=xB1, xF=xF, yT=yT, ySw=ySw, yB0=yB0, yB1=yB1,
                yFw=yFw, yEnd=yEnd, cx=cx, contorno=contorno, pliegues=pliegues,
                ranura=ranura, ranuras=[], slot_y=slot_y,
                back_cx=cx, back_left=cx-tw/2, back_right=cx+tw/2,
                front_cx=cx, front_left=cx-tw/2, front_right=cx+tw/2,
                left_top=yB0, left_bottom=yB1, left_cy=(yB0+yB1)/2,
                right_top=yB0, right_bottom=yB1, right_cy=(yB0+yB1)/2,
                xSolapaIzq=x0, xParedIzq=r.Hs,
                xParedDer=xB1+r.Hw, xSolapaDer=xF,
                paneles=[
                    ("BASE", (xB0, yB0), (xB1, yB1)),
                    ("pared trasera", (xB0, ySw), (xB1, yB0)),
                    ("pared frontal", (xB0, yB1), (xB1, yFw)),
                    ("pared izquierda", (r.Hs, yB0), (xB0, yB1)),
                    ("pared derecha", (xB1, yB0), (xB1+r.Hw, yB1)),
                    ("solapa trasera", (xB0, yT), (xB1, ySw)),
                    ("solapa frontal", (xB0, yFw), (xB1, yEnd)),
                    ("solapa izquierda", (x0, yB0), (r.Hs, yB1)),
                    ("solapa derecha", (xB1+r.Hw, yB0), (xF, yB1)),
                ],
                lengüetas=[],
                tabs={})


def parametros_tira_panal(largo: float, profundidad: float) -> tuple[int, float, float, float]:
    """Calcula periodo, tramo plano y longitud desarrollada de una tira."""
    if largo <= 0 or profundidad <= 0:
        raise ValueError("La longitud y profundidad del panal deben ser positivas")
    lado = profundidad / sqrt(3)
    periodo_ideal = 3 * lado
    n = max(1, round(largo / periodo_ideal))
    periodo = largo / n
    tramo_plano = periodo / 2 - lado / 2
    if tramo_plano < 0:
        tramo_plano = 0
    largo_desarrollado = 2 * n * (tramo_plano + lado)
    return n, periodo, tramo_plano, largo_desarrollado


def perfil_tira_panal(n: int, tramo_plano: float, profundidad: float) -> list[tuple[float, float]]:
    """Devuelve el perfil A de una tira; el perfil B es su espejo."""
    lado = profundidad / sqrt(3)
    avance = lado / 2
    subida = profundidad / 2
    x = tramo_plano / 2
    puntos = [(0.0, 0.0), (x, 0.0)]
    for i in range(n):
        x += avance
        puntos.append((x, subida))
        x += tramo_plano
        puntos.append((x, subida))
        x += avance
        puntos.append((x, 0.0))
        if i < n - 1:
            x += tramo_plano
            puntos.append((x, 0.0))
    x += tramo_plano / 2
    puntos.append((x, 0.0))
    return puntos


def tiras_panal(r: Resultado):
    """Tiras hexagonales del panal, dos perfiles espejo por pared."""
    alto = round(r.Hs, 1)
    largo_trasera_frontal = r.Lb - 2 * r.t
    largo_lateral = r.Wb - 2 * (r.t + r.d)

    n_tf, p_tf, f_tf, largo_desarrollado_tf = parametros_tira_panal(largo_trasera_frontal, r.d)
    n_lr, p_lr, f_lr, largo_desarrollado_lr = parametros_tira_panal(largo_lateral, r.d)
    return [
        {
            "cantidad": 4,
            "tipo": "frontal/trasera",
            "largo": round(largo_trasera_frontal, 2),
            "largo_desarrollado": round(largo_desarrollado_tf, 2),
            "alto": alto,
            "profundidad": r.d,
            "n_tramos": n_tf,
            "periodo": p_tf,
            "tramo": p_tf,
            "tramo_plano": f_tf,
        },
        {
            "cantidad": 4,
            "tipo": "laterales",
            "largo": round(largo_lateral, 2),
            "largo_desarrollado": round(largo_desarrollado_lr, 2),
            "alto": alto,
            "profundidad": r.d,
            "n_tramos": n_lr,
            "periodo": p_lr,
            "tramo": p_lr,
            "tramo_plano": f_lr,
        },
    ]


def paredes_panal_frontales(r: Resultado) -> list[dict]:
    """Devuelve las cuatro paredes destinadas al panal frontal/trasero.

    Las dimensiones se derivan del producto y de las paredes calculadas:
    ancho = base exterior menos dos espesores; alto = altura interior Hs.
    """
    largo = r.Lb - 2 * r.t
    if largo <= 0:
        raise ValueError("La pared frontal del panal no puede tener largo negativo")
    if r.Hs <= 0:
        raise ValueError("La pared frontal del panal no puede tener alto negativo")

    paredes = []
    for etiqueta in ("F1", "F2", "F3", "F4"):
        paredes.append({
            "etiqueta": etiqueta,
            "tipo": "frontal/trasera",
            "largo": round(largo, 2),
            "alto": round(r.Hs, 2),
            "profundidad": r.d,
        })
    return paredes


def layout_salida(r: Resultado) -> dict:
    """Cuadros de texto, círculos y recuadros calculados solo por datos."""
    g = geometria(r)
    detail_w, detail_h = 300.0, 210.0
    margin = 35.0
    ox = margin + detail_w + 70
    oy = margin + detail_h + 50
    xs = [p[0] for p in g["contorno"]]
    ys = [p[1] for p in g["contorno"]]
    cross_w = max(xs) - min(xs)
    cross_h = max(ys) - min(ys)
    W = detail_w * 2 + cross_w + 260
    H = detail_h * 2 + cross_h + 220

    tr = lambda p: (p[0] + ox, p[1] + oy)
    panel_rects = {}
    texto_rects = []
    for nombre, p1, p2 in g["paneles"]:
        aa, bb = tr(p1), tr(p2)
        rect = Rectangulo(min(aa[0], bb[0]), min(aa[1], bb[1]),
                          max(aa[0], bb[0]), max(aa[1], bb[1]))
        panel_rects[nombre] = rect
        texto_rects.append(Rectangulo(rect.x1+8, rect.y1+8,
                                      rect.x2-8, rect.y2-8))

    puntos = [
        (ox+20, oy+20),
        (ox+20, oy+45),
        (ox+20, oy+cross_h-20),
        (ox+cross_w/2, oy-20),
        (ox-20, oy+cross_h/2),
    ]
    circulos = []

    recuadros = {
        "A": Rectangulo(margin, margin+35, margin+detail_w, margin+35+detail_h),
        "B": Rectangulo(W-margin-detail_w, margin+35,
                        W-margin, margin+35+detail_h),
        "leyenda": Rectangulo(margin, H-detail_h-margin,
                              margin+detail_w, H-margin),
        "panal": Rectangulo(W-margin-detail_w, H-detail_h-margin,
                            W-margin, H-margin),
    }
    cotas_rects = [
        Rectangulo(ox-55, oy-30, ox+cross_w+55, oy+cross_h+100),
    ]
    return {
        "W": W, "H": H, "ox": ox, "oy": oy,
        "cross_w": cross_w, "cross_h": cross_h,
        "panel_rects": panel_rects, "texto_rects": texto_rects,
        "circulos": circulos, "recuadros": recuadros,
        "cotas_rects": cotas_rects,
    }


# -------------------------------------------------------------- pasos -------
def pasos(r: Resultado) -> list[str]:
    g = geometria(r)
    f = lambda v: f"{v:.1f}"
    e = r.entrada
    P = []
    P.append(f"PARÁMETROS: producto {f(e.largo)}×{f(e.ancho)}×{f(e.alto)} mm · fragilidad {r.fragilidad}/4 · "
             f"cartón flauta {r.flauta} (t = {r.t} mm) · holgura g = {r.g} mm · panal d = {r.d} mm.")
    P.append(f"Margen por lado = g + d + 2t = {r.g} + {r.d} + {2*r.t} = {f(r.g+r.d+2*r.t)} mm.")
    P.append(f"BASE exterior = {f(r.Lb)} × {f(r.Wb)} mm (largo + 2·margen, ancho + 2·margen). "
             f"Altura de pared Hw = {f(r.Hw)} mm. Solapa interior Hs = Hw − 2t = {f(r.Hs)} mm.")
    P.append(f"1) Hoja mínima necesaria: {f(r.ancho_total)} × {f(r.alto_total)} mm. "
             f"Define el origen (0,0) en la esquina superior izquierda (eje Y hacia abajo).")
    P.append(f"2) Marca las columnas verticales en X = 0 · {f(r.Hs)} · {f(g['xB0'])} · {f(g['xB1'])} · "
             f"{f(g['xB1']+r.Hw)} · {f(g['xF'])}.")
    P.append(f"3) Marca las filas horizontales en Y = {f(g['yT'])} · {f(g['ySw'])} · {f(g['yB0'])} · "
             f"{f(g['yB1'])} · {f(g['yFw'])} · {f(g['yEnd'])}.")
    P.append(f"4) Traza la BASE: rectángulo de ({f(g['xB0'])}, {f(g['yB0'])}) a ({f(g['xB1'])}, {f(g['yB1'])}).")
    P.append(f"5) Brazos laterales: pared izq. {f(r.Hw)}×{f(r.Wb)} y solapa izq. {f(r.Hs)}×{f(r.Wb)} a la izquierda "
             f"de la base; pared der. y solapa der. iguales a la derecha.")
    P.append(f"6) Brazos verticales: pared trasera {f(r.Lb)}×{f(r.Hw)} y solapa trasera {f(r.Lb)}×{f(r.Hs)} sobre la base; "
             f"pared frontal y solapa frontal iguales debajo.")
    if r.encastre:
        d = r.encastre_datos
        P.append(f"7) SOLAPAS ACORTADAS: trasera/frontal = {f(d['solapa_trasera_l'])} mm de largo "
                 f"(Lb − 2(t+d)), centradas sobre sus paredes; izquierda/derecha = "
                 f"{f(d['solapa_lateral_l'])} mm (Wb − 2(2t+d)), centradas sobre sus paredes.")
        P.append(f"8) LENGÜETAS: L1 sobre trasera: ancho {f(d['tab_trasera'])} mm; "
                 f"L2 sobre izquierda: ancho {f(d['tab_izquierda'])} mm; "
                 f"L3 sobre frontal: ancho {f(d['tab_frontal'])} mm; "
                 f"L4 sobre derecha: ancho {f(d['tab_derecha'])} mm. Alto común 15 mm, chaflán 3 mm.")
        P.append(f"9) CORTE DE ORIGEN: desplaza X = {f(d['tab_alto'])} mm y Y = {f(d['tab_alto'])} mm "
                 "para que todas las lengüetas queden dentro del lienzo.")
        for ranura in g["ranuras"]:
            p1, p2 = ranura["p1"], ranura["p2"]
            P.append(f"10) RANURA {ranura['id']} ↔ {ranura['lengüeta']}: "
                     f"de ({f(p1[0])}, {f(p1[1])}) a ({f(p2[0])}, {f(p2[1])}) mm; "
                     f"largo {f(ranura['ancho'])} mm, corte continuo.")
        P.append(f"11) DISTANCIA CALIBRABLE DE RANURA: t+d+t/2 = "
                 f"{r.t:.1f}+{r.d:.1f}+{r.t/2:.1f} = {f(d['off_encastre'])} mm "
                 "desde el pliegue correspondiente.")
        P.append("12) LÍNEAS DE CORTE: recorre una sola vez el contorno cerrado; "
                 "incluye las cuatro lengüetas como parte del polígono.")
        P.append("13) LÍNEAS DE PLIEGUE: sólo hundir, nunca cortar:")
        for (a, b) in g["pliegues"]:
            P.append(f"     de ({f(a[0])}, {f(a[1])}) a ({f(b[0])}, {f(b[1])})")
        P.append("14) PANAL: usa tiras recalculadas sin ocupar las esquinas ni orejas; "
                 "trasera/frontal = Lb−2t−2·ancho_oreja y lateral = Wb−2t−2d.")
        P.append("15) ARMADO PREVIO AL ENCASTRE: 1) levanta las 4 paredes; "
                 "2) dobla las orejas hacia adentro; 3) inserta el panal; "
                 "4) dobla las solapas sobre orejas y panal; "
                 "5) encastra L1↔R1, L2↔R2, L3↔R3 y L4↔R4.")
        P.append("16) CALIDAD: tolerancia de corte ±1 mm; prueba de caída a 1 m sobre 6 caras y esquinas.")
        for advertencia in r.advertencias:
            P.append(f"ADVERTENCIA: {advertencia}")
        return P

    P.append(f"7) Lengüeta de cierre sobre la solapa trasera, centrada en X = {f(g['cx'])}: base {f(r.tab_w)} mm, "
             f"alto {f(r.tab_l)} mm, con chaflán de 3 mm por lado.")
    P.append(f"8) RANURA de encastre (corte) en la base: de ({f(g['ranura'][0][0])}, {f(g['slot_y'])}) "
             f"a ({f(g['ranura'][1][0])}, {f(g['slot_y'])}).")
    P.append("9) LÍNEAS DE CORTE (continuas): recorre el contorno en este orden: " +
             " → ".join(f"({f(x)}, {f(y)})" for x, y in g["contorno"]) + " → cierre.")
    P.append("10) LÍNEAS DE PLIEGUE (punteadas, solo hundir sin cortar):")
    for (a, b) in g["pliegues"]:
        P.append(f"     de ({f(a[0])}, {f(a[1])}) a ({f(b[0])}, {f(b[1])})")
    P.append("11) PANAL: corta y pliega en zigzag las tiras: " +
             "; ".join(f"{s['cantidad']} de {s['largo']} mm (alto {s['alto']} mm, prof. {s['profundidad']} mm)"
                       for s in tiras_panal(r)) + ".")
    P.append("12) ARMADO: dobla las paredes hacia arriba, dobla cada solapa hacia adentro formando la 2ª pared, "
             "inserta las tiras de panal en el hueco, coloca el producto y encastra la lengüeta en la ranura.")
    P.append("13) CALIDAD: tolerancia de corte ±1 mm; prueba de caída a 1 m sobre 6 caras y esquinas; ajusta g y d si falla.")
    return P


# ------------------------------------------------------------------ SVG -----
def svg_legacy(r: Resultado, escala: float = 1.0) -> str:
    g = geometria(r)
    m = 40.0
    W = r.ancho_total + 2 * m + 60
    H = r.alto_total + 2 * m + 40
    ox, oy = m + 20, m + 10
    tr = lambda p: (p[0] + ox, p[1] + oy)
    pts = " ".join(f"{tr(p)[0]:.2f},{tr(p)[1]:.2f}" for p in g["contorno"])
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.1f} {H:.1f}" '
           f'width="{W*escala*2:.0f}" height="{H*escala*2:.0f}" font-family="Arial, sans-serif">',
           f'<rect width="100%" height="100%" fill="#ffffff"/>',
           f'<text x="{ox}" y="22" font-size="14" font-weight="bold">NIDO · troquel para '
           f'{r.entrada.largo:g}×{r.entrada.ancho:g}×{r.entrada.alto:g} mm ({r.entrada.tipo}, flauta {r.flauta})</text>']
    # rellenos por zona
    def rect(x1, y1, x2, y2, fill, label, rot=False):
        a, b = tr((x1, y1)), tr((x2, y2))
        out.append(f'<rect x="{a[0]:.2f}" y="{a[1]:.2f}" width="{b[0]-a[0]:.2f}" height="{b[1]-a[1]:.2f}" fill="{fill}"/>')
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        size = max(6, min(11, (b[0] - a[0]) / 9, (b[1] - a[1]) / 3))
        t = f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="{size:.1f}" text-anchor="middle" fill="#333"'
        if rot: t += f' transform="rotate(-90 {cx:.1f} {cy:.1f})"'
        out.append(t + f'>{label}</text>')
    if r.encastre:
        panel_colores = {
            "BASE": "#ebd5a4",
            "pared trasera": "#f2e4c4",
            "pared frontal": "#f2e4c4",
            "pared izquierda": "#f2e4c4",
            "pared derecha": "#f2e4c4",
            "solapa trasera": "#f8eed8",
            "solapa frontal": "#f8eed8",
            "solapa izquierda": "#f8eed8",
            "solapa derecha": "#f8eed8",
        }
        for nombre, p1, p2 in g["paneles"]:
            rot = "izquierda" in nombre or "derecha" in nombre
            rect(p1[0], p1[1], p2[0], p2[1], panel_colores[nombre],
                 nombre if "pared" not in nombre else nombre, rot)
    else:
        rect(g['xB0'], g['yB0'], g['xB1'], g['yB1'], "#ebd5a4", "BASE")
        rect(g['xB0'], g['ySw'], g['xB1'], g['yB0'], "#f2e4c4", "pared trasera")
        rect(g['xB0'], g['yB1'], g['xB1'], g['yFw'], "#f2e4c4", "pared frontal")
        rect(g['xB0'], g['yT'], g['xB1'], g['ySw'], "#f8eed8", "solapa int. (2ª pared)")
        rect(g['xB0'], g['yFw'], g['xB1'], g['yEnd'], "#f8eed8", "solapa int. (2ª pared)")
        rect(r.Hs, g['yB0'], g['xB0'], g['yB1'], "#f2e4c4", "pared izq.", True)
        rect(g['xB1'], g['yB0'], g['xB1'] + r.Hw, g['yB1'], "#f2e4c4", "pared der.", True)
        rect(0, g['yB0'], r.Hs, g['yB1'], "#f8eed8", "solapa int.", True)
        rect(g['xB1'] + r.Hw, g['yB0'], g['xF'], g['yB1'], "#f8eed8", "solapa int.", True)
    # pliegues
    for a, b in g["pliegues"]:
        a, b = tr(a), tr(b)
        out.append(f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}" '
                   f'stroke="#2e7d4f" stroke-width="1.2" stroke-dasharray="6 4"/>')
    # corte
    out.append(f'<polygon points="{pts}" fill="none" stroke="#222" stroke-width="1.8" stroke-linejoin="round"/>')
    if r.encastre:
        for ranura in g["ranuras"]:
            a, b = tr(ranura["p1"]), tr(ranura["p2"])
            out.append(f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}" '
                       f'stroke="#1f6f8b" stroke-width="3.0"/>')
            px, py = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            out.append(f'<text x="{px:.1f}" y="{py-4:.1f}" font-size="9" text-anchor="middle" '
                       f'fill="#1f6f8b" font-weight="bold">{ranura["lengüeta"]}↔{ranura["id"]}</text>')
        for label, cx, cy in (
            ("L1", g["back_cx"], g["yT"] - r.encastre_datos["tab_alto"] / 2),
            ("L2", r.encastre_datos["tab_alto"] / 2, g["left_cy"]),
            ("L3", g["front_cx"], g["yEnd"] + r.encastre_datos["tab_alto"] / 2),
            ("L4", g["xF"] + r.encastre_datos["tab_alto"] / 2, g["right_cy"]),
        ):
            p = tr((cx, cy))
            out.append(f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="9" fill="#fff" stroke="#1f6f8b" stroke-width="1"/>'
                       f'<text x="{p[0]:.1f}" y="{p[1]+3:.1f}" font-size="9" text-anchor="middle" '
                       f'fill="#1f6f8b" font-weight="bold">{label}</text>')
    else:
        a, b = tr(g["ranura"][0]), tr(g["ranura"][1])
        out.append(f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}" stroke="#222" stroke-width="2.4"/>')

    # cotas
    def cota_h(xa, xb, y, txt):
        a, b = tr((xa, y)), tr((xb, y))
        out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="#c0392b" stroke-width="0.8" '
                   f'marker-start="url(#ar)" marker-end="url(#ar)"/>')
        out.append(f'<text x="{(a[0]+b[0])/2:.1f}" y="{a[1]-3:.1f}" font-size="9" fill="#c0392b" text-anchor="middle">{txt}</text>')
    def cota_v(x, ya, yb, txt):
        a, b = tr((x, ya)), tr((x, yb))
        out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="#c0392b" stroke-width="0.8" '
                   f'marker-start="url(#ar)" marker-end="url(#ar)"/>')
        out.append(f'<text x="{a[0]-4:.1f}" y="{(a[1]+b[1])/2:.1f}" font-size="9" fill="#c0392b" text-anchor="end" '
                   f'transform="rotate(-90 {a[0]-4:.1f} {(a[1]+b[1])/2:.1f})" dy="0">{txt}</text>')
    out.insert(1, '<defs><marker id="ar" viewBox="0 0 6 6" refX="3" refY="3" markerWidth="5" markerHeight="5" '
                  'orient="auto-start-reverse"><path d="M0,0 L6,3 L0,6 z" fill="#c0392b"/></marker></defs>')
    cota_h(g['xB0'], g['xB1'], g['yEnd'] + 16, f"{r.Lb:.1f}")
    cota_h(0, g['xF'], g['yEnd'] + 32, f"{r.ancho_total:.1f}")
    cota_v(-14, g['yB0'], g['yB1'], f"{r.Wb:.1f}")
    cota_v(-30, 0, g['yEnd'], f"{r.alto_total:.1f}")
    cota_h(r.Hs, g['xB0'], g['yT'] - r.tab_l - 6, f"Hw {r.Hw:.1f}")
    # leyenda
    ly = H - 16
    out.append(f'<line x1="{ox}" y1="{ly}" x2="{ox+30}" y2="{ly}" stroke="#222" stroke-width="1.8"/>'
               f'<text x="{ox+36}" y="{ly+3}" font-size="9">corte</text>'
               f'<line x1="{ox+80}" y1="{ly}" x2="{ox+110}" y2="{ly}" stroke="#2e7d4f" stroke-width="1.2" stroke-dasharray="6 4"/>'
               f'<text x="{ox+116}" y="{ly+3}" font-size="9">pliegue</text>'
               f'<text x="{ox+170}" y="{ly+3}" font-size="9" fill="#c0392b">cotas en mm · sin pegante, sin cinta, sin grapas</text>')
    out.append("</svg>")
    return "\n".join(out)


def svg(r: Resultado, escala: float = 1.0) -> str:
    g = geometria(r)
    salida = layout_salida(r)
    detail_w, detail_h = 300.0, 210.0
    margin = 35.0
    ox, oy = salida["ox"], salida["oy"]
    tr = lambda p: (p[0] + ox, p[1] + oy)
    xs_reales = [p[0] for p in g["contorno"]]
    ys_reales = [p[1] for p in g["contorno"]]
    cross_w = max(xs_reales) - min(xs_reales)
    cross_h = max(ys_reales) - min(ys_reales)
    W, H = salida["W"], salida["H"]

    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {W:.1f} {H:.1f}" width="{W*escala*2:.0f}" height="{H*escala*2:.0f}" '
        'font-family="Arial, sans-serif">',
        '<defs>'
        '<marker id="ar" viewBox="0 0 6 6" refX="3" refY="3" markerWidth="5" '
        'markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L6,3 L0,6 z" fill="#c0392b"/></marker>'
        '<pattern id="patron-panal" width="16" height="16" patternUnits="userSpaceOnUse">'
        '<line x1="3" y1="0" x2="3" y2="16" stroke="#c55a11" stroke-width="1" stroke-dasharray="5 3"/>'
        '<line x1="11" y1="0" x2="11" y2="16" stroke="#2e7d4f" stroke-width="1" stroke-dasharray="8 3 2 3"/>'
        '<line x1="3" y1="8" x2="11" y2="8" stroke="#c55a11" stroke-width="0.7" stroke-dasharray="3 3"/>'
        '</pattern>'
        '</defs>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{margin:.1f}" y="24" font-size="14" font-weight="bold">'
        f'NIDO · plano de fabricación · {formato_mm(r.entrada.largo)}×'
        f'{formato_mm(r.entrada.ancho)}×{formato_mm(r.entrada.alto)} mm '
        f'({r.entrada.tipo} · flauta {r.flauta})</text>',
    ]

    colores = {
        "BASE": "#ebd5a4",
        "pared trasera": "#f2e4c4", "pared frontal": "#f2e4c4",
        "pared izquierda": "#f2e4c4", "pared derecha": "#f2e4c4",
        "solapa trasera": "#f8eed8", "solapa frontal": "#f8eed8",
        "solapa izquierda": "#f8eed8", "solapa derecha": "#f8eed8",
    }
    for nombre, p1, p2 in g["paneles"]:
        aa, bb = tr(p1), tr(p2)
        x1, x2 = sorted((aa[0], bb[0]))
        y1, y2 = sorted((aa[1], bb[1]))
        out.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2-x1:.1f}" '
                   f'height="{y2-y1:.1f}" fill="{colores[nombre]}" stroke="#ffffff" stroke-width="0.5"/>')
        if nombre in ("pared frontal", "pared trasera"):
            out.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2-x1:.1f}" '
                       f'height="{y2-y1:.1f}" fill="url(#patron-panal)" opacity="0.82"/>')
        cx, cy = (x1+x2)/2, (y1+y2)/2
        ancho = abs(p2[0]-p1[0])
        alto = abs(p2[1]-p1[1])
        if "izquierda" in nombre or "derecha" in nombre:
            out.append(f'<text x="{cx:.1f}" y="{cy-3:.1f}" font-size="9" text-anchor="middle" '
                       f'transform="rotate(-90 {cx:.1f} {cy:.1f})"><tspan font-weight="bold">{nombre}</tspan>'
                       f'<tspan x="{cx:.1f}" dy="12">{formato_mm(ancho)} × {formato_mm(alto)}</tspan></text>')
        else:
            out.append(f'<text x="{cx:.1f}" y="{cy-3:.1f}" font-size="9" text-anchor="middle">'
                       f'<tspan font-weight="bold">{nombre}</tspan>'
                       f'<tspan x="{cx:.1f}" dy="12">{formato_mm(ancho)} × {formato_mm(alto)}</tspan></text>')

    paredes_frontales = paredes_panal_frontales(r)[:2]
    pared_w = paredes_frontales[0]["largo"]
    pared_h = paredes_frontales[0]["alto"]
    pared_x = ox-pared_w-145
    pared_y = [oy+g["yT"], oy+g["yT"]+pared_h]
    for indice, (pared, y0) in enumerate(zip(paredes_frontales, pared_y)):
        etiqueta = f"F{indice+1} Frontal {chr(65+indice)}"
        out.append(f'<rect x="{pared_x:.1f}" y="{y0:.1f}" width="{pared_w:.1f}" '
                   f'height="{pared_h:.1f}" fill="#f2e4c4" stroke="#222" stroke-width="1.2" '
                   f'data-escala="1-mm" data-largo-mm="{formato_mm(pared["largo"])}" '
                   f'data-alto-mm="{formato_mm(pared["alto"])}"/>')
        out.append(f'<rect x="{pared_x:.1f}" y="{y0:.1f}" width="{pared_w:.1f}" '
                   f'height="{pared_h:.1f}" fill="url(#patron-panal)" opacity="0.82"/>')
        out.append(f'<text x="{pared_x+pared_w/2:.1f}" y="{y0+pared_h/2-3:.1f}" '
                   f'font-size="9" text-anchor="middle" font-weight="bold">{etiqueta}</text>')
        out.append(f'<text x="{pared_x+pared_w/2:.1f}" y="{y0+pared_h/2+11:.1f}" '
                   f'font-size="9" text-anchor="middle">'
                   f'{formato_mm(pared["largo"])} × {formato_mm(pared["alto"])}</text>')

    paredes_traseras = paredes_panal_frontales(r)[2:]
    pared_derecha_w = paredes_traseras[0]["largo"]
    pared_derecha_h = paredes_traseras[0]["alto"]
    pared_derecha_x = ox+cross_w+55
    pared_derecha_y = [oy+g["yT"], oy+g["yT"]+pared_derecha_h]
    for indice, (pared, y0) in enumerate(zip(paredes_traseras, pared_derecha_y)):
        etiqueta = f"F{indice+3} Trasera {chr(65+indice)}"
        out.append(f'<rect x="{pared_derecha_x:.1f}" y="{y0:.1f}" width="{pared_derecha_w:.1f}" '
                   f'height="{pared_derecha_h:.1f}" fill="#f2e4c4" stroke="#222" stroke-width="1.2" '
                   f'data-escala="1-mm" data-largo-mm="{formato_mm(pared["largo"])}" '
                   f'data-alto-mm="{formato_mm(pared["alto"])}"/>')
        out.append(f'<rect x="{pared_derecha_x:.1f}" y="{y0:.1f}" width="{pared_derecha_w:.1f}" '
                   f'height="{pared_derecha_h:.1f}" fill="url(#patron-panal)" opacity="0.82"/>')
        out.append(f'<text x="{pared_derecha_x+pared_derecha_w/2:.1f}" y="{y0+pared_derecha_h/2-3:.1f}" '
                   f'font-size="9" text-anchor="middle" font-weight="bold">{etiqueta}</text>')
        out.append(f'<text x="{pared_derecha_x+pared_derecha_w/2:.1f}" y="{y0+pared_derecha_h/2+11:.1f}" '
                   f'font-size="9" text-anchor="middle">'
                   f'{formato_mm(pared["largo"])} × {formato_mm(pared["alto"])}</text>')

    solapa_lateral_w = r.encastre_datos["solapa_lateral_l"]
    solapa_lateral_h = r.Hs
    solapa_izquierda_x = ox-solapa_lateral_w-145
    solapa_derecha_x = ox+cross_w+55
    solapa_y = [oy+g["yB0"], oy+g["yB0"]+solapa_lateral_h]
    for indice, y0 in enumerate(solapa_y):
        etiqueta = f"S{indice+1} Izq. {chr(65+indice)}"
        out.append(f'<rect x="{solapa_izquierda_x:.1f}" y="{y0:.1f}" '
                   f'width="{solapa_lateral_w:.1f}" height="{solapa_lateral_h:.1f}" '
                   f'fill="#f8eed8" stroke="#222" stroke-width="1.2" '
                   f'data-escala="1-mm" data-largo-mm="{formato_mm(solapa_lateral_w)}" '
                   f'data-alto-mm="{formato_mm(solapa_lateral_h)}"/>')
        out.append(f'<rect x="{solapa_izquierda_x:.1f}" y="{y0:.1f}" '
                   f'width="{solapa_lateral_w:.1f}" height="{solapa_lateral_h:.1f}" '
                   f'fill="url(#patron-panal)" opacity="0.82"/>')
        out.append(f'<text x="{solapa_izquierda_x+solapa_lateral_w/2:.1f}" '
                   f'y="{y0+solapa_lateral_h/2-3:.1f}" font-size="9" '
                   f'text-anchor="middle" font-weight="bold">{etiqueta}</text>')
        out.append(f'<text x="{solapa_izquierda_x+solapa_lateral_w/2:.1f}" '
                   f'y="{y0+solapa_lateral_h/2+11:.1f}" font-size="9" text-anchor="middle">'
                   f'{formato_mm(solapa_lateral_w)} × {formato_mm(solapa_lateral_h)}</text>')

    for indice, y0 in enumerate(solapa_y):
        etiqueta = f"S{indice+3} Der. {chr(65+indice)}"
        out.append(f'<rect x="{solapa_derecha_x:.1f}" y="{y0:.1f}" '
                   f'width="{solapa_lateral_w:.1f}" height="{solapa_lateral_h:.1f}" '
                   f'fill="#f8eed8" stroke="#222" stroke-width="1.2" '
                   f'data-escala="1-mm" data-largo-mm="{formato_mm(solapa_lateral_w)}" '
                   f'data-alto-mm="{formato_mm(solapa_lateral_h)}"/>')
        out.append(f'<rect x="{solapa_derecha_x:.1f}" y="{y0:.1f}" '
                   f'width="{solapa_lateral_w:.1f}" height="{solapa_lateral_h:.1f}" '
                   f'fill="url(#patron-panal)" opacity="0.82"/>')
        out.append(f'<text x="{solapa_derecha_x+solapa_lateral_w/2:.1f}" '
                   f'y="{y0+solapa_lateral_h/2-3:.1f}" font-size="9" '
                   f'text-anchor="middle" font-weight="bold">{etiqueta}</text>')
        out.append(f'<text x="{solapa_derecha_x+solapa_lateral_w/2:.1f}" '
                   f'y="{y0+solapa_lateral_h/2+11:.1f}" font-size="9" text-anchor="middle">'
                   f'{formato_mm(solapa_lateral_w)} × {formato_mm(solapa_lateral_h)}</text>')

    pts = " ".join(f"{tr(p)[0]:.1f},{tr(p)[1]:.1f}" for p in g["contorno"])
    out.append(f'<polygon points="{pts}" fill="none" stroke="#222" stroke-width="1.8" stroke-linejoin="round"/>')
    for a, b in g["pliegues"]:
        aa, bb = tr(a), tr(b)
        out.append(f'<line x1="{aa[0]:.1f}" y1="{aa[1]:.1f}" x2="{bb[0]:.1f}" y2="{bb[1]:.1f}" '
                   'stroke="#2e7d4f" stroke-width="1.2" stroke-dasharray="7 4"/>')
    if r.encastre:
        for ranura in g["ranuras"]:
            aa, bb = tr(ranura["p1"]), tr(ranura["p2"])
            out.append(f'<line x1="{aa[0]:.1f}" y1="{aa[1]:.1f}" x2="{bb[0]:.1f}" y2="{bb[1]:.1f}" '
                       'stroke="#1f6f8b" stroke-width="3"/>')
            px, py = (aa[0]+bb[0])/2, (aa[1]+bb[1])/2
            out.append(f'<text x="{px:.1f}" y="{py-4:.1f}" font-size="8" fill="#1f6f8b" '
                       f'text-anchor="middle" font-weight="bold">{ranura["lengüeta"]} / {ranura["id"]}</text>')
        for label, cx, cy in (
            ("L1", g["back_cx"], g["yT"]-r.encastre_datos["tab_alto"]/2),
            ("L2", r.encastre_datos["tab_alto"]/2, g["left_cy"]),
            ("L3", g["front_cx"], g["yEnd"]+r.encastre_datos["tab_alto"]/2),
            ("L4", g["xF"]-r.encastre_datos["tab_alto"]/2, g["right_cy"]),
        ):
            px, py = tr((cx, cy))
            out.append(f'<text x="{px:.1f}" y="{py+3:.1f}" font-size="9" fill="#1f6f8b" '
                       f'text-anchor="middle" font-weight="bold">{label}</text>')

    # Cotas directas sobre la cruz.
    d = r.encastre_datos
    top_y = tr((g["back_cx"], g["yT"]-12))[1]
    tx1, tx2 = tr((g["back_left"], g["yT"]-12))[0], tr((g["back_right"], g["yT"]-12))[0]
    out.append(f'<line x1="{tx1:.1f}" y1="{top_y:.1f}" x2="{tx2:.1f}" y2="{top_y:.1f}" '
               'stroke="#c0392b" stroke-width="0.8" marker-start="url(#ar)" marker-end="url(#ar)"/>'
               f'<text x="{(tx1+tx2)/2:.1f}" y="{top_y-4:.1f}" font-size="9" text-anchor="middle" fill="#c0392b">'
               f'{formato_mm(r.t+r.d)}</text>')
    lx = tr((g["xParedIzq"]-r.Hw/2, g["left_cy"]))[0]
    ly1, ly2 = tr((g["xParedIzq"], g["left_top"]))[1], tr((g["xParedIzq"], g["left_bottom"]))[1]
    out.append(f'<line x1="{lx:.1f}" y1="{ly1:.1f}" x2="{lx:.1f}" y2="{ly2:.1f}" '
               'stroke="#c0392b" stroke-width="0.8" marker-start="url(#ar)" marker-end="url(#ar)"/>'
               f'<text x="{lx-4:.1f}" y="{(ly1+ly2)/2:.1f}" font-size="9" fill="#c0392b" '
               f'text-anchor="middle" transform="rotate(-90 {lx-4:.1f} {(ly1+ly2)/2:.1f})">'
               f'{formato_mm(2*r.t+r.d)}</text>')
    # Registro y dibujo de cotas.
    cotas: list[Cota] = []
    cotas.append(Cota(r.Lb, (g["xB0"], g["yB0"]), (g["xB1"], g["yB0"]), 1))
    cotas.append(Cota(r.Wb, (g["xB0"], g["yB0"]), (g["xB0"], g["yB1"]), 1))
    cotas.append(Cota(r.Hw, (g["xB0"], g["ySw"]), (g["xB0"], g["yB0"]), 2))
    cotas.append(Cota(r.Hs, (g["xB0"], g["yT"]), (g["xB0"], g["ySw"]), 2))
    for cota in cotas:
        validar_cota(cota)

    # Cadenas horizontales.
    cy = oy + r.alto_total + 55
    xs_internal = [0, g["xSolapaIzq"], g["xParedIzq"], g["xB0"], g["xB1"],
                   g["xParedDer"], g["xSolapaDer"], g["xSolapaDer"]+r.encastre_datos["tab_alto"]]
    xs = [ox+x for x in xs_internal]
    vals = [r.encastre_datos["tab_alto"], r.Hs, r.Hw, r.Lb, r.Hw, r.Hs,
            r.encastre_datos["tab_alto"]]
    for i, val in enumerate(vals):
        y = cy + (10 if i % 2 == 0 else 0)
        out.append(f'<line x1="{xs[i]:.1f}" y1="{y:.1f}" x2="{xs[i+1]:.1f}" y2="{y:.1f}" '
                   'stroke="#c0392b" stroke-width="0.8" marker-start="url(#ar)" marker-end="url(#ar)"/>')
        out.append(f'<text x="{(xs[i]+xs[i+1])/2:.1f}" y="{y-4:.1f}" font-size="9" '
                   f'text-anchor="middle" fill="#c0392b">{formato_mm(val)}</text>')
    out.append(f'<line x1="{ox:.1f}" y1="{cy+32:.1f}" x2="{ox+cross_w:.1f}" y2="{cy+32:.1f}" '
               'stroke="#c0392b" stroke-width="0.8" marker-start="url(#ar)" marker-end="url(#ar)"/>')
    out.append(f'<text x="{ox+cross_w/2:.1f}" y="{cy+29:.1f}" font-size="9" '
               f'text-anchor="middle" fill="#c0392b">{formato_mm(cross_w)} total</text>')

    # Cadena vertical.
    cx = ox - 55
    ys_internal = [0, g["yT"], g["ySw"], g["yB0"], g["yB1"], g["yFw"], g["yEnd"],
                   g["yEnd"]+r.encastre_datos["tab_alto"]]
    ys = [oy+y for y in ys_internal]
    vals = [r.tab_l, r.Hs, r.Hw, r.Wb, r.Hw, r.Hs, r.tab_l]
    for i, val in enumerate(vals):
        x = cx-(12 if i % 2 == 0 else 0)
        out.append(f'<line x1="{x:.1f}" y1="{ys[i]:.1f}" x2="{x:.1f}" y2="{ys[i+1]:.1f}" '
                   'stroke="#c0392b" stroke-width="0.8" marker-start="url(#ar)" marker-end="url(#ar)"/>')
        out.append(f'<text x="{x-4:.1f}" y="{(ys[i]+ys[i+1])/2:.1f}" font-size="9" fill="#c0392b" '
                   f'text-anchor="end" transform="rotate(-90 {x-4:.1f} {(ys[i]+ys[i+1])/2:.1f})">'
                   f'{formato_mm(val)}</text>')
    out.append(f'<line x1="{cx-30:.1f}" y1="{oy:.1f}" x2="{cx-30:.1f}" y2="{oy+cross_h:.1f}" '
               'stroke="#c0392b" stroke-width="0.8" marker-start="url(#ar)" marker-end="url(#ar)"/>')
    out.append(f'<text x="{cx-34:.1f}" y="{oy+cross_h/2:.1f}" font-size="9" fill="#c0392b" '
               f'text-anchor="middle" transform="rotate(-90 {cx-34:.1f} {oy+cross_h/2:.1f})">'
               f'{formato_mm(cross_h)} total</text>')

    # Recuadros A y B fuera de la cruz.
    ax, ay = margin, margin+35
    bx = W-margin-detail_w
    by = margin+35
    out.append(f'<rect x="{ax:.1f}" y="{ay:.1f}" width="{detail_w:.1f}" height="{detail_h:.1f}" rx="5" fill="#fbfbfb" stroke="#aab4aa"/>'
               f'<text x="{ax+12:.1f}" y="{ay+18:.1f}" font-size="11" font-weight="bold">DETALLE A · lengüeta ampliada</text>')
    aw = r.encastre_datos["tab_trasera"]
    chaflan = r.encastre_datos["tab_chaflan"]
    alto_tab = r.encastre_datos["tab_alto"]
    punta = max(0.0, aw-2*chaflan)

    # Vista ampliada proporcional a las medidas reales de la lengüeta.
    escala_detalle = min(7.0, 210.0 / max(aw, alto_tab))
    visual_base = aw*escala_detalle
    visual_punta = punta*escala_detalle
    visual_alto = alto_tab*escala_detalle
    ax1 = ax+(detail_w-visual_base)/2
    ax2 = ax1+visual_base
    ay0 = ay+58
    ay1 = ay0+visual_alto
    px1 = (ax1+ax2-visual_punta)/2
    px2 = px1+visual_punta

    out.append(f'<polygon points="{ax1:.1f},{ay1:.1f} {px1:.1f},{ay0:.1f} '
               f'{px2:.1f},{ay0:.1f} {ax2:.1f},{ay1:.1f}" fill="#f8eed8" stroke="#222" stroke-width="2"/>')

    # Cota superior: punta superior (ancho entre los chaflanes).
    cota_y = ay0-22
    out.append(f'<line x1="{px1:.1f}" y1="{cota_y:.1f}" x2="{px2:.1f}" y2="{cota_y:.1f}" '
               'stroke="#c0392b" stroke-width="0.8" marker-start="url(#ar)" marker-end="url(#ar)"/>'
               f'<text x="{(px1+px2)/2:.1f}" y="{cota_y-7:.1f}" font-size="10" '
               f'text-anchor="middle" fill="#c0392b">{formato_mm(punta)}</text>')

    # Cota izquierda corta para mostrar el chaflán de 3 mm.
    if aw > 2*chaflan:
        linea_chaflan_x1 = ax1
        linea_chaflan_x2 = px1
        linea_chaflan_y = ay0-4
        out.append(f'<line x1="{linea_chaflan_x1:.1f}" y1="{linea_chaflan_y:.1f}" '
                   f'x2="{linea_chaflan_x2:.1f}" y2="{linea_chaflan_y:.1f}" '
                   'stroke="#c0392b" stroke-width="0.8" marker-start="url(#ar)" marker-end="url(#ar)"/>'
                   f'<text x="{(linea_chaflan_x1+linea_chaflan_x2)/2:.1f}" y="{linea_chaflan_y-7:.1f}" '
                   f'font-size="9" text-anchor="middle" fill="#c0392b">{formato_mm(chaflan)}</text>')
        out.append(f'<text x="{ax1-6:.1f}" y="{ay0+visual_alto/2:.1f}" font-size="9" '
                   f'text-anchor="middle" fill="#c0392b">{formato_mm(chaflan)}</text>')

    # Cota inferior: base real de la lengüeta.
    base_y = ay1+24
    out.append(f'<line x1="{ax1:.1f}" y1="{base_y:.1f}" x2="{ax2:.1f}" y2="{base_y:.1f}" '
               'stroke="#c0392b" stroke-width="0.8" marker-start="url(#ar)" marker-end="url(#ar)"/>'
               f'<text x="{(ax1+ax2)/2:.1f}" y="{base_y+15:.1f}" font-size="10" '
               f'text-anchor="middle" fill="#c0392b">{formato_mm(aw)}</text>')

    # Cota vertical y texto de centrado.
    vertical_x = ax2+28
    out.append(f'<line x1="{vertical_x:.1f}" y1="{ay0:.1f}" x2="{vertical_x:.1f}" y2="{ay1:.1f}" '
               'stroke="#c0392b" stroke-width="0.8" marker-start="url(#ar)" marker-end="url(#ar)"/>'
               f'<text x="{vertical_x+8:.1f}" y="{(ay0+ay1)/2:.1f}" font-size="10" '
               f'text-anchor="middle" fill="#c0392b" '
               f'transform="rotate(-90 {vertical_x+8:.1f} {(ay0+ay1)/2:.1f})">{formato_mm(alto_tab)}</text>'
               f'<text x="{(ax1+ax2)/2:.1f}" y="{ay1-visual_alto/2:.1f}" font-size="10" '
               f'text-anchor="middle" fill="#777">centrada</text>')

    out.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{detail_w:.1f}" height="{detail_h:.1f}" rx="5" fill="#fbfbfb" stroke="#aab4aa"/>'
               f'<text x="{bx+12:.1f}" y="{by+18:.1f}" font-size="11" font-weight="bold">DETALLE B · ranura ampliada</text>')
    rf = r.encastre_datos["tab_frontal"]+1
    rl = r.encastre_datos["tab_izquierda"]+1
    bx1 = bx+(detail_w-rf*2)/2
    by1 = by+85
    out.append(f'<line x1="{bx1:.1f}" y1="{by1:.1f}" x2="{bx1+rf*2:.1f}" y2="{by1:.1f}" stroke="#1f6f8b" stroke-width="4"/>'
               f'<text x="{bx1+rf:.1f}" y="{by1-8:.1f}" font-size="9" text-anchor="middle">frontal largo {formato_mm(rf)}</text>'
               f'<line x1="{bx1:.1f}" y1="{by1+28:.1f}" x2="{bx1+rl*2:.1f}" y2="{by1+28:.1f}" stroke="#1f6f8b" stroke-width="4"/>'
               f'<text x="{bx1+rl:.1f}" y="{by1+44:.1f}" font-size="9" text-anchor="middle">lateral largo {formato_mm(rl)} · centrada</text>'
               f'<text x="{bx+12:.1f}" y="{by+145:.1f}" font-size="9">a {formato_mm(r.encastre_datos["off_encastre"])} del pliegue · distancias laterales iguales</text>')

    # Leyenda y datos fuera de la cruz.
    ley_x, ley_y = margin, H-detail_h-margin
    ley = [
        f'<rect x="{ley_x:.1f}" y="{ley_y:.1f}" width="{detail_w:.1f}" height="{detail_h:.1f}" rx="5" fill="#fbfbfb" stroke="#aab4aa"/>',
        f'<text x="{ley_x+12:.1f}" y="{ley_y+19:.1f}" font-size="12" font-weight="bold">LEYENDA Y DATOS</text>',
        f'<line x1="{ley_x+12:.1f}" y1="{ley_y+40:.1f}" x2="{ley_x+55:.1f}" y2="{ley_y+40:.1f}" stroke="#222" stroke-width="2.5"/>',
        f'<text x="{ley_x+62:.1f}" y="{ley_y+44:.1f}" font-size="9">corte</text>',
        f'<line x1="{ley_x+105:.1f}" y1="{ley_y+40:.1f}" x2="{ley_x+148:.1f}" y2="{ley_y+40:.1f}" stroke="#2e7d4f" stroke-width="1.5" stroke-dasharray="7 4"/>',
        f'<text x="{ley_x+155:.1f}" y="{ley_y+44:.1f}" font-size="9">pliegue</text>',
        f'<line x1="{ley_x+205:.1f}" y1="{ley_y+40:.1f}" x2="{ley_x+248:.1f}" y2="{ley_y+40:.1f}" stroke="#1f6f8b" stroke-width="4"/>',
        f'<text x="{ley_x+255:.1f}" y="{ley_y+44:.1f}" font-size="9">ranura</text>',
        f'<text x="{ley_x+12:.1f}" y="{ley_y+52:.1f}" font-size="8">L1-L4 · lengüetas · R1-R4 · ranuras</text>',
        f'<text x="{ley_x+12:.1f}" y="{ley_y+60:.1f}" font-size="9">Medidas en mm, ancho × alto tal como se ven.</text>',
        f'<text x="{ley_x+12:.1f}" y="{ley_y+74:.1f}" font-size="9">Los pliegues coinciden con los bordes de cada panel.</text>',
        f'<text x="{ley_x+12:.1f}" y="{ley_y+94:.1f}" font-size="11" font-weight="bold">DATOS</text>',
    ]
    datos = (
        f'Producto {formato_mm(r.entrada.largo)} × {formato_mm(r.entrada.ancho)} × {formato_mm(r.entrada.alto)}',
        f'Material: {r.entrada.material}',
        f'Flauta {r.flauta} (t = {formato_mm(r.t)} mm)',
        f'Holgura g = {formato_mm(r.g)}',
        f'Panal d = {formato_mm(r.d)}',
        f'Hoja mínima {formato_mm(cross_w)} × {formato_mm(cross_h)}',
    )
    for idx, dato in enumerate(datos):
        ley.append(f'<text x="{ley_x+12:.1f}" y="{ley_y+112+idx*12:.1f}" font-size="9">{dato}</text>')
    out.append("\n".join(ley))

    pan_x, pan_y = W-margin-detail_w, H-detail_h-margin
    out.append(f'<rect x="{pan_x:.1f}" y="{pan_y:.1f}" width="{detail_w:.1f}" height="{detail_h:.1f}" rx="5" fill="#fbfbfb" stroke="#aab4aa"/>'
               f'<text x="{pan_x+12:.1f}" y="{pan_y+18:.1f}" font-size="11" font-weight="bold">PANAL · 8 TIRAS HEXAGONALES</text>')
    tiras = tiras_panal(r)
    tira_tf, tira_lr = tiras
    largo_tf = tira_tf["largo"]
    alto_tf = tira_tf["alto"]
    n_tf = tira_tf["n_tramos"]
    p_tf = tira_tf["tramo"]
    f_tf = tira_tf["tramo_plano"]
    largo_lr = tira_lr["largo"]
    alto_lr = tira_lr["alto"]
    n_lr = tira_lr["n_tramos"]
    p_lr = tira_lr["tramo"]
    f_lr = tira_lr["tramo_plano"]

    perfiles = [
        ("F1", n_tf, f_tf, largo_tf),
        ("F2", n_tf, f_tf, largo_tf),
        ("F3", n_tf, f_tf, largo_tf),
        ("F4", n_tf, f_tf, largo_tf),
        ("S1", n_lr, f_lr, largo_lr),
        ("S2", n_lr, f_lr, largo_lr),
        ("S3", n_lr, f_lr, largo_lr),
        ("S4", n_lr, f_lr, largo_lr),
    ]
    ancho_mini = 118.0
    for indice, (etiqueta, n_tira, tramo_plano, largo_tira) in enumerate(perfiles):
        col = indice % 2
        fila = indice // 2
        x0 = pan_x + 22 + col*142
        y0 = pan_y + 40 + fila*38
        perfil = perfil_tira_panal(n_tira, tramo_plano, r.d)
        x_max = max(x for x, _ in perfil)
        z_scale = 11.0 / r.d
        x_scale = ancho_mini / x_max if x_max > 0 else 1.0

        puntos_a = " ".join(
            f"{x0+x*x_scale:.1f},{y0+24-z*z_scale:.1f}" for x, z in perfil
        )
        puntos_b = " ".join(
            f"{x0+x*x_scale:.1f},{y0+24-(r.d-z)*z_scale:.1f}" for x, z in perfil
        )
        out.append(f'<text x="{x0:.1f}" y="{y0+3:.1f}" font-size="8" font-weight="bold">{etiqueta}</text>')
        out.append(f'<polyline points="{puntos_a}" fill="none" stroke="#b5542a" stroke-width="1.4"/>')
        out.append(f'<polyline points="{puntos_b}" fill="none" stroke="#2a6f97" stroke-width="1.4"/>')
        out.append(f'<rect x="{x0:.1f}" y="{y0+13:.1f}" width="{ancho_mini:.1f}" height="22" '
                   'fill="none" stroke="#c7b99e" stroke-width="0.5"/>')
        for punto_indice, (x, z_a) in enumerate(perfil):
            xx = x0+x*x_scale
            ya = y0+24-z_a*z_scale
            yb = y0+24-(r.d-z_a)*z_scale
            if punto_indice not in (0, len(perfil)-1):
                color = "#2e7d4f" if punto_indice % 2 else "#c55a11"
                estilo = 'stroke-dasharray="5 3"' if punto_indice % 2 else 'stroke-dasharray="8 3 2 3"'
                out.append(f'<line x1="{xx:.1f}" y1="{ya:.1f}" x2="{xx:.1f}" y2="{yb:.1f}" '
                           f'stroke="{color}" stroke-width="1.1" {estilo}/>')
        out.append(f'<text x="{x0+ancho_mini:.1f}" y="{y0+6:.1f}" font-size="7" fill="#c0392b" '
                   f'text-anchor="end">{formato_mm(largo_tira)} × {formato_mm(r.Hs)} × {formato_mm(r.d)}</text>')

    tx = pan_x + 12
    ty = pan_y + 192
    out.append(
        f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="7">'
        f'<tspan x="{tx:.1f}" dy="0">F1-F4: {formato_mm(largo_tf)} × {formato_mm(alto_tf)} mm</tspan>'
        f'<tspan x="{tx+145:.1f}" dy="0">S1-S4: {formato_mm(largo_lr)} × {formato_mm(alto_lr)} mm</tspan>'
        f'<tspan x="{tx:.1f}" dy="10">Perfiles A/B hexagonales · Profundidad d = {formato_mm(r.d)} mm · 8 piezas</tspan>'
        f'</text>'
    )

    scale_x = W-margin-150
    scale_y = ley_y+detail_h-25
    out.append(f'<line x1="{scale_x:.1f}" y1="{scale_y:.1f}" x2="{scale_x+100:.1f}" y2="{scale_y:.1f}" stroke="#222" stroke-width="3"/>'
               f'<text x="{scale_x+50:.1f}" y="{scale_y-6:.1f}" font-size="9" text-anchor="middle">100 mm</text>')
    out.append("</svg>")
    return "\n".join(out)


def a_dict(r: Resultado) -> dict:
    d = asdict(r)
    d["panal"] = tiras_panal(r)
    d["geometria"] = {k: v for k, v in geometria(r).items()}
    return d
