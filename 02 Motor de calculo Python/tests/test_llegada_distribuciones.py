"""PAT 139 (14-11-2026): las 10 distribuciones de la llegada de tomate dan series distintas para el mismo modelo y tamaño.
El error que se investigó (el gráfico de Desafío no cambiaba al cambiar la distribución) no estaba en el motor: esta prueba lo deja
fijado para que una regresión en motor/demanda.llegada_tomate (por ejemplo, ignorar dist_id en la ruta modelo y tamaño) se note."""
import pytest
from pat_sim.motor import demanda as DM

MODELOS_TAMANOS = [("agrozzi", "mediana"), ("agrozzi", "chica"), ("cold36_tvr3", "grande")]


@pytest.mark.parametrize("modelo,tamano", MODELOS_TAMANOS)
def test_las_10_distribuciones_dan_series_distintas(modelo, tamano):
    assert len(DM.IDS_DISTRIBUCIONES) == 10
    series, picos, p95s, formas = {}, {}, {}, {}
    for d in DM.IDS_DISTRIBUCIONES:
        r = DM.llegada_tomate(modelo=modelo, tamano=tamano, dist_id=d)
        assert r["distribucion"] == d
        series[d] = tuple(round(x, 6) for x in r["serie_t_h"])
        m = DM.resumen_llegada(r); picos[d] = round(m["pico_t_h"], 3); p95s[d] = round(m["p95_t_h"], 3)
        formas[d] = tuple(round(x, 4) for x in r["extra"]["pesos"])
        assert sum(r["serie"]) == pytest.approx(r["total_t"], rel=1e-9)         # todas reparten el mismo tomate de la temporada
    assert len(set(series.values())) == 10, "dos distribuciones dan exactamente la misma serie"
    assert len(set(formas.values())) == 10, "dos distribuciones dan los mismos pesos (forma)"
    assert len(set(picos.values())) == 10, f"dos distribuciones dan el mismo pico: {picos}"
    assert len(set(p95s.values())) == 10, f"dos distribuciones dan el mismo percentil 95: {p95s}"


def test_la_variante_compuesta_y_el_modelo_dan_la_misma_serie_por_distribucion():
    for d in ("normal", "gamma", "bimodal"):
        a = DM.llegada_tomate(modelo="agrozzi", tamano="mediana", dist_id=d)["serie"]
        b = DM.llegada_tomate("agrozzi|mediana", d)["serie"]
        assert a == b
