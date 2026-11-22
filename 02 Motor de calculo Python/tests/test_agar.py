"""Pruebas del rubro agar agar (PAT 143 b, tarea 9 del plan PAT 141): catálogo catalogos/agar.py, escenario escenarios/agar.py,
su registro en el motor (registro, plantas genéricas, precedencia, plantillas, curso, temporada, calidad, auxiliares, costeo y base)
y que las cifras de la planta basada en Agrozzi no cambian."""
import csv
import json
import pytest
from pat_sim.catalogos import agar as A, registro as RG, plantas_genericas as PG
from pat_sim.catalogos.registro import TIPOS, catalogo, planta_desde_dict
from pat_sim.escenarios import agar, agrozzi
from pat_sim.motor import precedencia as PR, validador as V, sintesis as SI
from pat_sim.motor.resumen import resumen_planta
from pat_sim.simbolos import iso10628 as ISO

TIPOS_AGAR = ("alimentacion_alga", "lavado_alga", "tratamiento_alcalino_agar", "lavado_neutralizacion_agar", "extractor_agar",
              "filtro_prensa_agar", "gelificador_agar", "prensa_gel_agar", "secador_agar", "molino_agar", "envasado_agar")


@pytest.fixture(scope="module")
def pl():
    return agar.crear()


@pytest.fixture(scope="module")
def r(pl):
    return agar.resumen_corto(pl)


# ------------------------------------------------------------------ catálogo y registro
def test_rubro_registrado_con_sus_equipos():
    assert RG.RUBROS["agar"] == "Agar agar" and RG.nombre_rubro("agar") == "Agar agar"
    tipos = {c.tipo for c in catalogo("agar")}
    assert set(TIPOS_AGAR) <= tipos and "caldera_gas" in tipos
    assert not {c.tipo for c in catalogo("pellet")} & set(TIPOS_AGAR)       # no aparecen en otros rubros


def test_simbolos_iso_10628_coherentes():
    for t in TIPOS_AGAR:
        c = TIPOS[t]
        nombre, cat, letra, _dib = ISO.SIMBOLOS[c.simbolo]
        assert (c.iso_categoria, c.iso_letra) == (cat, letra), t
        assert PG.SIMBOLO_PROPIO[t] == c.simbolo, t


def test_los_genericos_iso_siguen_existiendo():
    # los símbolos que usa el agar también tienen su equipo genérico, que usan los tipos de planta de plantas_genericas
    for t in ("iso_reactor", "iso_camisa", "iso_filtro_prensa", "iso_intercambiador_placas", "iso_filtro", "iso_recipiente_agitado",
              "iso_bascula", "iso_molino_bolas", "iso_dosificador_rotativo"):
        assert t in TIPOS, t


def test_parametros_con_fuente_o_supuesto_justificado():
    for c in A.CATALOGO:
        for p in c.params_base:
            assert p.categoria in ("Literatura", "Derivado", "Supuesto", "Usuario", "Oficial", "Fabricante"), (c.tipo, p.clave)
            if p.categoria in ("Literatura", "Derivado", "Oficial", "Fabricante"):
                assert p.fuente, (c.tipo, p.clave)
            if p.categoria == "Supuesto" and p.clave not in ("capacidad", "estado"):
                assert p.justificacion or p.fuente, (c.tipo, p.clave)


