"""NIDO - núcleo paramétrico (sin dependencias externas).

Entrada : tipo de producto, material, largo, ancho, alto (mm), peso opcional.
Salida  : dimensiones del troquel, pasos de trazado con coordenadas, tiras de
          panal y un SVG del troquel (corte continuo, pliegue punteado).

Todos los valores de holgura/espesor son PUNTOS DE PARTIDA: se calibran con la
prueba de caída (Fase 4 del documento) y se editan en config.json.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict

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

    ancho_total = 2 * (Hs + Hw) + Lb
    alto_total = tab_l + 2 * (Hs + Hw) + Wb
    caben = (ancho_total <= HOJA_MAX[0] and alto_total <= HOJA_MAX[1]) or \
            (ancho_total <= HOJA_MAX[1] and alto_total <= HOJA_MAX[0])
    if not caben:
        adv.append(f"El troquel ({ancho_total:.0f}×{alto_total:.0f} mm) no cabe en la hoja "
                   f"{HOJA_MAX[0]:.0f}×{HOJA_MAX[1]:.0f} mm.")
    return Resultado(e, frag, flauta[0], t, g, d, Lb, Wb, Hw, Hs, tab_w, tab_l,
                     slot_off, ancho_total, alto_total, adv)


# ------------------------------------------------------------- geometría ----
def geometria(r: Resultado):
    """Coordenadas en mm. Origen (0,0) = esquina superior izquierda de la hoja
    (incluye la lengüeta). Eje Y hacia abajo."""
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
                ranura=ranura, slot_y=slot_y)


def tiras_panal(r: Resultado):
    """Tiras de cartón en zigzag/celda que van entre la 1ª y la 2ª pared."""
    alto = round(r.Hs, 1)
    return [
        {"cantidad": 2, "largo": round(r.Lb - 2 * r.t, 1), "alto": alto, "profundidad": r.d},
        {"cantidad": 2, "largo": round(r.Wb - 2 * r.t, 1), "alto": alto, "profundidad": r.d},
    ]


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
def svg(r: Resultado, escala: float = 1.0) -> str:
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


def a_dict(r: Resultado) -> dict:
    d = asdict(r)
    d["panal"] = tiras_panal(r)
    d["geometria"] = {k: v for k, v in geometria(r).items()}
    return d
