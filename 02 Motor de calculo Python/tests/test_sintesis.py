"""Pruebas de la planta automática y de la carta en blanco (PAT 136, tarea T22): pat_sim.motor.sintesis, la alimentación genérica
y los equipos de balance simplificado de catalogos/iso_generico.py, y la taxonomía del catálogo (catalogos/taxonomia.py)."""
import json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import sintesis as SI, precedencia as PR, lienzo as LZ, demanda as DM
from pat_sim.catalogos import plantas_genericas as PG, taxonomia as TX
from pat_sim.catalogos.registro import TIPOS, catalogo, planta_desde_dict, nombre_rubro
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor.corrientes import Corriente

ESCENARIOS = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}
NUEVAS = [p for p in PG.IDS_PLANTAS if p not in ESCENARIOS]
_CACHE = {}


def auto(pid, **kw):
    clave = (pid, tuple(sorted(kw.items())))
    if clave not in _CACHE:
        _CACHE[clave] = SI.armar_planta(pid, **kw)
    return _CACHE[clave]


def cierre_relativo(pl):
    cm = max(abs(f["cierre_masa"]) / max(1.0, f["masa_entra"]) for f in pl.cierres())
    ce = max(abs(f["cierre_energia"]) / max(1.0, abs(f["energia_entra"])) for f in pl.cierres())
    return cm, ce


# ------------------------------------------------------------------ armar_planta en las 10 plantas
@pytest.mark.parametrize("pid", list(PG.IDS_PLANTAS))
def test_armar_planta_resuelve_y_cierra_el_balance(pid):
    pl = auto(pid)
    assert pl.resuelta and pl.rubro == PG.PLANTAS[pid]["rubro"]
    cm, ce = cierre_relativo(pl)
    assert cm < 1e-9 and ce < 1e-9
    assert SI.misma_cadena(pl, pid)
    assert SI.producto_final(pl) > 0
    assert PR.violaciones(pl, PR.tabla_plantas()) == []              # la línea respeta la precedencia de estados
    inf = SI.informe(pl)
    assert inf["tipo_planta"] == pid and len(inf["decisiones"]) == len(PG.PLANTAS[pid]["operaciones"])
    json.dumps(pl._p)                                                # el informe se guarda con la versión (JSON)


@pytest.mark.parametrize("pid", list(PG.IDS_PLANTAS))
def test_capacidad_instalada_cubre_el_punto_de_operacion(pid):
    pl = auto(pid)
    for k, eq in pl.equipos.items():
        cap = eq.params["capacidad"].valor if "capacidad" in eq.params else None
        carga = eq.resultado.detalle.get("carga_t_h") if eq.resultado else None
        if cap and carga:
            assert carga <= cap * (1 + 1e-9), k                     # diseño ≥ operación: utilización ≤ 100 %


# ------------------------------------------------------------------ equivalencia con los escenarios
@pytest.mark.parametrize("pid", list(ESCENARIOS))
def test_equivalente_a_su_escenario(pid):
    ref = ESCENARIOS[pid].crear()
    pl = auto(pid, alternativas=False)
    assert sorted(e.tipo for e in pl.equipos.values()) == sorted({e.tipo for e in ref.equipos.values()})
    f, fr = SI._alimentacion(pl), SI._alimentacion(ref)
    rend = SI.producto_final(pl) / f.resultado.detalle["carga_t_h"]
    rend_ref = SI.producto_final(ref) / fr.resultado.detalle["carga_t_h"]
    assert rend == pytest.approx(rend_ref, rel=1e-6)                # mismo modelo físico: mismo rendimiento másico


def test_tomate_con_la_demanda_de_agrozzi_da_la_misma_planta():
    """Con la oferta agrícola del tomate (450.000 t en 76 días) el punto de operación es la alimentación de Agrozzi y el producto es
    el mismo; la capacidad de diseño es el percentil 95 diario × 1,10."""
    pl = auto("tomate", alternativas=False); ref = agrozzi.crear()
    inf = SI.informe(pl)["dimensionamiento"]
    assert inf["materia_prima_operacion_t_h"] == pytest.approx(450000 / (76 * 24), rel=1e-9)
    assert SI.producto_final(pl) == pytest.approx(SI.producto_final(ref), rel=1e-6)
    serie = DM.generar("agricola_tomate")["serie_t_h"]
    assert inf["materia_prima_diseno_t_h"] == pytest.approx(DM.percentil(serie, 95) * 1.10, rel=1e-9)


