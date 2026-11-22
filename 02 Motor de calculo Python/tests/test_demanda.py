"""Pruebas de motor/demanda.py (PAT 136, tarea T21): oferta agrícola, pronóstico, estrategias de capacidad, plan agregado,
los 10 perfiles y la compatibilidad con el desafío y la temporada."""
import math
import pytest
from pat_sim.motor import demanda as M
from pat_sim.motor import desafio as D

IDS = ["agricola_tomate", "agricola_fruta", "mercado_agar", "mercado_estacional_invierno", "mercado_constante",
       "mercado_tendencia_creciente", "contrato_industrial", "exportacion_ventana", "mercado_impulsos", "mixta_oferta_mercado"]
S12 = [10, -5, 3, 8, -12, 0, 4, -6, 2, -1, 5, -8]                 # índices estacionales aditivos que suman 0
I12 = [1.2, 0.9, 1.0, 1.1, 0.8, 1.0, 1.05, 0.95, 1.0, 0.9, 1.1, 1.0]   # índices multiplicativos que promedian 1


def _aditiva(n=48):
    return [100 + 2 * t + S12[t % 12] for t in range(n)]


def _mult(n=48):
    return [(200 + 3 * t) * I12[t % 12] for t in range(n)]


# ------------------------------------------------------------------ catálogo de perfiles
def test_exactamente_los_10_perfiles():
    assert list(M.PERFILES) == IDS
    lst = M.listar_perfiles()
    assert [p["id"] for p in lst] == IDS
    for p in lst:
        assert p["logica"] in M.LOGICAS and p["nombre"] and p["descripcion"] and p["unidad"]
        for c, par in p["parametros"].items():
            assert str(par["fuente"]).strip(), f"{p['id']}.{c} sin fuente"
            assert "Supuesto" in par["fuente"] or "Derivado" in par["fuente"] or ".pdf" in par["fuente"] or "Tres turnos" in par["fuente"]


def test_logicas_de_los_perfiles():
    log = {k: v["logica"] for k, v in M.PERFILES.items()}
    assert log["agricola_tomate"] == log["agricola_fruta"] == "agricola"
    assert log["mixta_oferta_mercado"] == "mixta"
    assert sum(v == "mercado" for v in log.values()) == 7


@pytest.mark.parametrize("pid", IDS)
def test_perfiles_generan_series_no_negativas(pid):
    r = M.generar(pid)
    assert r["perfil"] == pid and len(r["serie"]) == len(r["etiquetas"]) > 0
    assert all(v >= 0 and math.isfinite(v) for v in r["serie"]) and sum(r["serie"]) > 0
    assert r["periodo"] in D.PERIODOS and r["unidad"] in D.UNIDADES
    assert r["estadisticas"]["total"] == pytest.approx(sum(r["serie"]))
    assert len(r["supuestos"]) == len(M.PERFILES[pid]["parametros"])


@pytest.mark.parametrize("pid", IDS)
def test_determinismo_con_semilla(pid):
    a = M.generar(pid, semilla=7); b = M.generar(pid, semilla=7)
    assert a["serie"] == b["serie"]
    assert M.generar(pid)["serie"] == M.generar(pid, semilla=M.SEMILLA_DEFECTO)["serie"]


def test_semillas_distintas_cambian_la_serie():
    assert M.generar("mercado_agar", semilla=1)["serie"] != M.generar("mercado_agar", semilla=2)["serie"]


def test_parametros_desconocidos_o_negativos_fallan():
    with pytest.raises(ValueError):
        M.generar("mercado_agar", dict(no_existe=1))
    with pytest.raises(ValueError):
        M.generar("mercado_agar", dict(cv=-1))
    with pytest.raises(ValueError):
        M.generar("agricola_tomate", dict(curva="cuadrada"))
    with pytest.raises(ValueError):
        M.generar("no_es_perfil")


# ------------------------------------------------------------------ (a) oferta agrícola
@pytest.mark.parametrize("cap", [None, 300.0, 416.7, 150.0])
def test_cierre_de_masa_oferta_agricola(cap):
    r = M.oferta_agricola(5000, 90, 76, 24, "normal", 0.5, 0.25, 0.1, cap, 6.0, 0.05 / 8, 48.0, semilla=3)
    b = r["balance"]
    assert b["cosechado"] == pytest.approx(450000.0)
    assert b["procesado"] + b["perdido"] == pytest.approx(b["cosechado"], rel=1e-9)
    assert sum(r["serie"]) == pytest.approx(b["cosechado"])
    assert sum(r["procesado"]) + sum(r["perdido"]) == pytest.approx(b["cosechado"], rel=1e-9)


