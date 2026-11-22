"""PAT 144 a (20-11-2026): desafío de agar agar en la pantalla Desafío (motor).

Comprueba el catálogo catalogos/plantas_agar.py (10 modelos de proceso × 3 tamaños, cada valor con fuente), que «base|mediana» es
exactamente el escenario base del agar, la llegada de alga seca de motor/demanda.llegada_agar con las 10 distribuciones, el desafío
de la sesión (desafio_agar), la planta ideal y la planta en blanco de motor/sintesis.py con el agar, la familia «agar» del docente
(datos/genericos.py) y que el tomate y el agar genérico siguen como antes.
"""
import pytest
from pat_sim.catalogos import plantas_agar as PA
from pat_sim.escenarios import agar as EA
from pat_sim.motor import demanda as DM, desafio as D, sintesis as SI
from pat_sim.datos import genericos as GE
from pat_sim.datos.bd import BaseDatos

TIPOS_ESCENARIO = ["alimentacion_alga", "lavado_alga", "tratamiento_alcalino_agar", "lavado_neutralizacion_agar", "extractor_agar",
                   "filtro_prensa_agar", "gelificador_agar", "prensa_gel_agar", "secador_agar", "molino_agar", "envasado_agar", "caldera_gas"]


# ---------------------------------------------------------------- catálogo
def test_diez_modelos_tres_tamanos_y_cada_valor_con_fuente():
    assert len(PA.IDS_MODELOS) == 10 and len(PA.IDS_TAMANOS) == 3 and len(PA.combinaciones()) == 30
    for m in PA.IDS_MODELOS:
        f = PA.fuentes_modelo(m)
        for k in PA.ETIQUETAS:
            assert f[k] and ("McHugh" in f[k] or "Armisen" in f[k] or "Belattmania" in f[k] or "Correa" in f[k]), (m, k)
        assert ("combinacion" in f) == (len(PA.MODELOS[m]["cambios"]) > 1)
    for t in PA.IDS_TAMANOS:
        f = PA.fuentes_tamano(t)
        assert set(f) == {"agar_t_ano", "dias", "horas_dia"} and all(f.values())
    assert [PA.TAMANOS[t]["agar_t_ano"] for t in PA.IDS_TAMANOS] == [200.0, 602.0, 1200.0]


def test_un_valor_sin_fuente_no_se_acepta():
    with pytest.raises(KeyError):
        PA._m("x", "x", "x", naoh=0.03)


def test_base_mediana_es_exactamente_el_escenario_base():
    a, b = EA.crear(), PA.crear_escenario("base|mediana")
    assert b.nombre == a.nombre == EA.NOMBRE
    ra, rb = EA.resumen_corto(a), EA.resumen_corto(b)
    assert ra == rb
    assert rb["calor_proceso_kW"] == pytest.approx(1733.8, abs=0.05) and rb["recuperable_todas_kW"] == pytest.approx(867.0, abs=0.05)
    kw = PA.kw_escenario(None)
    assert all(kw[k] == EA.BASE[k] for k in kw)
    assert PA.es_base("base") and PA.es_base("base|mediana") and not PA.es_base("base|chica")


@pytest.mark.parametrize("vid", PA.combinaciones())
def test_las_30_plantas_resuelven_sin_avisos_y_producen_el_agar_del_tamano(vid):
    pl = PA.crear_escenario(vid)
    v = PA.variante(vid)
    assert pl.resuelta and not pl.avisos, pl.avisos
    r = EA.resumen_corto(pl)
    assert r["producto_t_h"] * v["dias"] * v["horas_dia"] == pytest.approx(v["agar_t_ano"], rel=1e-6)
    assert r["alga_t_h"] * v["dias"] * v["horas_dia"] == pytest.approx(v["alga_t_ano"], rel=1e-6)
    assert r["humedad_producto"] < 0.18                       # especificación de Armisen y Galatas (1987)


def test_los_modelos_cambian_lo_que_dicen():
    q = {m: EA.resumen_corto(PA.crear_escenario(m))["calor_proceso_kW"] for m in PA.IDS_MODELOS}
    assert q["extraccion_100"] > q["base"] and q["extracto_diluido"] > q["base"] and q["extracto_concentrado"] < q["base"]
    assert q["prensado_intenso"] < q["base"] and q["intensivo"] == max(q.values()) and q["eficiente"] == min(q.values())
    assert PA.variante("alga_gracilis")["alga_t_ano"] > PA.variante("base")["alga_t_ano"]      # menor rendimiento, más alga
    pl = PA.crear_escenario("alcali_suave")
    c1 = next(e for e in pl.equipos.values() if e.tipo == "tratamiento_alcalino_agar")
    assert c1.v("conc_naoh") == 0.02 and "límite inferior" in c1.params["conc_naoh"].fuente