def test_cifras_de_agrozzi_intactas_despues_de_la_sintesis():
    SI.armar_planta("tomate")
    r = agrozzi.resumen(agrozzi.crear())
    assert r["Qhb"] == pytest.approx(15956.0, abs=0.5)
    assert r["cascada"] == pytest.approx(9073.8, abs=0.5)
    assert r["pinch"] == pytest.approx(9722.9, abs=0.5)


def test_alternativa_elegida_es_la_de_menor_costo():
    inf = SI.informe(auto("pellet"))
    a = inf["alternativas"][0]
    validas = [o for o in a["opciones"] if o["costo_anual_clp"] is not None]
    assert a["elegido"] == min(validas, key=lambda o: o["costo_anual_clp"])["tipo"]
    assert len(a["opciones"]) == 1 + len(PG.PLANTAS["pellet"]["operaciones"][1]["alternativas"])


def test_demanda_de_mercado_se_lleva_a_materia_prima_con_el_rendimiento():
    pl = auto("pellet", alternativas=False)
    d = SI.informe(pl)["dimensionamiento"]
    assert d["de"] == "producto"
    assert SI.producto_final(pl) == pytest.approx(d["operacion_t_h"], rel=1e-6)


# ------------------------------------------------------------------ demanda y dimensionamiento
def test_leer_demanda_y_dimensionar():
    d = SI.leer_demanda(10.0)
    assert d["serie_t_h"] == [10.0]
    x = SI.dimensionar(SI.leer_demanda([1.0, 2.0, 3.0, 4.0]), 7200, "pico", factor_servicio=1.2)
    assert x["diseno_t_h"] == pytest.approx(4.8) and x["operacion_t_h"] == pytest.approx(2.5)
    x = SI.dimensionar(SI.leer_demanda([1.0, 2.0, 3.0, 4.0]), 7200, "media", factor_servicio=1.0)
    assert x["diseno_t_h"] == pytest.approx(2.5)
    m = SI.dimensionar(SI.leer_demanda("mercado_constante"), 7200)
    assert m["razon_horas"] == pytest.approx(8760 / 7200)
    with pytest.raises(ValueError):
        SI.dimensionar(SI.leer_demanda([0.0, 0.0]), 7200)
    with pytest.raises(ValueError):
        SI.leer_demanda(object())


def test_armar_con_el_desafio_de_la_sesion():
    des = dict(titulo="Prueba", demanda_t_h=[0.5, 0.8, 1.2], periodo="mes", unidad="t")
    pl = SI.armar_planta("agar", des, desafio=dict(titulo="Prueba"))
    assert pl.resuelta and pl._p["desafio"]["titulo"] == "Prueba"
    assert SI.informe(pl)["demanda"]["nombre"] == "Prueba"


# ------------------------------------------------------------------ carta en blanco
@pytest.mark.parametrize("pid", ["tomate", "agar", "vino_granel"])
def test_carta_en_blanco_vacia_y_sin_fallas(pid):
    pl = SI.planta_en_blanco(pid)
    assert not pl.equipos and pl.resuelta and SI.es_carta_en_blanco(pl) and SI.tipo_de(pl) == pid
    assert pl.rubro == PG.PLANTAS[pid]["rubro"] and pl._p["demanda_perfil"] == PG.PLANTAS[pid]["demanda_defecto"]
    pl.precedencia = PR.tabla_plantas()
    sol, motivo = LZ.resolver_parcial(pl)
    d = LZ.datos_lienzo(pl, sol, motivo, LZ.catalogo_taxonomia(catalogo))
    assert d["equipos"] == [] and any("vacía" in x["texto"] for x in d["diagnostico"])
    r = LZ.aplicar_evento(pl, dict(evento="agregar", datos=dict(tipo=PG.PLANTAS[pid]["operaciones"][0]["tipo_equipo"])))
    assert r["ok"] and not SI.es_carta_en_blanco(pl)


def test_carta_en_blanco_sin_tipo():
    pl = SI.planta_en_blanco(None)
    assert pl.rubro == "general" and SI.tipo_de(pl) is None and SI.es_carta_en_blanco(pl)