def test_sin_capacidad_no_hay_perdida_y_capacidad_baja_pierde():
    sin = M.oferta_agricola(1000, 50, 30, 24, capacidad_t_h=None)["balance"]
    assert sin["perdido"] == pytest.approx(0.0) and sin["procesado"] == pytest.approx(50000.0)
    bajo = M.oferta_agricola(1000, 50, 30, 24, capacidad_t_h=40.0, perecibilidad_h=24.0)["balance"]
    alto = M.oferta_agricola(1000, 50, 30, 24, capacidad_t_h=80.0, perecibilidad_h=24.0)["balance"]
    assert bajo["perdido"] > alto["perdido"] >= 0


def test_perecibilidad_mayor_reduce_la_perdida():
    kw = dict(superficie_ha=1000, rendimiento_t_ha=50, dias=30, capacidad_t_h=60.0, tasa_perdida_h=0.0)
    corta = M.oferta_agricola(perecibilidad_h=0.0, **kw)["balance"]["perdido"]
    larga = M.oferta_agricola(perecibilidad_h=96.0, **kw)["balance"]["perdido"]
    assert corta > larga


def test_capacidad_para_perdida_cumple_el_objetivo():
    kw = dict(superficie_ha=5000, rendimiento_t_ha=90, dias=76, horas_dia=24, cv=0.1, umbral_h=6.0, tasa_perdida_h=0.05 / 8,
              perecibilidad_h=48.0, semilla=1)
    k = M.capacidad_para_perdida(0.01, **kw)
    assert M.oferta_agricola(capacidad_t_h=k, **kw)["balance"]["fraccion_perdida"] <= 0.01 + 1e-9
    assert M.oferta_agricola(capacidad_t_h=0.9 * k, **kw)["balance"]["fraccion_perdida"] > 0.01
    r = M.oferta_agricola(**kw)["capacidad"]
    assert r["media_t_h"] <= r["percentil_t_h"] <= r["pico_t_h"]


def test_serie_semanal_suma_lo_mismo_que_la_diaria():
    d = M.oferta_agricola(1000, 50, 30, 20, periodo="día", cv=0.2, semilla=5)
    s = M.oferta_agricola(1000, 50, 30, 20, periodo="semana", dias_semana=6, cv=0.2, semilla=5)
    assert len(s["serie"]) == 5 and sum(s["serie"]) == pytest.approx(sum(d["serie"]))
    assert s["serie_t_h"][0] == pytest.approx(s["serie"][0] / (6 * 20))


def test_tomate_por_defecto_cuadra_con_agrozzi():
    r = M.generar("agricola_tomate")
    assert r["estadisticas"]["total"] == pytest.approx(450000.0)
    cap = r["extra"]["capacidad"]
    assert cap["media_t_h"] == pytest.approx(450000.0 / (76 * 24))
    assert cap["para_perdida_1pct_t_h"] <= 416.7          # la recepción de 10.000 t/d alcanza para perder menos de 1 %


def test_compatible_con_temporada_curva_llegada():
    from pat_sim.escenarios import agrozzi
    from pat_sim.motor import temporada as TM
    pl = agrozzi.crear()
    kw = M.desde_planta(pl)
    r = M.oferta_agricola(**kw)
    ref = TM.curva_llegada(pl)
    assert len(r["serie"]) == len(ref)
    assert max(abs(a - b) for a, b in zip(r["serie"], ref)) < 1e-6


@pytest.mark.parametrize("rubro", ["pellet", "chip", "lena"])
def test_desde_planta_en_biomasa_es_pareja(rubro):
    import importlib
    from pat_sim.motor import temporada as TM
    pl = importlib.import_module(f"pat_sim.escenarios.{rubro}").crear()
    r = M.oferta_agricola(**M.desde_planta(pl))
    assert r["serie"] == pytest.approx(TM.curva_llegada(pl))


# ------------------------------------------------------------------ (b) pronóstico
def test_holt_winters_aditivo_recupera_estacionalidad():
    y = _aditiva()
    r = M.holt_winters(y, 12, 0.3, 0.1, 0.2, "aditivo", 12)
    assert r["estacional"] == pytest.approx([float(v) for v in S12], abs=1e-9)
    assert r["tendencia"] == pytest.approx(2.0)
    assert r["pronostico"] == pytest.approx([100 + 2 * t + S12[t % 12] for t in range(48, 60)])


def test_holt_winters_multiplicativo_recupera_estacionalidad():
    # sin tendencia la recuperación es exacta; con tendencia la media móvil del arranque deja un sesgo de 0,1 % (esperado)
    r = M.holt_winters([200 * I12[t % 12] for t in range(48)], 12, 0.4, 0.1, 0.3, "multiplicativo", 6)
    assert r["estacional"] == pytest.approx(I12, rel=1e-9)
    assert r["pronostico"] == pytest.approx([200 * I12[t % 12] for t in range(48, 54)], rel=1e-9)
    r = M.holt_winters(_mult(), 12, 0.4, 0.1, 0.3, "multiplicativo", 6)
    assert r["estacional"] == pytest.approx(I12, abs=0.005)
    assert r["pronostico"] == pytest.approx([(200 + 3 * t) * I12[t % 12] for t in range(48, 54)], rel=0.01)


