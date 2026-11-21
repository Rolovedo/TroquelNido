import pytest  # type: ignore[import-not-found]
import re
import html

import nido_core as nc
from config import cargar_configuracion
from fastapi.testclient import TestClient
from api import app


CONFIG = cargar_configuracion()
CLIENT = TestClient(app)


@pytest.mark.parametrize(("valor", "unidad", "esperado"), [(25, "mm", 25), (2.5, "cm", 25)])
def test_convierte_medidas_a_milimetros(valor, unidad, esperado):
    assert nc.convertir_a_mm(valor, unidad) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(100, "100"), (17.25, "17.25"), (17.2, "17.2"), (17.0, "17")],
)
def test_formato_mm_sin_ceros_sobrantes(valor, esperado):
    assert nc.formato_mm(valor) == esperado


def test_cota_valida_distancia_real_con_escala():
    cota = nc.Cota(valor=25, p1=(0, 0), p2=(50, 0), escala=2)

    nc.validar_cota(cota)
    assert cota.texto_mm() == "25"


def test_cota_rechaza_valor_incorrecto():
    cota = nc.Cota(valor=24, p1=(0, 0), p2=(50, 0), escala=2)

    with pytest.raises(ValueError, match="no coincide"):
        nc.validar_cota(cota)


def test_escotaduras_no_estan_intercambiadas():
    resultado = nc.calcular(
        nc.Entrada("vidrio / cristal", "vidrio", 48, 50, 80, 0.4, "E"),
        CONFIG,
    )

    assert resultado.t == 1.5
    assert resultado.d == 15
    assert resultado.t + resultado.d == 16.5
    assert 2 * resultado.t + resultado.d == 18
    texto_svg = nc.svg(resultado)
    assert "escotadura: trasera/frontal" not in texto_svg
    assert "escotadura: laterales" not in texto_svg


def test_tiras_panal_usan_tramos_enteros_distintos():
    resultado = nc.calcular(entrada_valida(largo=48, ancho=50, alto=80), CONFIG)
    tiras = nc.tiras_panal(resultado)

    for tira in tiras:
        largo = tira["largo"]
        n = tira["n_tramos"]
        assert tira["periodo"] == pytest.approx(largo / n)

    assert tiras[0]["largo"] != tiras[1]["largo"] or tiras[0]["n_tramos"] != tiras[1]["n_tramos"]


def test_paredes_panal_frontales_usan_dimensiones_calculadas():
    resultado = nc.calcular(entrada_valida(largo=48, ancho=50, alto=80), CONFIG)
    paredes = nc.paredes_panal_frontales(resultado)

    assert len(paredes) == 4
    assert {pared["etiqueta"] for pared in paredes} == {"F1", "F2", "F3", "F4"}
    assert all(pared["largo"] == pytest.approx(resultado.Lb - 2 * resultado.t) for pared in paredes)
    assert all(pared["alto"] == pytest.approx(resultado.Hs) for pared in paredes)
    assert all(pared["profundidad"] == resultado.d for pared in paredes)


def test_panal_hexagonal_referencia_120x80x100():
    resultado = nc.calcular(
        nc.Entrada("cerámica / taza", "cerámica", 120, 80, 100, 0.4, "E"),
        CONFIG,
    )
    tiras = nc.tiras_panal(resultado)
    frontal = tiras[0]
    lateral = tiras[1]

    assert resultado.Lb == pytest.approx(172)
    assert resultado.Wb == pytest.approx(132)
    assert resultado.Hw == pytest.approx(152)
    assert resultado.Hs == pytest.approx(149)
    assert resultado.ancho_total == pytest.approx(804)
    assert resultado.alto_total == pytest.approx(764)
    assert frontal["cantidad"] == 4
    assert frontal["n_tramos"] == 7
    assert frontal["periodo"] == pytest.approx(169 / 7, rel=1e-3)
    assert frontal["tramo_plano"] == pytest.approx(169 / 14 - 4.330127, rel=1e-3)
    assert frontal["largo_desarrollado"] == pytest.approx(229.62, rel=1e-2)
    assert lateral["cantidad"] == 4
    assert lateral["n_tramos"] == 4
    assert lateral["periodo"] == pytest.approx(99 / 4, rel=1e-3)
    assert lateral["tramo_plano"] == pytest.approx(99 / 8 - 4.330127, rel=1e-3)
    assert lateral["largo_desarrollado"] == pytest.approx(133.64, rel=1e-2)