# ------------------------------------------------------------------ registro: alimentación genérica y equipos simplificados
def test_planta_automatica_se_guarda_y_se_carga():
    from pat_sim.datos.bd import planta_a_dict
    pl = auto("harina_pescado")
    q = planta_desde_dict(json.loads(json.dumps(planta_a_dict(pl))))
    q.resolver()
    assert SI.producto_final(q) == pytest.approx(SI.producto_final(pl), rel=1e-9)
    assert {e.tipo for e in q.equipos.values()} >= {"alimentacion_generica", "simple_secador_biomasa"}


def test_equipo_simplificado_retira_agua_y_cierra():
    eq = TIPOS["simple_secador_banda"]("T1"); eq.set("x_salida", 0.80)
    e = Corriente("x", "producto", m=1000.0, s=200.0, T=20.0)
    r = eq.calcular({"entrada": e})
    assert r.salidas["producto"].m == pytest.approx(250.0) and r.salidas["vahos"].m == pytest.approx(750.0)
    assert abs(r.cierre_energia()) < 1e-9 and r.servicios["vapor_kW"] > 0
    eq.set("x_salida", 0.10)                                        # menor que la de entrada: no retira agua y avisa
    r = eq.calcular({"entrada": e})
    assert r.salidas["vahos"].m == 0 and r.avisos
    assert TIPOS["simple_molino_martillos"].simbolo == TIPOS["molino_martillos"].simbolo
    assert all(not c.tipo.startswith("simple_") for r_ in ("tomate", "pellet") for c in catalogo(r_))   # no ensucia los rubros


def test_nombre_rubro_de_los_tipos_nuevos():
    assert nombre_rubro("tomate") == "Pasta de tomate" and nombre_rubro("agar") == "Agar agar" and nombre_rubro("xyz") == "xyz"


# ------------------------------------------------------------------ taxonomía del catálogo
def test_taxonomia_cubre_todos_los_equipos():
    fs = TX.fichas()
    assert len(fs) == len(TIPOS)
    nombres = {k for k, _n, _f in TX.GRUPOS}
    assert all(set(f["funciones"]) <= nombres and 1 <= f["familia"] <= 24 and f["letra"] for f in fs)
    usados = {o["tipo_equipo"] for p in PG.PLANTAS.values() for o in p["operaciones"]}
    en_arbol = {e["tipo"] for g in TX.arbol(fs) for fa in g["familias"] for e in fa["equipos"]}
    assert usados <= en_arbol and len(en_arbol) == len(TIPOS)
    assert all(len(r["equipos"]) >= len(PG.PLANTAS[r["planta_id"]]["operaciones"]) for r in TX.resumen_plantas(fs))


def test_buscador_sin_tildes_y_filtros():
    a = {f["tipo"] for f in TX.buscar("EVAPORACIÓN")}
    b = {f["tipo"] for f in TX.buscar("evaporacion")}
    assert a == b and "evaporador_mvr" in a
    assert {f["tipo"] for f in TX.buscar("secador", planta="agar", simplificados=False)} == {"secador_banda"}
    assert all("secado" in f["funciones"] for f in TX.buscar(funcion="secado"))
    assert all(f["familia"] == 14 for f in TX.buscar(familia=14)) and TX.buscar(familia=14)
    assert TX.buscar("no existe este equipo") == []
    pla = TX.ficha(TIPOS["iso_intercambiador_placas"])
    assert {"tratamiento_termico", "enfriamiento"} <= set(pla["funciones"])   # pasteuriza en una planta y enfría en otra


def test_catalogo_del_lienzo_con_taxonomia():
    cat = LZ.catalogo_taxonomia(catalogo)
    claves = list(cat)
    assert claves[0] == "todos" and claves[-1] == "isa" and len(cat["todos"]["equipos"]) == len(TIPOS)
    assert all(r in cat for r in ("tomate", "agar", "vino_granel"))           # una lista por tipo de planta (clave del rubro)
    assert sum(1 for k in claves if k.startswith("fun_")) >= 12
    tipos = {e["tipo"] for e in cat["todos"]["equipos"]}
    assert all(e["tipo"] in tipos and e["grupo"] for k in claves if k not in ("todos", "isa") for e in cat[k]["equipos"])
    assert all(e["buscar"] == TX.normalizar(e["buscar"]) for e in cat["todos"]["equipos"])
