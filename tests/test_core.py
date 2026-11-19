import pytest  # type: ignore[import-not-found]

import nido_core as nc
from config import cargar_configuracion


CONFIG = cargar_configuracion()


@pytest.mark.parametrize(("valor", "unidad", "esperado"), [(25, "mm", 25), (2.5, "cm", 25)])
def test_convierte_medidas_a_milimetros(valor, unidad, esperado):
    assert nc.convertir_a_mm(valor, unidad) == esperado


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