def test_perfil_panal_es_simetrico_y_tiene_pliegues():
    perfil = nc.perfil_tira_panal(7, 7.741, 15)

    assert perfil[0] == (0.0, 0.0)
    assert perfil[-1][1] == 0.0
    assert max(z for _, z in perfil) == pytest.approx(7.5)
    assert len(perfil) >= 22


def test_hoja_disponible_personalizada_solo_advierte():
    resultado = nc.calcular(
        nc.Entrada(
            "cerámica / taza",
            "cerámica",
            120,
            80,
            100,
            peso_kg=0.4,
            flauta="E",
            ancho_hoja=700,
            alto_hoja=700,
        ),
        CONFIG,
    )

    assert resultado.ancho_total == pytest.approx(804)
    assert resultado.alto_total == pytest.approx(764)
    assert any("700×700 mm" in advertencia for advertencia in resultado.advertencias)


def test_la_vista_web_muestra_las_advertencias_de_resultado():
    web = open("web/index.html", "r", encoding="utf-8").read()

    assert "resultado.medidas.advertencias" in web
    assert 'status.textContent = `⚠ ${advertencias.join(" ")}`' in web


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 80, 100),
    (48, 50, 80),
    (300, 250, 60),
    (50, 50, 50),
])
def test_salida_principal_sin_texto_de_coordenadas(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    svg = nc.svg(resultado)
    textos = " ".join(html.unescape(fragment)
                      for fragment in re.findall(r">([^<>]+)<", svg))

    assert not re.search(r"\(\s*\d+(?:\.\d*)?\s*,\s*\d+(?:\.\d*)?\s*\)", textos)
    assert not re.search(r"\bX\s*=", textos, re.I)
    assert not re.search(r"\bY\s*=", textos, re.I)
    assert not re.search(r"\borigen\b", textos, re.I)


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 80, 100),
    (48, 50, 80),
    (300, 250, 60),
    (50, 50, 50),
])
def test_paneles_completos_en_salida_svg(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    g = nc.geometria(resultado)
    svg = nc.svg(resultado)

    assert len(g["paneles"]) == 9
    for nombre, p1, p2 in g["paneles"]:
        ancho = abs(p2[0] - p1[0])
        alto = abs(p2[1] - p1[1])
        assert ancho > 0
        assert alto > 0
        assert nombre in svg
        assert nc.formato_mm(ancho) in svg
        assert nc.formato_mm(alto) in svg


def entrada_valida(**cambios):
    valores = {
        "tipo": "libro / papel",
        "material": "papel",
        "largo": 100,
        "ancho": 80,
        "alto": 50,
        "peso_kg": 1,
    }
    valores.update(cambios)
    return nc.Entrada(**valores)


def test_base_es_dimension_mas_dos_margenes():
    resultado = nc.calcular(entrada_valida(), CONFIG)
    margen = resultado.g + resultado.d + 2 * resultado.t

    assert resultado.Lb == pytest.approx(resultado.entrada.largo + 2 * margen)
    assert resultado.Wb == pytest.approx(resultado.entrada.ancho + 2 * margen)
    assert resultado.Hw == pytest.approx(resultado.entrada.alto + 2 * margen)


def test_permite_sobrescribir_holguras_y_flauta():
    resultado = nc.calcular(entrada_valida(g=20, d=25, flauta="B"), CONFIG)

    assert resultado.g == 20
    assert resultado.d == 25
    assert resultado.flauta == "B"
    assert resultado.t == 3


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 80, 100),
    (48, 50, 80),
    (300, 250, 60),
    (50, 50, 50),
])
def test_registro_cotas_coincide_con_geometria(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    g = nc.geometria(resultado)
    cotas = [
        nc.Cota(resultado.Lb, (g["xB0"], g["yB0"]), (g["xB1"], g["yB0"]), nivel=1),
        nc.Cota(resultado.Wb, (g["xB0"], g["yB0"]), (g["xB0"], g["yB1"]), nivel=1),
        nc.Cota(resultado.Hw, (g["xB0"], g["ySw"]), (g["xB0"], g["yB0"]), nivel=2),
        nc.Cota(resultado.Hs, (g["xB0"], g["yT"]), (g["xB0"], g["ySw"]), nivel=2),
    ]

    for cota in cotas:
        nc.validar_cota(cota)

    detalle = nc.Cota(
        valor=resultado.tab_w,
        p1=(g["back_cx"] - resultado.tab_w, g["yT"]),
        p2=(g["back_cx"] + resultado.tab_w, g["yT"]),
        nivel=1,
        escala=2,
    )
    nc.validar_cota(detalle)


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 80, 100),
    (48, 50, 80),
    (300, 250, 60),
    (50, 50, 50),
])
def test_solapa_lateral_contorno_relleno_lengüeta(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    g = nc.geometria(resultado)
    paneles = {nombre: (p1, p2) for nombre, p1, p2 in g["paneles"]}
    largo_solapa = resultado.Wb - 2 * (2 * resultado.t + resultado.d)
    for nombre in ("solapa izquierda", "solapa derecha"):
        p1, p2 = paneles[nombre]
        assert abs(p2[1] - p1[1]) == pytest.approx(largo_solapa)
        assert p1 in g["contorno"] and p2 in g["contorno"]

    for label, poligono, base in g["lengüetas"]:
        xs = [p[0] for p in poligono]
        ys = [p[1] for p in poligono]
        medido = abs(max(xs)-min(xs)) if label in ("L1", "L3") else abs(max(ys)-min(ys))
        assert medido == pytest.approx(base)


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 80, 100),
    (48, 50, 80),
    (300, 250, 60),
    (50, 50, 50),
])
def test_cadenas_completas_incluyen_lengüetas(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    g = nc.geometria(resultado)
    tab = r.encastre_datos["tab_alto"] if (r := resultado).encastre else r.tab_l

    horizontal = [tab, r.Hs, r.Hw, r.Lb, r.Hw, r.Hs, tab]
    vertical = [tab, r.Hs, r.Hw, r.Wb, r.Hw, r.Hs, tab]

    assert sum(horizontal) == pytest.approx(g["cross_w"] if "cross_w" in g else
                                             (max(p[0] for p in g["contorno"]) -
                                              min(p[0] for p in g["contorno"])))
    assert sum(vertical) == pytest.approx(max(p[1] for p in g["contorno"]) -
                                          min(p[1] for p in g["contorno"]))


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 80, 100),
    (48, 50, 80),
    (300, 250, 60),
    (50, 50, 50),
])
def test_circulos_orden_no_se_superponen(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    layout = nc.layout_salida(resultado)
    puntos = []
    for c in layout["circulos"]:
        puntos.append(((c.x1+c.x2)/2, (c.y1+c.y2)/2))

    for i, p1 in enumerate(puntos):
        for p2 in puntos[i+1:]:
            assert nc.distancia_puntos(p1, p2) >= 18


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 80, 100),
    (48, 50, 80),
    (300, 250, 60),
    (50, 50, 50),
])
def test_layout_no_superpone_circulos_textos_y_recuadros(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    layout = nc.layout_salida(resultado)

    circulos = layout["circulos"]
    for i, c1 in enumerate(circulos):
        for c2 in circulos[i+1:]:
            assert not c1.interseca(c2)
        for texto in layout["texto_rects"]:
            assert not c1.interseca(texto)

    recuadros = list(layout["recuadros"].values())
    for i, r1 in enumerate(recuadros):
        for r2 in recuadros[i+1:]:
            assert not r1.interseca(r2)
        for cota in layout["cotas_rects"]:
            assert not r1.interseca(cota)


def test_app_no_generar_png():
    app_text = open("app.py", "r", encoding="utf-8").read()
    assert "cairosvg" not in app_text
    assert "nido_troquel.png" not in app_text
    assert "svg2png" not in app_text


def test_svg_no_muestra_cotas_antiguas():
    resultado = nc.calcular(entrada_valida(largo=120, ancho=80, alto=100), CONFIG)
    svg = nc.svg(resultado)

    assert "764.0" not in svg
    assert "804.0" not in svg
    assert "172.0" not in svg or "L3" not in svg
    assert "DETALLE A · lengüeta ampliada" in svg
    assert "DETALLE B · ranura ampliada" in svg
    assert "LEYENDA Y DATOS" in svg
    assert "DATOS" in svg
    assert "PANAL · 8 TIRAS HEXAGONALES" in svg
    assert "Profundidad d =" in svg
    assert "<circle" not in svg
    assert "ORDEN DE TRAZADO" not in svg
    assert "Medidas en mm, ancho × alto tal como se ven." in svg
    assert "Los pliegues coinciden con los bordes de cada panel." in svg
    assert "Producto 120 × 80 × 100" in svg


def test_detalle_a_muestra_lado_por_lado_de_la_lengüeta():
    resultado = nc.calcular(entrada_valida(largo=48, ancho=50, alto=80), CONFIG)
    svg = nc.svg(resultado)
    datos = resultado.encastre_datos

    punta = datos["tab_trasera"] - 2 * datos["tab_chaflan"]
    assert "DETALLE A · lengüeta ampliada" in svg
    assert f">{nc.formato_mm(punta)}</text>" in svg
    assert f">{nc.formato_mm(datos['tab_trasera'])}</text>" in svg
    assert f">{nc.formato_mm(datos['tab_alto'])}</text>" in svg
    assert f">{nc.formato_mm(datos['tab_chaflan'])}</text>" in svg


def test_detalle_a_muestra_f1_f2_frontal_con_medidas_dinamicas():
    resultado = nc.calcular(entrada_valida(largo=48, ancho=50, alto=80), CONFIG)
    svg = nc.svg(resultado)
    paredes = nc.paredes_panal_frontales(resultado)[:2]

    assert "F1 Frontal A" in svg
    assert "F2 Frontal B" in svg
    for pared in paredes:
        assert f"{nc.formato_mm(pared['largo'])} × {nc.formato_mm(pared['alto'])}" in svg
    assert "corte largo" not in svg


def test_paredes_traseras_f3_f4_se_muestran_a_la_derecha():
    resultado = nc.calcular(entrada_valida(largo=48, ancho=50, alto=80), CONFIG)
    svg = nc.svg(resultado)
    paredes = nc.paredes_panal_frontales(resultado)[2:]

    assert "F3 Trasera A" in svg
    assert "F4 Trasera B" in svg
    for pared in paredes:
        assert f"{nc.formato_mm(pared['largo'])} × {nc.formato_mm(pared['alto'])}" in svg


def test_cuatro_paredes_panal_usan_la_misma_escala_real():
    resultado = nc.calcular(entrada_valida(largo=48, ancho=50, alto=80), CONFIG)
    paredes = nc.paredes_panal_frontales(resultado)
    svg = nc.svg(resultado)
    layout = nc.layout_salida(resultado)

    largo_real = resultado.Lb - 2 * resultado.t
    alto_real = resultado.Hs
    assert all(pared["largo"] == pytest.approx(largo_real) for pared in paredes)
    assert all(pared["alto"] == pytest.approx(alto_real) for pared in paredes)
    assert svg.count('data-escala="1-mm"') == 8
    assert f'data-largo-mm="{nc.formato_mm(largo_real)}"' in svg
    assert f'data-alto-mm="{nc.formato_mm(alto_real)}"' in svg

    pared_x = layout["ox"] - largo_real - 145
    linea_roja_x = layout["ox"] - 55
    assert pared_x + largo_real < linea_roja_x


def test_cuatro_solapas_laterales_se_muestran_en_lados_opuestos():
    resultado = nc.calcular(entrada_valida(largo=48, ancho=50, alto=80), CONFIG)
    svg = nc.svg(resultado)
    ancho_solapa = resultado.encastre_datos["solapa_lateral_l"]

    assert "S1 Izq. A" in svg
    assert "S2 Izq. B" in svg
    assert "S3 Der. A" in svg
    assert "S4 Der. B" in svg
    assert svg.count(f'data-largo-mm="{nc.formato_mm(ancho_solapa)}"') >= 4


def test_ancho_total_es_la_suma_de_las_columnas():
    resultado = nc.calcular(entrada_valida(encastre=False), CONFIG)
    columnas = (
        resultado.Hs
        + resultado.Hw
        + resultado.Lb
        + resultado.Hw
        + resultado.Hs
    )

    assert resultado.ancho_total == pytest.approx(columnas)


def cruce_segmentos(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 95, 100),
    (300, 250, 60),
    (50, 50, 50),
])
def test_encastre_contorno_simple_sin_coordenadas_negativas(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    geometria = nc.geometria(resultado)
    puntos = geometria["contorno"]

    assert all(x >= 0 and y >= 0 for x, y in puntos)
    for i, punto in enumerate(puntos):
        siguiente = puntos[(i + 1) % len(puntos)]
        for j in range(i + 1, len(puntos)):
            otro = puntos[j]
            otro_siguiente = puntos[(j + 1) % len(puntos)]
            if j in (i, i + 1, i - 1):
                continue
            assert not cruce_segmentos(punto, siguiente, otro, otro_siguiente)


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 95, 100),
    (300, 250, 60),
    (50, 50, 50),
])
def test_encastre_lengüetas_tienen_ranuras_en_la_base(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    geometria = nc.geometria(resultado)
    puntos = geometria["contorno"]

    xs = [p[0] for p in puntos]
    ys = [p[1] for p in puntos]
    assert resultado.ancho_total == pytest.approx(max(xs) - min(xs))
    assert resultado.alto_total == pytest.approx(max(ys) - min(ys))
    assert len(geometria["ranuras"]) == 4

    for ranura in geometria["ranuras"]:
        (x1, y1), (x2, y2) = ranura["p1"], ranura["p2"]
        assert ranura["ancho"] >= geometria["tabs"][ranura["lengüeta"]] + 1 - 1e-9
        assert geometria["xB0"] <= min(x1, x2) <= max(x1, x2) <= geometria["xB1"] or \
               geometria["yB0"] <= min(y1, y2) <= max(y1, y2) <= geometria["yB1"]


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 95, 100),
    (300, 250, 60),
    (50, 50, 50),
])
def test_encastre_todas_las_ranuras_cae_en_la_base(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    g = nc.geometria(resultado)

    for ranura in g["ranuras"]:
        (x1, y1), (x2, y2) = ranura["p1"], ranura["p2"]
        assert g["xB0"] <= x1 <= g["xB1"]
        assert g["xB0"] <= x2 <= g["xB1"]
        assert g["yB0"] <= y1 <= g["yB1"]
        assert g["yB0"] <= y2 <= g["yB1"]


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 95, 100),
    (300, 250, 60),
    (50, 50, 50),
])
def test_encastre_simetria_izquierda_derecha(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    g = nc.geometria(resultado)
    eje_x = (g["xB0"] + g["xB1"]) / 2
    reflejado = {(2 * eje_x - x, y) for x, y in g["contorno"]}

    assert reflejado == set(g["contorno"])
    assert g["xParedIzq"] == pytest.approx(2 * eje_x - g["xParedDer"])
    assert g["xSolapaIzq"] == pytest.approx(2 * eje_x - g["xSolapaDer"])
    assert g["left_top"] == pytest.approx(g["right_top"])
    assert g["left_bottom"] == pytest.approx(g["right_bottom"])


@pytest.mark.parametrize(("largo", "ancho", "alto"), [
    (120, 95, 100),
    (300, 250, 60),
    (50, 50, 50),
])
def test_encastre_rellenos_coinciden_con_paneles(largo, ancho, alto):
    resultado = nc.calcular(entrada_valida(largo=largo, ancho=ancho, alto=alto), CONFIG)
    g = nc.geometria(resultado)

    assert len(g["paneles"]) == 9
    nombres = {nombre for nombre, _, _ in g["paneles"]}
    assert {"BASE", "pared izquierda", "pared derecha",
            "solapa izquierda", "solapa derecha"} <= nombres

    for nombre, p1, p2 in g["paneles"]:
        x1, y1 = p1
        x2, y2 = p2
        assert x2 > x1 or y2 > y1
        assert min(x1, x2) >= g["x0"] - 1e-9
        assert max(x1, x2) <= g["xF"] + resultado.encastre_datos["tab_alto"] + 1e-9


def test_valores_calculados_y_geometria_nunca_son_negativos():
    resultado = nc.calcular(entrada_valida(), CONFIG)
    geometria = nc.geometria(resultado)
    tiras = nc.tiras_panal(resultado)
    puntos_ranuras = []
    if resultado.encastre:
        puntos_ranuras = [coordenada for ranura in geometria["ranuras"]
                          for punto in (ranura["p1"], ranura["p2"]) for coordenada in punto]
    else:
        puntos_ranuras = [coordenada for punto in geometria["ranura"] for coordenada in punto]

    valores = [
        resultado.t,
        resultado.g,
        resultado.d,
        resultado.Lb,
        resultado.Wb,
        resultado.Hw,
        resultado.Hs,
        resultado.tab_w,
        resultado.tab_l,
        resultado.slot_off,
        resultado.ancho_total,
        resultado.alto_total,
        *[coordenada for punto in geometria["contorno"] for coordenada in punto],
        *[coordenada for segmento in geometria["pliegues"] for punto in segmento for coordenada in punto],
        *puntos_ranuras,
        *[valor for tira in tiras for valor in (tira["cantidad"], tira["largo"], tira["alto"], tira["profundidad"])],
    ]

    assert all(valor >= 0 for valor in valores)


def test_advierte_si_el_troquel_no_cabe_en_la_hoja():
    resultado = nc.calcular(entrada_valida(largo=1000, ancho=1000, alto=1000), CONFIG)

    assert any("no cabe en la hoja" in advertencia for advertencia in resultado.advertencias)


@pytest.mark.parametrize("campo, valor", [("largo", 9), ("ancho", 1001), ("alto", 0)])
def test_rechaza_dimensiones_fuera_de_rango(campo, valor):
    with pytest.raises(ValueError, match=campo):
        nc.calcular(entrada_valida(**{campo: valor}), CONFIG)


def test_tiras_panal_devuelve_cuatro_largas_y_cuatro_laterales():
    resultado = nc.calcular(entrada_valida(largo=75, ancho=55, alto=90), CONFIG)
    tiras = nc.tiras_panal(resultado)

    assert len(tiras) == 2
    assert tiras[0]["tipo"] == "frontal/trasera"
    assert tiras[1]["tipo"] == "laterales"
    assert tiras[0]["cantidad"] == 4
    assert tiras[1]["cantidad"] == 4
    assert sum(tira["cantidad"] for tira in tiras) == 8


def test_combinacion_cualquiera_produce_exactamente_ocho_tiras():
    resultado = nc.calcular(entrada_valida(largo=63, ancho=47, alto=72), CONFIG)
    tiras = nc.tiras_panal(resultado)

    assert sum(tira["cantidad"] for tira in tiras) == 8
    assert all(tira["largo"] > 0 for tira in tiras)
    assert all(tira["alto"] > 0 for tira in tiras)
    assert all(tira["profundidad"] > 0 for tira in tiras)


def test_dimensiones_panal_cambian_con_largo_ancho_y_alto():
    base = nc.calcular(entrada_valida(largo=50, ancho=40, alto=60), CONFIG)
    largo = nc.calcular(entrada_valida(largo=70, ancho=40, alto=60), CONFIG)
    ancho = nc.calcular(entrada_valida(largo=50, ancho=65, alto=60), CONFIG)
    alto = nc.calcular(entrada_valida(largo=50, ancho=40, alto=85), CONFIG)

    base_tiras = nc.tiras_panal(base)
    largo_tiras = nc.tiras_panal(largo)
    ancho_tiras = nc.tiras_panal(ancho)
    alto_tiras = nc.tiras_panal(alto)

    assert largo_tiras[0]["largo"] != base_tiras[0]["largo"]
    assert ancho_tiras[1]["largo"] != base_tiras[1]["largo"]
    assert alto_tiras[0]["alto"] != base_tiras[0]["alto"]


def test_cuatro_pares_lengüeta_ranura_tienen_ancho_coincidente():
    resultado = nc.calcular(entrada_valida(largo=55, ancho=45, alto=70), CONFIG)
    g = nc.geometria(resultado)

    esperados = {
        "L1": resultado.encastre_datos["tab_trasera"],
        "L2": resultado.encastre_datos["tab_izquierda"],
        "L3": resultado.encastre_datos["tab_frontal"],
        "L4": resultado.encastre_datos["tab_derecha"],
    }
    for ranura in g["ranuras"]:
        assert ranura["lengüeta"] in esperados
        assert ranura["ancho"] == pytest.approx(esperados[ranura["lengüeta"]] + 1)


def test_svg_identifica_encastre_panal_y_leyenda():
    resultado = nc.calcular(entrada_valida(largo=55, ancho=45, alto=70), CONFIG)
    svg = nc.svg(resultado)

    for etiqueta in ("L1", "L2", "L3", "L4", "R1", "R2", "R3", "R4"):
        assert etiqueta in svg
    assert "PANAL · 8 TIRAS HEXAGONALES" in svg
    assert "F1" in svg and "S4" in svg
    assert ">corte</text>" in svg or ">corte<" in svg
    assert ">pliegue</text>" in svg or ">pliegue<" in svg
    assert ">ranura</text>" in svg or ">ranura<" in svg
    assert "Sin pegante" not in svg


def test_svg_no_repite_medidas_fijas_de_120x80x100():
    resultado = nc.calcular(entrada_valida(largo=55, ancho=45, alto=70), CONFIG)
    svg = nc.svg(resultado)

    assert "Producto 55 × 45 × 70" in svg
    assert "Hoja mínima 804 × 764" not in svg
    assert "Hoja mínima 804" not in svg
    assert "172.0" not in svg or "172 × 132 × 152" not in svg


def test_encastre_false_no_modifica_dimensiones_de_base():
    con_encastre = nc.calcular(entrada_valida(largo=55, ancho=45, alto=70), CONFIG)
    sin_encastre = nc.calcular(entrada_valida(largo=55, ancho=45, alto=70, encastre=False), CONFIG)

    assert sin_encastre.Lb == con_encastre.Lb
    assert sin_encastre.Wb == con_encastre.Wb
    assert sin_encastre.Hw == con_encastre.Hw
    assert sin_encastre.Hs == con_encastre.Hs
    assert sin_encastre.encastre is False
    assert nc.geometria(sin_encastre)["ranuras"] == []


def _payload(largo, ancho, alto, encastre=True):
    return {
        "tipo": "cerámica / taza",
        "material": "cerámica",
        "unidad": "mm",
        "largo": largo,
        "ancho": ancho,
        "alto": alto,
        "peso": 0.4,
        "flauta": "E",
        "encastre": encastre,
    }


def test_api_opciones():
    response = CLIENT.get("/opciones")

    assert response.status_code == 200
    assert "tipos" in response.json()
    assert "materiales" in response.json()
    assert "flautas" in response.json()


def test_api_120x80x100_devuelve_diseno_completo():
    response = CLIENT.post("/troquel", json=_payload(120, 80, 100))

    assert response.status_code == 200
    body = response.json()
    assert body["medidas"]["largo_base"] == pytest.approx(172)
    assert body["medidas"]["ancho_base"] == pytest.approx(132)
    assert body["medidas"]["alto_pared"] == pytest.approx(152)
    assert body["medidas"]["alto_solapa"] == pytest.approx(149)
    assert body["medidas"]["encastre"] is True
    assert sum(tira["cantidad"] for tira in body["medidas"]["tiras_panal"]) == 8
    assert body["medidas"]["tapa"]["tab_trasera"] > 0
    assert body["medidas"]["ancho_total"] > 0
    assert body["medidas"]["alto_total"] > 0
    assert isinstance(body["medidas"]["advertencias"], list)
    assert isinstance(body["pasos"], list)
    assert body["svg"].startswith("<svg")


def test_api_48x50x80_devuelve_medidas_distintas():
    grande = CLIENT.post("/troquel", json=_payload(120, 80, 100)).json()
    pequena = CLIENT.post("/troquel", json=_payload(48, 50, 80)).json()

    assert pequena["medidas"]["largo_base"] != grande["medidas"]["largo_base"]
    assert pequena["medidas"]["ancho_total"] != grande["medidas"]["ancho_total"]
    assert pequena["medidas"]["alto_total"] != grande["medidas"]["alto_total"]


def test_api_encastre_false_sigue_siendovalido():
    response = CLIENT.post("/troquel", json=_payload(48, 50, 80, encastre=False))

    assert response.status_code == 200
    body = response.json()
    assert body["medidas"]["encastre"] is False
    assert body["medidas"]["tapa"] is None
    assert sum(tira["cantidad"] for tira in body["medidas"]["tiras_panal"]) == 8
    assert body["svg"].startswith("<svg")


@pytest.mark.parametrize(("campo", "valor"), [
    ("largo", 9),
    ("ancho", 1001),
    ("alto", 0),
])
def test_api_dimensiones_invalidas_devuelven_400(campo, valor):
    payload = _payload(48, 50, 80)
    payload[campo] = valor

    response = CLIENT.post("/troquel", json=payload)

    assert response.status_code == 400


def test_interfaz_web_incluye_encastre_obligatorio_solo_visual():
    web = open("web/index.html", "r", encoding="utf-8").read()

    assert 'id="encastre"' not in web
    assert "Incluye tapa con cierre por lengüetas y ranuras" not in web
    assert "datos.encastre = true" in web
    assert "Pasos de trazado y armado" not in web
    assert 'id="steps"' not in web
    assert "Descargar SVG" in web
    assert "Descargar PNG" in web
    assert "Descargar PDF 1:1" in web
    assert "overflow: auto" in web