def test_holt_winters_con_ruido_se_acerca_a_la_estacionalidad():
    import random
    g = random.Random(4)
    y = [v + g.gauss(0, 1.0) for v in _aditiva(72)]
    r = M.optimizar_hw(y, 12, "aditivo")
    assert max(abs(a - b) for a, b in zip(r["estacional"], S12)) < 3.0


def test_descomposicion_clasica_recupera_indices_y_tendencia():
    dc = M.descomposicion_clasica(_mult(), 12, "multiplicativo")
    assert dc["estacional"] == pytest.approx(I12, abs=0.005)
    assert (dc["a"], dc["b"]) == pytest.approx((200.0, 3.0), rel=0.005)
    da = M.descomposicion_clasica(_aditiva(), 12, "aditivo")       # aditiva con tendencia lineal: exacta
    assert da["estacional"] == pytest.approx([float(v) for v in S12], abs=1e-9) and (da["a"], da["b"]) == pytest.approx((100.0, 2.0))
    with pytest.raises(ValueError):
        M.descomposicion_clasica(_mult(20), 12)


def test_regresion_con_tendencia():
    a, b = M.regresion_lineal([5 + 3 * t for t in range(10)])
    assert (a, b) == pytest.approx((5.0, 3.0))
    r = M.pronostico_regresion([5 + 3 * t for t in range(10)], 2)
    assert r["pronostico"] == pytest.approx([35.0, 38.0])


def test_errores_pronostico_perfecto_es_cero():
    y = [10.0, 20.0, 30.0, 25.0]
    e = M.errores(y, y)
    assert e["mad"] == 0 and e["mape"] == 0 and e["mse"] == 0 and e["sesgo"] == 0 and not e["fuera_de_control"]


def test_errores_mad_mape_y_senal_de_rastreo():
    e = M.errores([100, 100, 100, 100], [90, 90, 90, 90])
    assert e["mad"] == pytest.approx(10.0) and e["mape"] == pytest.approx(10.0) and e["sesgo"] == pytest.approx(10.0)
    assert e["senal"] == pytest.approx([1.0, 2.0, 3.0, 4.0]) and not e["fuera_de_control"]
    assert M.errores([100] * 5, [90] * 5)["fuera_de_control"]          # sesgo sostenido: la señal pasa de 4
    with pytest.raises(ValueError):
        M.errores([1, 2], [1])


def test_evaluar_metodos_ordena_por_mad_y_hw_gana_en_serie_estacional():
    ev = M.evaluar_metodos(_aditiva(60), 12, 12)
    assert [x["errores"]["mad"] for x in ev] == sorted(x["errores"]["mad"] for x in ev)
    assert ev[0]["clave"] in ("hw_aditivo", "hw_multiplicativo", "descomposicion")
    assert ev[0]["errores"]["mape"] < 1.0


def test_croston_en_demanda_intermitente():
    y = [0, 0, 10, 0, 0, 10, 0, 0, 10, 0, 0, 10]
    r = M.croston(y, 0.1, 4)
    assert r["pronostico"] == pytest.approx([10.0 / 3.0] * 4, rel=1e-6)


# ------------------------------------------------------------------ (b) capacidad y plan agregado
def test_estrategias_de_capacidad_crecimiento():
    d = [100 + 10 * t for t in range(12)]
    r = M.estrategias_capacidad(d, capacidad_inicial=100, bloque=25, costo_capacidad=1.0, costo_expansion=50.0, margen=5.0)
    E = r["estrategias"]
    assert E["adelantarse"]["faltante_total"] == pytest.approx(0.0)              # adelantarse nunca deja demanda sin atender
    assert all(c <= max(d[:t]) + 1e-9 for t, c in enumerate(E["rezagarse"]["capacidad"]) if t > 0)
    assert E["rezagarse"]["faltante_total"] >= E["seguir"]["faltante_total"] >= E["adelantarse"]["faltante_total"]
    assert E["adelantarse"]["ocioso_total"] >= E["seguir"]["ocioso_total"] >= E["rezagarse"]["ocioso_total"]
    for k, x in E.items():
        assert all(b >= a for a, b in zip(x["capacidad"], x["capacidad"][1:]))     # la capacidad no baja
        assert all(abs((c - 100) / 25 - round((c - 100) / 25)) < 1e-9 for c in x["capacidad"])   # en bloques
        assert x["costo_total"] == pytest.approx(x["costo_capacidad"] + x["costo_expansion"] + x["costo_faltante"])