def test_ids_invalidas():
    for x in ("no_existe", "base|enorme", "agrozzi|mediana"):
        assert not PA.es_variante(x)
        with pytest.raises(KeyError):
            PA.variante(x)


# ---------------------------------------------------------------- llegada de alga seca
@pytest.mark.parametrize("dist", DM.IDS_DISTRIBUCIONES)
def test_llegada_agar_suma_el_alga_del_ano_en_los_dias_de_operacion(dist):
    r = DM.llegada_agar(modelo="intensivo", tamano="chica", dist_id=dist)
    v = PA.variante("intensivo|chica")
    assert r["perfil"] == DM.PERFIL_AGAR and r["rubro"] == "agar" and r["logica"] == "agricola" and r["periodo"] == "día"
    assert len(r["serie"]) == len(r["serie_t_h"]) == v["dias"] == 330
    assert sum(r["serie"]) == pytest.approx(v["alga_t_ano"], rel=1e-9)
    assert r["serie_t_h"][0] == pytest.approx(r["serie"][0] / 16.0)
    assert r["extra"]["balance"]["perdido"] == pytest.approx(0.0, abs=1e-9)        # el alga seca no se pierde por esperar
    textos = " ".join([r["nombre"], r["descripcion"]] + [str(s["nombre"]) + " " + str(s["valor"]) + " " + s["unidad"] for s in r["supuestos"]])
    assert "tomate" not in textos and "peak" not in textos and "variedad" not in textos and "MM" not in textos


def test_llegada_agar_por_omision_es_uniforme_y_reproducible():
    a, b = DM.llegada_agar(), DM.llegada_agar()
    assert a["distribucion"] == "uniforme" and a["variante"] == "base|mediana" and a["serie"] == b["serie"]
    assert DM.llegada_agar(semilla=5)["serie"] != a["serie"]
    m = DM.resumen_llegada(a)
    assert m["media_t_h"] * 1000 == pytest.approx(376.17, abs=0.05)               # 76,0 kg/h de agar del escenario base
    assert DM.llegada("agar")["serie"] == a["serie"] and DM.llegada("tomate")["perfil"] == DM.PERFIL_TOMATE
    with pytest.raises(ValueError):
        DM.llegada("pellet")
    with pytest.raises(ValueError):
        DM.llegada_agar(dist_id="no_existe")


def test_desafio_agar_valido_y_sin_claves_del_tomate():
    r = DM.llegada_agar(modelo="prensado_intenso", tamano="grande", dist_id="bimodal")
    d = DM.desafio_agar(r, "Ana Pérez")
    assert d["tipo_planta"] == d["rubro"] == "agar" and d["variante_agar"] == "prensado_intenso|grande"
    assert (d["modelo_agar"], d["tamano_agar"], d["distribucion_agar"]) == ("prensado_intenso", "grande", "bimodal")
    assert not any(k.endswith("_tomate") for k in d)
    assert d["demanda_t_h"] == r["serie_t_h"] and sum(d["demanda"]) == pytest.approx(r["total_t"])
    assert not D.validar(dict(d, demanda=dict(periodo=d["periodo"], unidad=d["unidad"], valores=d["demanda"], fuente="x")))
    assert "dos épocas de entrega" in d["titulo"] and DM.desafio_de_llegada(r)["tipo_planta"] == "agar"
    assert SI.agar_de_desafio(d) == ("prensado_intenso|grande", "bimodal")
    assert SI.agar_de_desafio(DM.desafio_tomate(DM.llegada_tomate())) is None and SI.agar_de_desafio(None) is None


