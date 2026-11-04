"""PAT 133, mejora 21: lectura y escritura de números en formato chileno."""
import pytest
from pat_sim.motor import formato as F


@pytest.mark.parametrize("t,v", [("1.234,5", 1234.5), ("1234,5", 1234.5), ("1234.5", 1234.5), ("1.234", 1234.0),
                                 ("1.234.567", 1234567.0), ("-0,25", -0.25), ("0.5", 0.5), (" 2,77 ", 2.77), ("$1.000", 1000.0)])
def test_leer(t, v):
    assert F.leer(t) == pytest.approx(v)


def test_leer_rechaza_texto():
    with pytest.raises(ValueError):
        F.leer("abc")
    with pytest.raises(ValueError):
        F.leer("")


def test_escribir_y_decimales():
    assert F.escribir(1234.5, 1) == "1.234,5"
    assert F.leer(F.escribir(98765.4321, 3)) == pytest.approx(98765.432)
    assert F.decimales("%.3f", 1.0, False) == 3 and F.decimales(None, 0.25, False) == 2 and F.decimales(None, 1, True) == 0


def test_decimales_del_valor_no_redondean():
    assert F.decimales_valor(2.77) == 2 and F.decimales_valor(5355.1) == 1 and F.decimales_valor(20) == 0
    assert F.leer(F.escribir(2.77, max(F.decimales(None, 0.1, False), F.decimales_valor(2.77)))) == pytest.approx(2.77)