def test_plan_agregado_nivelacion_contra_persecucion():
    d = [50, 80, 120, 150, 120, 80]
    r = M.plan_agregado(d, 0.0, costo_mantener=2.0, costo_cambio=5.0, costo_faltante=100.0)
    N, P = r["planes"]["nivelacion"], r["planes"]["persecucion"]
    assert N["faltante_total"] == pytest.approx(0.0) and P["faltante_total"] == pytest.approx(0.0)
    assert min(N["inventario"]) >= -1e-9 and len(set(round(x, 9) for x in N["produccion"])) == 1
    assert P["inventario"] == pytest.approx([0.0] * 6) and P["costo_mantener"] == 0
    assert N["cambios"] == pytest.approx(0.0) and P["cambios"] == pytest.approx(100 + 70)   # sube 100 y baja 70
    assert sum(N["produccion"]) - sum(d) == pytest.approx(N["inventario"][-1])
    assert r["mejor"] in ("nivelacion", "persecucion")
    caro = M.plan_agregado(d, 0.0, costo_mantener=100.0, costo_cambio=0.1)
    assert caro["mejor"] == "persecucion"
    barato = M.plan_agregado(d, 0.0, costo_mantener=0.01, costo_cambio=100.0)
    assert barato["mejor"] == "nivelacion"


def test_plan_agregado_con_capacidad_maxima_deja_faltante():
    r = M.plan_agregado([100, 200, 100], capacidad_max=120.0, costo_faltante=10.0)
    P = r["planes"]["persecucion"]
    assert P["faltante_total"] == pytest.approx(80.0) and P["costo_faltante"] == pytest.approx(800.0)


def test_mixta_cubre_el_mercado_con_inventario():
    r = M.generar("mixta_oferta_mercado")
    x = r["extra"]
    assert sum(r["serie"]) == pytest.approx(sum(x["demanda_mercado"]) - x["venta_no_cubierta_t"])
    assert min(x["inventario"]) >= -1e-9
    assert x["materia_prima_usada_t"] + x["materia_prima_sobrante_t"] == pytest.approx(x["oferta_materia_prima_t"])
    assert sum(1 for v in r["serie"] if v > 0) == 4                    # solo los meses de cosecha


# ------------------------------------------------------------------ compatibilidad con el desafío
@pytest.mark.parametrize("pid", IDS)
def test_compatible_con_desafio_serie_demanda(pid):
    r = M.generar(pid)
    d = M.a_desafio(r)
    assert D.validar(d) == []
    assert D.serie_demanda(d) == pytest.approx(r["serie"])
    assert D.estadisticas(d)["total"] == pytest.approx(r["estadisticas"]["total"])
    th = D.demanda_t_h(d)
    assert th[0] == pytest.approx(r["serie"][0] / D.PERIODOS[r["periodo"]])


def test_pronostico_al_desafio_y_estado_de_sesion():
    r = M.generar("mercado_agar")
    d = M.a_desafio(r, usar="pronostico")
    assert D.validar(d) == [] and len(D.serie_demanda(d)) == 12
    actual = D.estado_sesion(M.a_desafio(M.generar("mercado_constante"), titulo="Mi desafío", rubro="pellet",
                                         precios=[dict(producto="X", precio=5.0, moneda="US$", unidad="kg", fuente="Supuesto")]), "Ana", "doña")
    nuevo = M.estado_desafio(r, actual, usar="pronostico")
    assert nuevo["titulo"] == "Mi desafío" and nuevo["rubro"] == "pellet" and nuevo["nombre"] == "Ana" and len(nuevo["precios"]) == 1
    assert nuevo["demanda"] == pytest.approx(r["extra"]["pronostico"]) and nuevo["perfil_demanda"] == "mercado_agar"
    assert actual["demanda"] != nuevo["demanda"]                          # no modifica el diccionario recibido
    solo = M.estado_desafio(M.generar("agricola_tomate"))
    assert solo["periodo"] == "día" and len(solo["demanda"]) == 76 and solo["demanda_t_h"] is not None
    with pytest.raises(ValueError):
        M.a_desafio(M.generar("agricola_tomate"), usar="pronostico")


def test_percentil_y_estadisticas():
    assert M.percentil([1, 2, 3, 4, 5], 50) == 3 and M.percentil([1, 2, 3, 4], 95) == pytest.approx(3.85)
    e = M.estadisticas([2.0, 4.0, 6.0])
    assert (e["total"], e["media"], e["maximo"], e["i_max"]) == (12.0, 4.0, 6.0, 2)
    assert M.estadisticas([])["n"] == 0