# ---------------------------------------------------------------- planta ideal y planta en blanco
def test_planta_ideal_del_agar_usa_los_equipos_del_escenario():
    r = DM.llegada_agar()
    d = DM.desafio_agar(r)
    pl = SI.armar_planta("agar", r, desafio=d)
    assert [e.tipo for e in pl.equipos.values()] == TIPOS_ESCENARIO
    assert pl.rubro == "agar" and pl.resuelta and not pl.avisos, pl.avisos
    inf = SI.informe(pl)
    assert inf["variante_agar"] == "base|mediana" and inf["distribucion_agar"] == "uniforme"
    assert inf["variante_tomate"] is None and inf["distribucion_tomate"] is None and not inf["violaciones"]
    assert all(s["clave"] != "simple" for s in inf["supuestos"])                        # no es el balance simplificado
    assert pl._p["variante_agar"] == "base|mediana" and pl._p["desafio"] is d and "variante_tomate" not in pl._p
    assert SI.misma_cadena(pl, "agar") and SI.tipo_de(pl) == "agar" and SI.variante_agar_de(pl) == "base|mediana"
    assert "modelo base" in pl.nombre
    # en el punto de operación (media de la llegada uniforme) la planta pide el mismo calor que el escenario base
    from pat_sim.motor.resumen import resumen_planta
    a, b = resumen_planta(pl), resumen_planta(EA.crear())
    assert float(a["servicios"]["vapor_kW"]) == pytest.approx(float(b["servicios"]["vapor_kW"]), rel=1e-6)
    assert a["sumidero"]["equipo"] == "C1" and a["cascada"] == pytest.approx(b["cascada"], rel=1e-6)


def test_planta_ideal_del_agar_crece_con_el_tamano_y_toma_la_variante_sin_demanda():
    cap = {}
    for t in PA.IDS_TAMANOS:
        pl = SI.armar_planta("agar", DM.llegada_agar(modelo="eficiente", tamano=t, dist_id="normal"))
        cap[t] = SI.informe(pl)["dimensionamiento"]["materia_prima_diseno_t_h"]
        assert not pl.avisos and SI.informe(pl)["variante_agar"] == f"eficiente|{t}"
    assert 0 < cap["chica"] < cap["mediana"] < cap["grande"]
    pl = SI.armar_planta("agar", variante="extraccion_100|chica")                   # sin demanda: la llegada uniforme de la variante
    inf = SI.informe(pl)
    assert inf["variante_agar"] == "extraccion_100|chica" and inf["distribucion_agar"] == "uniforme"
    w1 = next(e for e in pl.equipos.values() if e.tipo == "extractor_agar")
    assert w1.v("T_extraccion") == 100.0


@pytest.mark.parametrize("dist", DM.IDS_DISTRIBUCIONES)
def test_planta_ideal_del_agar_con_las_10_distribuciones(dist):
    pl = SI.armar_planta("agar", DM.llegada_agar(dist_id=dist))
    assert len(pl.equipos) == 12 and not pl.avisos, pl.avisos


def test_el_agar_sin_variante_sigue_con_los_tipos_genericos():
    pl = SI.armar_planta("agar")
    tipos = [e.tipo for e in pl.equipos.values()]
    assert tipos[0] == "alimentacion_generica" and "extractor_agar" not in tipos
    inf = SI.informe(pl)
    assert inf.get("variante_agar") is None and any(s["clave"] == "simple" for s in inf["supuestos"])


def test_planta_en_blanco_del_agar():
    r = DM.llegada_agar(modelo="alga_gracilis", tamano="chica", dist_id="gamma")
    d = DM.desafio_agar(r)
    for pl in (SI.planta_en_blanco("agar", r, d), SI.planta_en_blanco("agar", "mercado_agar", d), SI.planta_en_blanco("agar", d, d)):
        assert not pl.equipos and pl.rubro == "agar" and SI.es_carta_en_blanco(pl)
        assert pl._p["variante_agar"] == "alga_gracilis|chica" and pl._p["distribucion_agar"] == "gamma"
        assert "alga de menor rendimiento" in pl.nombre and "variante_tomate" not in pl._p
    pl = SI.planta_en_blanco("agar", "mercado_agar", DM.desafio_tomate(DM.llegada_tomate()))     # un desafío de tomate no se usa
    assert pl._p.get("variante_agar") is None and pl.nombre == "Carta en blanco: Agar agar"


def test_tomate_sin_cambios():
    r = DM.llegada_tomate()
    d = DM.desafio_tomate(r)
    assert not any(k.endswith("_agar") for k in d) and d["tipo_planta"] == "tomate"
    pl = SI.armar_planta("tomate", r)
    inf = SI.informe(pl)
    assert inf["variante_tomate"] == "agrozzi" and "variante_agar" not in inf and "variante_agar" not in pl._p
    b = SI.planta_en_blanco("tomate", r, d)
    assert b._p["variante_tomate"] == "agrozzi" and "variante_agar" not in b._p