def test_fuentes_del_rubro_en_el_indice():
    from pat_sim.datos.bd import CSV_FUENTES_AGAR
    with open(CSV_FUENTES_AGAR, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    assert [k for k in filas[0]] == ["cita", "archivo", "doi", "url", "fecha_consulta", "nota", "sha1"]
    assert len({x["archivo"] for x in filas}) == len(filas) >= 6
    assert all(x["cita"] and x["fecha_consulta"] and (x["url"] or x["doi"]) for x in filas)
    archivos = " ".join(x["archivo"] for x in filas)
    for autor in ("McHugh", "Armisen", "Belattmania", "Correa", "Escalante", "JECFA"):
        assert autor in archivos


# ------------------------------------------------------------------ balances del escenario base
def test_cierres_de_masa_solidos_y_energia(pl):
    filas = pl.cierres()
    assert len(filas) == len(pl.equipos)
    for f in filas:
        assert abs(f["cierre_masa"]) < 1e-6, f
        assert f["cierre_solidos"] is None or abs(f["cierre_solidos"]) < 1e-6, f
        assert abs(f["cierre_energia"]) < 1e-6, f


def test_especificacion_de_produccion_y_humedad(pl, r):
    assert r["producto_t_h"] == pytest.approx(agar.BASE["produccion"], rel=1e-8)
    assert r["producto_t_h"] * agar.BASE["dias"] * agar.BASE["hpd"] == pytest.approx(agar.AGAR_T_ANO, rel=1e-8)
    assert r["humedad_producto"] == pytest.approx(agar.BASE["Mseco"], rel=1e-10)
    d = pl.equipos["A1"].resultado.detalle
    assert d["cumple_humedad"] and not pl.avisos


def test_agar_extraido_y_perdido_en_la_torta(pl):
    seca = pl.salidas[("B1", "producto")].s
    W1 = pl.equipos["W1"].resultado.detalle; F1 = pl.equipos["F1"].resultado.detalle
    assert W1["agar_extraido_kgh"] == pytest.approx(agar.BASE["rend"] * seca, rel=1e-12)   # el lavado y la soda no disuelven materia seca
    filtrado = pl.salidas[("F1", "producto")]
    assert filtrado.s == pytest.approx(W1["agar_extraido_kgh"] - F1["agar_en_torta_kgh"], rel=1e-12)
    assert pl.salidas[("A1", "producto")].s == pytest.approx(filtrado.s, rel=1e-12)       # el agar seco llega entero al envase
    # el extracto queda con la concentración pedida en su fase líquida
    x = pl.salidas[("W1", "producto")]; Rs = x.s - W1["agar_extraido_kgh"]
    assert W1["agar_extraido_kgh"] / (x.m - Rs) == pytest.approx(agar.BASE["cext"], rel=1e-9)


def test_rendimiento_global_cerca_de_la_planta_de_lima(r):
    # Escalante y Noriega (2019, p. 37): 175 kg de agar por tonelada de alga seca
    assert 0.15 <= r["rendimiento_global"] <= 0.20


def test_gel_y_gel_prensado(pl):
    gel = pl.salidas[("W2", "producto")]; prensado = pl.salidas[("F2", "producto")]
    assert gel.x == pytest.approx(agar.BASE["cext"], rel=1e-9)        # sin residuo, el gel tiene la concentración del extracto
    assert prensado.x == pytest.approx(agar.BASE["xgel"], rel=1e-12)
    assert gel.T == pytest.approx(pl.equipos["W2"].v("T_gel"))


def test_soda_se_va_con_la_lejia_y_el_lavado(pl):
    naoh = pl.equipos["C1"].resultado.servicios["reactivo_kgh"]
    lejia = pl.salidas[("C1", "lejia")].s; alga = pl.salidas[("C1", "producto")]
    ef = pl.salidas[("R2", "efluente")].s
    assert lejia + ef == pytest.approx(naoh, rel=1e-12)
    assert pl.salidas[("R2", "producto")].extra["fr_naoh"] == 0.0 and alga.extra["fr_naoh"] > 0


def test_agua_y_reactivo_como_servicio_cuentan_en_el_balance(pl, r):
    agua = sum(e.resultado.servicios.get("agua_kgh", 0.0) for e in pl.equipos.values())
    assert r["agua_proceso_kgh"] == pytest.approx(agua) and agua > 0 and r["naoh_kgh"] > 0
    f = next(x for x in pl.cierres() if x["equipo"] == "C1")
    srv = pl.equipos["C1"].resultado.servicios
    assert f["masa_entra"] == pytest.approx(pl.salidas[("R1", "producto")].m + srv["agua_kgh"] + srv["reactivo_kgh"])


# ------------------------------------------------------------------ energía y recuperación de calor
def test_calor_de_proceso_y_caldera(pl, r):
    assert r["calor_proceso_kW"] == pytest.approx(r["calor_bano_kW"] + r["calor_extraccion_kW"] + r["calor_secado_kW"], rel=1e-12)
    assert pl.equipos["D1"].resultado.detalle["Q_vapor_kW"] == pytest.approx(r["calor_proceso_kW"], rel=1e-12)
    assert r["gas_kgh"] > 0


def test_sumideros_y_residuales(pl):
    snk = {s.equipo: s for s in pl.sumideros()}
    assert set(snk) == {"C1", "W1", "T1"}
    assert snk["C1"].T_out == agar.BASE["Tbano"] and snk["W1"].T_out == agar.BASE["Text"] and snk["T1"].T_out == agar.BASE["Tae"]
    res = {x.nombre: x for x in pl.residuales()}
    assert {"Lejía_C1", "Extracto_W2"} <= set(res) and any(n.startswith("Escape") for n in res)
    assert res["Extracto_W2"].T_out == pl.equipos["W2"].v("T_recuperable")      # no gelifica en el intercambiador
    todos = {x.nombre for x in pl.residuales(solo_mapa=False)}
    assert "Extracto_W2_gel" in todos and "Extracto_W2_gel" not in res


def test_consumo_especifico_del_secador_en_rango(r):
    assert 2.5 <= r["consumo_MJ_kg_agua"] <= 12.0


def test_recuperacion_con_un_sumidero_y_con_todos(pl, r):
    R = resumen_planta(pl)
    assert R["sumidero"]["equipo"] == "C1"                         # el baño alcalino es el mayor sumidero
    assert 0 < r["cascada"] <= r["pinch"] + 1e-9 <= r["Qsumidero"] + 1e-9
    m = agar.objetivo_pinch_multiple(pl)
    assert m["recuperable_kW"] <= min(m["Q_frias_kW"], m["Q_calientes_kW"]) + 1e-6
    assert m["recuperable_kW"] >= r["pinch"] - 1e-6                # con más sumideros se recupera al menos lo mismo
    assert m["Q_frias_kW"] - m["recuperable_kW"] == pytest.approx(m["Q_externo_min_kW"], rel=1e-9)


def test_tabla_del_problema_en_un_caso_simple():
    class _Pl:
        globales = dict(dT_min=10.0, T_final_residual=30.0)
        def residuales(self):
            from pat_sim.motor.corrientes import Residual
            return [Residual("H", "X", 150.0, 2.0, 0.0, 50.0)]
        def sumideros(self):
            from pat_sim.motor.equipos import Sumidero
            return [Sumidero("C", "Y", 40.0, 120.0, 3.0)]
    m = agar.objetivo_pinch_multiple(_Pl())
    # caliente 150→50 con CP 2 (200 kW); fría 40→120 con CP 3 (240 kW); ΔTmin 10: toda la caliente cabe (50 °C contra 40 °C a la
    # entrada de la fría y 150 contra 120 a la salida), así que faltan 40 kW de calor externo y no sobra enfriamiento
    assert m["Q_calientes_kW"] == pytest.approx(200.0) and m["Q_frias_kW"] == pytest.approx(240.0)
    assert m["Q_externo_min_kW"] == pytest.approx(40.0) and m["recuperable_kW"] == pytest.approx(200.0)
    assert m["Q_enfriamiento_min_kW"] == pytest.approx(0.0, abs=1e-9)


def test_sensibilidades_del_escenario():
    base = agar.resumen_corto(agar.crear(capacidades=False))
    caliente = agar.resumen_corto(agar.crear(capacidades=False, Tbano=90.0))
    diluido = agar.resumen_corto(agar.crear(capacidades=False, cext=0.015))
    assert caliente["calor_bano_kW"] > base["calor_bano_kW"]
    assert diluido["calor_extraccion_kW"] < base["calor_extraccion_kW"] and diluido["agua_proceso_kgh"] < base["agua_proceso_kgh"]


def test_avisos_de_equipos_fuera_de_orden():
    pl2 = agar.crear(capacidades=False)
    pl2.conexiones = [c for c in pl2.conexiones if not (c.origen in ("C1", "R2"))]
    pl2.conectar("C1", "producto", "W1", "entrada", nombre="3")      # sin lavado y neutralización: el extractor recibe soda
    pl2.quitar("R2"); pl2.resolver()
    assert any("soda" in a for a in pl2.avisos)


# ------------------------------------------------------------------ validador, precedencia y planta genérica
def test_validador_acepta_el_escenario_base_sin_errores(pl):
    tabla = PR.tabla_plantas()
    for vista in V.VISTAS:
        res = V.revisar(pl, vista, precedencia=tabla)
        assert not res["errores"] and not res["bloquea"], (vista, res["errores"])


def test_precedencia_del_agar_con_los_equivalentes(pl):
    t = PR.de_planta("agar")
    assert t.entrega("agar", "extractor_agar") == t.entrega("agar", "iso_camisa") == "extracto_caliente"
    assert t.entrega("agar", "secador_agar") == "agar_seco" and t.entrega("agar", "lavado_neutralizacion_agar") is None
    assert PR.violaciones(pl, PR.tabla_plantas()) == []
    assert SI.misma_cadena(pl, "agar") and SI.tipo_de(pl) == "agar"


def test_la_planta_automatica_del_agar_sigue_igual():
    # los equivalentes no entran como alternativas: la planta automática usa los tipos de la operación
    p = PG.planta("agar")
    assert all(not o["alternativas"] for o in p["operaciones"]) and all(o["equivalentes"] for o in p["operaciones"])
    pa = SI.armar_planta("agar", dict(titulo="Prueba", demanda_t_h=[0.05, 0.08, 0.06], periodo="mes", unidad="t"), alternativas=False)
    assert pa.resuelta and not set(TIPOS_AGAR) & {e.tipo for e in pa.equipos.values()}


def test_escenario_enlazado_en_plantas_genericas():
    assert "agar" in PG.EXISTENTES and PG.PLANTAS["agar"]["escenario_funcion"] == "pat_sim.escenarios.agar.crear"
    assert PG.PLANTAS["agar"]["produccion"]["valor"] == agar.AGAR_T_ANO
    pa = PG.crear_escenario("agar", capacidades=False)
    assert pa.rubro == "agar" and pa.resuelta


def test_guardar_y_cargar_en_json(pl):
    d = json.loads(json.dumps(pl.a_dict()))
    p2 = planta_desde_dict(d); p2.resolver()
    assert agar.resumen_corto(p2)["calor_proceso_kW"] == pytest.approx(agar.resumen_corto(pl)["calor_proceso_kW"], rel=1e-9)


# ------------------------------------------------------------------ pantallas del motor que listan rubros
def test_plantillas_curso_temporada_y_calidad():
    from pat_sim.escenarios import plantillas as PLT
    from pat_sim.motor import curso as CU, temporada as TE
    from pat_sim.catalogos import calidad as Q
    vacia = PLT.cargar("plantilla_agar")
    assert vacia.rubro == "agar" and not any(e.tipo.startswith("caldera") for e in vacia.equipos.values()) and not vacia.instrumentos
    assert PLT.cargar("ejemplo_agar").nombre == agar.NOMBRE
    var = CU.variante("ana.perez", "agar")
    pv = CU.crear_planta(var)
    assert pv.rubro == "agar" and pv.resuelta and set(var["planta"]) == {"produccion", "rend", "dias"}
    s = TE.supuestos(pv)
    assert s["camion"] == 10.0 and s["umbral"] == 0.0
    vs = Q.variables(agar.crear())
    assert [v.id for v in vs] == ["humedad"] and vs[0].hi == pytest.approx(18.0)
    assert [a["equipo"] for a in Q.acciones(agar.crear())] == ["T1"]


def test_auxiliares_costeo_y_seleccion(pl):
    from pat_sim.motor import auxiliares as AU, costeo as CO, seleccion as SEL
    filas = {f["servicio"]: f for f in AU.servicios(pl)["filas"]}
    assert filas["Agua de proceso"]["demanda"] == pytest.approx(pl.servicio_total("agua_kgh") / 1000.0)
    assert filas["Reactivos (NaOH)"]["demanda"] == pytest.approx(pl.servicio_total("reactivo_kgh"))
    items = {i["equipo"]: i for i in CO.lista_equipos(pl)}
    assert items["T1"]["clave"] == "secador_banda" and items["W1"]["clave"] == "extractor_agar"
    assert "Supuesto" in CO.REFERENCIAS["extractor_agar"]["fuente"]
    req = {x["equipo"] for x in SEL.requerimientos(pl)}
    assert {"W1", "T1", "C1"} <= req


def test_otros_rubros_sin_agua_de_proceso():
    from pat_sim.escenarios import pellet
    from pat_sim.motor import auxiliares as AU
    servicios = {f["servicio"] for f in AU.servicios(pellet.crear())["filas"]}
    assert "Agua de proceso" not in servicios and "Reactivos (NaOH)" not in servicios


def test_precarga_crea_el_proyecto_y_las_fuentes(tmp_path):
    from pat_sim.datos.bd import BaseDatos
    bd = BaseDatos(tmp_path / "agar.db")
    out = bd.precargar()
    assert out["fuentes_agar"] >= 6 and bd.obtener_proyecto(agar.NOMBRE)["rubro"] == "agar"
    assert bd.precargar().get("proyecto_agar") is None                 # idempotente


def test_cifras_de_agrozzi_no_cambian():
    R = agrozzi.resumen(agrozzi.crear())
    assert round(R["Qhb"], 1) == 15956.0 and round(R["cascada"], 1) == 9073.8 and round(R["pinch"], 1) == 9722.9
