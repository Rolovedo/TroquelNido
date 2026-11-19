import pytest  # type: ignore[import-not-found]
import re
import html

import nido_core as nc
from config import cargar_configuracion


CONFIG = cargar_configuracion()


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
    assert "escotadura: trasera/frontal 16.5" in texto_svg
    assert "escotadura: laterales 18" in texto_svg


def test_tiras_panal_usan_tramos_enteros_distintos():
    resultado = nc.calcular(entrada_valida(largo=48, ancho=50, alto=80), CONFIG)
    tiras = nc.tiras_panal(resultado)

    for tira in tiras:
        largo = tira["largo"]
        n = max(2, round(largo / tira["profundidad"]))
        assert tira["n_tramos"] == n
        assert tira["tramo"] == pytest.approx(largo / n)

    assert tiras[0]["largo"] != tiras[1]["largo"] or tiras[0]["n_tramos"] != tiras[1]["n_tramos"]


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
