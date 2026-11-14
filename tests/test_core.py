import pytest  # type: ignore[import-not-found]

import nido_core as nc


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
    resultado = nc.calcular(entrada_valida())
    margen = resultado.g + resultado.d + 2 * resultado.t

    assert resultado.Lb == pytest.approx(resultado.entrada.largo + 2 * margen)
    assert resultado.Wb == pytest.approx(resultado.entrada.ancho + 2 * margen)
    assert resultado.Hw == pytest.approx(resultado.entrada.alto + 2 * margen)


def test_ancho_total_es_la_suma_de_las_columnas():
    resultado = nc.calcular(entrada_valida())
    columnas = (
        resultado.Hs
        + resultado.Hw
        + resultado.Lb
        + resultado.Hw
        + resultado.Hs
    )

    assert resultado.ancho_total == pytest.approx(columnas)


def test_valores_calculados_y_geometria_nunca_son_negativos():
    resultado = nc.calcular(entrada_valida())
    geometria = nc.geometria(resultado)
    tiras = nc.tiras_panal(resultado)

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
        *[coordenada for punto in geometria["ranura"] for coordenada in punto],
        *[valor for tira in tiras for valor in (tira["cantidad"], tira["largo"], tira["alto"], tira["profundidad"])],
    ]

    assert all(valor >= 0 for valor in valores)


def test_advierte_si_el_troquel_no_cabe_en_la_hoja():
    resultado = nc.calcular(entrada_valida(largo=1000, ancho=1000, alto=1000))

    assert any("no cabe en la hoja" in advertencia for advertencia in resultado.advertencias)


@pytest.mark.parametrize("campo, valor", [("largo", 9), ("ancho", 1001), ("alto", 0)])
def test_rechaza_dimensiones_fuera_de_rango(campo, valor):
    with pytest.raises(ValueError, match=campo):
        nc.calcular(entrada_valida(**{campo: valor}))