# ---------------------------------------------------------------- docente: familia «agar»
@pytest.fixture
def g(tmp_path):
    return GE.BaseGenericos(BaseDatos(str(tmp_path / "t.db")))


def _curso(g, n):
    cid = g.crear_curso("PAT 2026-2")
    g.cargar_estudiantes(cid, "\n".join(f"Estudiante {i:03d}" for i in range(n)))
    return cid


def test_familia_agar_trescientas_combinaciones_naturales(g):
    assert "agar" in GE.FAMILIAS
    c = g.combinaciones(1, "agar")
    assert len(c) == 300 == len(set(c)) and all(n == 2 for n in [f["nivel"] for f in g.compatibilidad_agar()])
    assert g.nivel_agar("base", "uniforme") == 2 and g.nivel_agar("base|chica", "gamma") == 2
    assert len(g.compatibilidad_agar("intensivo")) == 30 and len(g.compatibilidad_agar("intensivo|grande", "beta")) == 1


def test_reparto_agar_sin_repetir_y_reproducible(g):
    cid = _curso(g, 25)
    r = g.asignar_al_azar(cid, 3, familia="agar")
    a = r["asignaciones"]
    assert len(a) == 25 and not r["avisos"] and all(x["familia"] == "agar" and x["planta_id"] == GE.PLANTA_AGAR for x in a)
    assert len({GE.combinacion(x) for x in a}) == 25
    assert {x["modelo_agar"] for x in a} <= set(PA.IDS_MODELOS) and {x["tamano_agar"] for x in a} <= set(PA.IDS_TAMANOS)
    r2 = g.asignar_al_azar(cid, 3, familia="agar")
    assert [GE.combinacion(x) for x in r2["asignaciones"]] == [GE.combinacion(x) for x in a]


def test_asignacion_manual_agar_y_lo_que_ve_el_estudiante(g):
    cid = _curso(g, 2)
    est = [u["nombre_usuario"] for u in g.listar_usuarios(cid, "estudiante")]
    r = g.asignar(cid, est[0], "alcali_fuerte", "weibull", familia="agar", tamano_id="grande", asignado_por="docente")
    assert not r["avisos"]
    a = g.asignacion_de(est[0])
    assert a["familia"] == "agar" and (a["modelo_agar"], a["tamano_agar"], a["distribucion_agar"]) == ("alcali_fuerte", "grande", "weibull")
    assert a["variante_agar"] == "alcali_fuerte|grande" and a["detalle_planta"]["nombre"] == PA.variante("alcali_fuerte|grande")["nombre"]
    assert a["detalle_demanda"]["nombre"] == "Weibull" and a["nivel"] == 2 and a["justificacion"]
    r = g.asignar(cid, est[1], "alcali_fuerte|grande", "weibull", familia="agar")
    assert any("misma combinación" in x for x in r["avisos"])
    for args in (("no_existe", "weibull", None), ("base", "no_existe", None), ("base", "weibull", "enorme")):
        with pytest.raises(KeyError):
            g.asignar(cid, est[1], args[0], args[1], familia="agar", tamano_id=args[2])


def test_familias_tomate_agar_y_generica_no_se_mezclan(g):
    cid = _curso(g, 3)
    est = [u["nombre_usuario"] for u in g.listar_usuarios(cid, "estudiante")]
    g.asignar(cid, est[0], "agrozzi", "bimodal", familia="tomate", tamano_id="chica")
    g.asignar(cid, est[1], "base", "bimodal", familia="agar", tamano_id="chica")
    fila = {x["nombre_usuario"]: x for x in g.asignaciones(cid)}
    assert fila[est[0]]["familia"] == "tomate" and fila[est[0]]["planta_id"] == GE.PLANTA_TOMATE
    assert fila[est[1]]["familia"] == "agar" and fila[est[1]]["planta"].startswith("Planta chica de agar agar")
    assert GE.combinacion(fila[est[0]])[0] == "tomate" and GE.combinacion(fila[est[1]]) == ("agar", "base|chica", "bimodal")
    r = g.asignar_al_azar(cid, 9, familia="agar")                     # conserva las manuales de las otras familias
    fila = {x["nombre_usuario"]: x for x in r["asignaciones"]}
    assert fila[est[0]]["familia"] == "tomate" and fila[est[1]]["familia"] == "agar" and fila[est[2]]["familia"] == "agar"
    assert fila[est[1]]["variante_agar"] == "base|chica"
