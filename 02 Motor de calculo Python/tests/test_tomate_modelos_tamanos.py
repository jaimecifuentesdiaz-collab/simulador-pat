"""Pruebas de PAT 139 (14-11-2026, comentarios del profesor Torres, puntos 1 y 7): 10 modelos de planta de tomate (por °Brix y
proceso, sin tamaño) × 3 tamaños (chica, mediana y grande) × 10 distribuciones de la llegada = 300 combinaciones, la
compatibilidad con las 10 ids de PAT 138 y la asignación del docente con modelo, distribución y tamaño."""
import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.catalogos import plantas_tomate as PT
from pat_sim.datos import genericos as GE
from pat_sim.datos.bd import BaseDatos
from pat_sim.escenarios import agrozzi
from pat_sim.motor import demanda as DM, sintesis as SI, desafio as D


@pytest.fixture
def g(tmp_path):
    return GE.BaseGenericos(BaseDatos(str(tmp_path / "t.db")))


def _curso(g, n):
    cid = g.crear_curso("PAT 2026-2")
    g.cargar_estudiantes(cid, "\n".join(f"Estudiante {i:03d}" for i in range(n)))
    return cid


# ------------------------------------------------------------------ catálogo: 10 modelos y 3 tamaños
def test_diez_modelos_distintos_sin_tamano_y_con_fuentes():
    assert len(PT.IDS_MODELOS) == 10 and PT.MODELO_BASE in PT.MODELOS
    firmas = {(m["brix"], m["quiebre"], m["tvr"], m["N"]) for m in PT.MODELOS.values()}
    assert len(firmas) == 10                                                         # se distinguen por °Brix y proceso
    assert {m["brix"] for m in PT.MODELOS.values()} == {28.0, 30.0, 36.0, 38.0}
    assert {m["quiebre"] for m in PT.MODELOS.values()} == {"hot", "cold"}
    assert {m["evaporador"] for m in PT.MODELOS.values()} == set(PT.EVAPORADORES)
    assert {m["N"] for m in PT.MODELOS.values()} == {3, 4} and {m["tvr"] for m in PT.MODELOS.values()} == {True, False}
    for k, m in PT.MODELOS.items():
        assert not ({"temporada_t", "dias", "horas_dia"} & set(m))                  # sin tamaño
        assert "t por temporada" not in m["nombre"]
        f = PT.fuentes_modelo(k)
        assert set(f) == {"brix", "quiebre", "evaporador"} and all(f.values())
        txt = m["nombre"] + m["descripcion"] + m["corto"]
        assert "MM" not in txt and " don " not in txt and "—" not in txt and "–" not in txt
    assert [t["id"] for t in PT.tabla_modelos()] == list(PT.IDS_MODELOS)


def test_tres_tamanos_con_fuente_o_supuesto():
    assert PT.IDS_TAMANOS == ("chica", "mediana", "grande")
    med = PT.tamano("mediana")
    assert (med["temporada_t"], med["dias"], med["horas_dia"]) == (450000.0, 76, 24.0)          # Agrozzi
    assert "DIA_Agrozzi_rev0.pdf, p. 47" in med["fuentes"]["temporada_t"] and "Balance de Masa_Rev0.pdf, p. 6" in med["fuentes"]["dias"]
    ch, gr = PT.tamano("chica"), PT.tamano("grande")
    assert ch["temporada_t"] < med["temporada_t"] < gr["temporada_t"] and ch["media_t_h"] < med["media_t_h"] < gr["media_t_h"]
    for t in (ch, gr):
        assert "Supuesto" in t["fuentes"]["temporada_t"] and "Supuesto" in t["fuentes"]["dias"]
    assert "Supuesto" in ch["fuentes"]["horas_dia"] and "Balance de Masa_Rev0.pdf, p. 6" in gr["fuentes"]["horas_dia"]
    assert [t["id"] for t in PT.tabla_tamanos()] == list(PT.IDS_TAMANOS)
    with pytest.raises(KeyError):
        PT.tamano("enorme")
    with pytest.raises(KeyError):
        PT.modelo("no_existe")


def test_treinta_plantas_y_modelo_agrozzi_mediana_es_agrozzi():
    ids = PT.combinaciones()
    assert len(ids) == 30 and len(set(ids)) == 30
    r0 = agrozzi.resumen(agrozzi.crear()); r1 = agrozzi.resumen(PT.crear_escenario("agrozzi|mediana"))
    for k in ("Qhb", "cascada", "pinch"):
        assert r1[k] == pytest.approx(r0[k], abs=1e-9)
    assert (round(r1["Qhb"], 1), round(r1["cascada"], 1), round(r1["pinch"], 1)) == (15956.0, 9073.8, 9722.9)
    assert PT.es_base("agrozzi") and PT.es_base("agrozzi|mediana") and not PT.es_base("agrozzi|chica")
    assert PT.kw_escenario("agrozzi|mediana") == PT.kw_escenario("agrozzi")
    assert PT.variante("agrozzi")["modelo"] == "agrozzi" and PT.variante("agrozzi")["tamano"] == "mediana"


@pytest.mark.parametrize("cid", PT.combinaciones())
def test_cada_planta_modelo_tamano_se_resuelve(cid):
    m, t = PT.separar_id(cid)
    v = PT.variante(cid); M, T = PT.modelo(m), PT.tamano(t)
    assert v["id"] == cid and v["modelo"] == m and v["tamano"] == t and not v["legada"]
    assert (v["temporada_t"], v["dias"], v["horas_dia"]) == (T["temporada_t"], T["dias"], T["horas_dia"])
    assert (v["brix"], v["quiebre"], v["tvr"], v["N"]) == (M["brix"], M["quiebre"], M["tvr"], M["N"])
    assert PT.capacidad_media_t_h(cid) == pytest.approx(T["media_t_h"])
    f = PT.fuentes(cid)
    assert set(f) == {"temporada_t", "dias", "horas_dia", "brix", "quiebre", "evaporador"} and all(f.values())
    pl = PT.crear_escenario(cid, capacidades=False)
    assert pl.resuelta and not pl.avisos
    assert pl.equipos["B1"].v("temporada_t") == T["temporada_t"] and pl.equipos["W4"].v("N") == M["N"]
    assert pl.propiedad_entrada("A1", "x") == pytest.approx(M["brix"] / 100, abs=1e-8)


def test_mas_tamano_mas_calor_de_quiebre():
    q = {t: agrozzi.resumen(PT.crear_escenario(f"hot30_me3|{t}", capacidades=False))["Qhb"] for t in PT.IDS_TAMANOS}
    assert q["chica"] < q["mediana"] < q["grande"]


# ------------------------------------------------------------------ compatibilidad con las 10 ids de PAT 138
def test_ids_viejas_siguen_funcionando():
    assert len(PT.IDS) == 10 and len(PT.VARIANTES) == 10 and len(PT.tabla()) == 10
    assert PT.variante("pequena_28")["temporada_t"] == 30000.0 and PT.variante("muy_grande_36cb")["temporada_t"] == 900000.0
    assert PT.capacidad_media_t_h("mediana_30") == pytest.approx(200000.0 / (70 * 24))
    for k in PT.IDS:
        v = PT.variante(k)
        assert v["id"] == k and v["legada"]
        m, t = PT.traducir(k)                                    # id vieja → (modelo, tamaño más cercano)
        assert m in PT.MODELOS and t in PT.TAMANOS
        assert (PT.modelo(m)["brix"], PT.modelo(m)["quiebre"], PT.modelo(m)["tvr"], PT.modelo(m)["N"]) == (v["brix"], v["quiebre"], v["tvr"], v["N"])
        assert k in PT.VARIANTES and PT.VARIANTES[k]["nombre"] == v["nombre"]
        assert PT.crear_escenario(k, capacidades=False).resuelta
    assert PT.traducir("pequena_28") == ("hot28_me3", "chica") and PT.traducir("agrozzi") == ("agrozzi", "mediana")
    assert PT.traducir("muy_grande_36cb") == ("cold36_tvr4", "grande")
    # las ids de PAT 139 también valen donde se esperaba una id de PAT 138 (ui/comun.tomate_sesion usa «in PT.VARIANTES»)
    assert "agrozzi|chica" in PT.VARIANTES and "hot28_me3" in PT.VARIANTES and "no|existe" not in PT.VARIANTES and None not in PT.VARIANTES
    assert PT.VARIANTES["cold38_tvr3|grande"]["temporada_t"] == 900000.0 and PT.VARIANTES.get("x") is None
    assert PT.variante("cold38_tvr3")["tamano"] == "mediana"                                     # un modelo solo es mediano
    with pytest.raises(KeyError):
        PT.variante("agrozzi|enorme")
    with pytest.raises(KeyError):
        PT.variante("no_existe")


# ------------------------------------------------------------------ llegada y desafío con modelo, distribución y tamaño
@pytest.mark.parametrize("tam", PT.IDS_TAMANOS)
def test_llegada_con_modelo_y_tamano(tam):
    T = PT.tamano(tam)
    r = DM.llegada_tomate(modelo="cold36_tvr3", tamano=tam, dist_id="beta", perdida_1pct=False)
    assert r["modelo"] == "cold36_tvr3" and r["tamano"] == tam and r["variante"] == f"cold36_tvr3|{tam}" and r["distribucion"] == "beta"
    assert len(r["serie"]) == T["dias"] and sum(r["serie"]) == pytest.approx(T["temporada_t"], rel=1e-12)
    assert r["serie_t_h"] == pytest.approx([x / T["horas_dia"] for x in r["serie"]])
    b = r["extra"]["balance"]
    assert b["cosechado"] == pytest.approx(b["procesado"] + b["perdido"], rel=1e-12)
    claves = {s["clave"] for s in r["supuestos"]}
    assert {"brix", "quiebre", "evaporador", "temporada_t", "dias", "horas_dia", "distribucion"} <= claves
    assert all(s["fuente"] for s in r["supuestos"])


def test_llegada_sin_tamano_es_mediana_y_equivale_a_la_id_compuesta():
    a = DM.llegada_tomate(modelo="agrozzi", dist_id="normal_truncada", cv=0.0, perdida_1pct=False)
    b = DM.llegada_tomate("agrozzi|mediana", "normal_truncada", cv=0.0, perdida_1pct=False)
    c = DM.llegada_tomate(tamano="mediana", dist_id="normal_truncada", cv=0.0, perdida_1pct=False)
    assert a["serie"] == b["serie"] == c["serie"] and a["tamano"] == "mediana" and len(a["serie"]) == 76
    assert a["serie"] == pytest.approx(DM.llegada_tomate("agrozzi", "normal_truncada", cv=0.0, perdida_1pct=False)["serie"], rel=1e-12)


def test_desafio_tomate_guarda_modelo_tamano_distribucion_y_variante_compuesta():
    r = DM.llegada_tomate(modelo="hot28_tvr3", tamano="chica", dist_id="bimodal")
    d = DM.desafio_tomate(r, "Ana Pérez")
    assert (d["modelo_tomate"], d["tamano_tomate"], d["distribucion_tomate"], d["variante_tomate"]) == ("hot28_tvr3", "chica", "bimodal", "hot28_tvr3|chica")
    assert d["tipo_planta"] == "tomate" and d["logica"] == "agricola" and d["rubro"] == "tomate"
    assert d["demanda_t_h"] == pytest.approx(r["serie_t_h"]) and d["demanda_t_h"][0] == pytest.approx(d["demanda"][0] / 20.0)   # chica: 20 h
    assert "don" not in d["enunciado"].split() and "MM" not in d["titulo"] and not D.validar(DM.a_desafio(r, "serie", rubro="tomate"))
    assert PT.variante(d["variante_tomate"])["tamano"] == "chica"
    v = DM.desafio_tomate(DM.llegada_tomate("pequena_28", "normal"))                         # una id vieja sigue igual
    assert v["variante_tomate"] == "pequena_28" and v["modelo_tomate"] == "hot28_me3" and v["tamano_tomate"] == "chica"


def test_planta_automatica_y_en_blanco_con_la_id_compuesta():
    r = DM.llegada_tomate(modelo="cold38_me3", tamano="grande", dist_id="weibull", perdida_1pct=False)
    des = DM.desafio_tomate(r)
    pl = SI.armar_planta("tomate", des, desafio=des)
    inf = SI.informe(pl)
    assert SI.variante_de(pl) == "cold38_me3|grande" and inf["variante_tomate"] == "cold38_me3|grande" and inf["distribucion_tomate"] == "weibull"
    assert "900.000 t" in pl.nombre and any("Cold break" in e.nombre for e in pl.equipos.values())
    assert inf["dimensionamiento"]["materia_prima_diseno_t_h"] == pytest.approx(1.10 * DM.percentil(r["serie_t_h"], 95))
    b = SI.planta_en_blanco("tomate", des, des)
    assert SI.es_carta_en_blanco(b) and SI.variante_de(b) == "cold38_me3|grande" and "900.000 t" in b.nombre
    v = SI.armar_planta("tomate", variante="hot30_tvr4|chica")
    assert SI.variante_de(v) == "hot30_tvr4|chica" and "150.000 t" in v.nombre


def test_trescientas_combinaciones_dan_series_validas():
    vistas = set()
    for m in PT.IDS_MODELOS:
        for t in PT.IDS_TAMANOS:
            for dist in DM.IDS_DISTRIBUCIONES:
                r = DM.llegada_tomate(modelo=m, tamano=t, dist_id=dist, perdida_1pct=False)
                assert sum(r["serie"]) == pytest.approx(PT.tamano(t)["temporada_t"], rel=1e-9) and min(r["serie"]) >= 0
                vistas.add((r["modelo"], r["tamano"], r["distribucion"]))
    assert len(vistas) == 300


# ------------------------------------------------------------------ asignación del docente: modelo × distribución × tamaño
def test_siembra_de_modelos_tamanos_y_trescientas_combinaciones(g):
    c = g.contar()
    assert (c["modelos_tomate"], c["tamanos_tomate"], c["compatibilidad_modelo_tomate"]) == (10, 3, 300)
    assert c["variantes_tomate"] == 10 and c["compatibilidad_tomate"] == 100                  # lo de ayer se conserva
    assert g.sembrar_modelos_tomate() == {"modelos_tomate": 0, "tamanos_tomate": 0, "compatibilidad_modelo_tomate": 0}
    filas = g.compatibilidad_tomate()
    assert len(filas) == 300 and {f["tamano_id"] for f in filas} == set(PT.IDS_TAMANOS) and all(f["nivel"] == 2 for f in filas)
    assert len(g.combinaciones(1, "tomate")) == 300 and len(set(g.combinaciones(2, "tomate"))) == 300
    assert len(g.compatibilidad_tomate("agrozzi", tamano_id="grande")) == 10 and len(g.compatibilidad_tomate("agrozzi|chica")) == 10
    assert g.nivel_tomate("agrozzi", "bimodal") == g.nivel_tomate("agrozzi|mediana", "bimodal") == g.nivel_tomate("agrozzi", "bimodal", "mediana") == 2
    assert g.nivel_tomate("pequena_28", "bimodal") == 2                                         # id vieja: tabla de 10 × 10
    assert g.nivel_tomate("agrozzi", "no_existe") is None


def test_reparto_300_sin_repetir_con_tamanos_distintos(g):
    cid = _curso(g, 300)
    r = g.asignar_al_azar(cid, 7, familia="tomate")
    a = r["asignaciones"]
    assert len(a) == 300 and not r["avisos"] and r["repetidas"] == 0 and r["combinaciones"] == 300
    assert len({(x["variante_tomate"], x["tamano_tomate"], x["distribucion_tomate"]) for x in a}) == 300
    assert {x["tamano_tomate"] for x in a} == set(PT.IDS_TAMANOS) and {x["variante_tomate"] for x in a} == set(PT.IDS_MODELOS)
    assert all(x["variante_compuesta"] == f"{x['variante_tomate']}|{x['tamano_tomate']}" and x["modelo_tomate"] == x["variante_tomate"] for x in a)
    assert all(x["familia"] == "tomate" and x["nivel"] == 2 and x["planta"] and x["demanda"] for x in a)
    primeras = sorted(a, key=lambda x: x["id"])[:10]
    assert len({x["variante_tomate"] for x in primeras}) == 10                                   # la ronda intercala los modelos
    r2 = g.asignar_al_azar(cid, 7, familia="tomate")
    k = lambda r_: {x["nombre_usuario"]: (x["variante_tomate"], x["tamano_tomate"], x["distribucion_tomate"]) for x in r_["asignaciones"]}
    assert k(r) == k(r2)                                                                         # misma semilla, mismo reparto


def test_asignacion_manual_con_tamano_y_detalle(g):
    cid = _curso(g, 4)
    est = [u["nombre_usuario"] for u in g.listar_usuarios(cid, "estudiante")]
    r = g.asignar(cid, est[0], "cold36_tvr3", "weibull", familia="tomate", tamano_id="grande")
    assert r["avisos"] == []
    a = g.asignacion_de(est[0])
    assert (a["variante_tomate"], a["tamano_tomate"], a["distribucion_tomate"]) == ("cold36_tvr3", "grande", "weibull")
    assert a["detalle_planta"]["temporada_t"] == 900000.0 and a["detalle_planta"]["quiebre"] == "cold" and a["nivel"] == 2 and a["justificacion"]
    assert a["variante_compuesta"] == "cold36_tvr3|grande" and a["planta_id"] == GE.PLANTA_TOMATE
    r = g.asignar(cid, est[1], "cold36_tvr3|grande", "weibull", familia="tomate")                # id compuesta
    assert r["avisos"] and est[0] in r["avisos"][0]                                               # misma combinación
    r = g.asignar(cid, est[2], "cold36_tvr3", "weibull", familia="tomate", tamano_id="chica")      # otro tamaño: no es repetida
    assert r["avisos"] == []
    assert g.asignacion_de(est[3]) is None
    with pytest.raises(KeyError):
        g.asignar(cid, est[3], "cold36_tvr3", "weibull", familia="tomate", tamano_id="enorme")
    with pytest.raises(KeyError):
        g.asignar(cid, est[3], "no_existe", "weibull", familia="tomate", tamano_id="chica")


def test_nivel_cero_por_tamano(g):
    cid = _curso(g, 1)
    est = g.listar_usuarios(cid, "estudiante")[0]["nombre_usuario"]
    g.fijar_compatibilidad_tomate("agrozzi", "uniforme", 0, "Con la planta chica no se ejercita este caso", tamano_id="chica")
    assert len(g.combinaciones(1, "tomate")) == 299 and g.nivel_tomate("agrozzi|chica", "uniforme") == 0
    assert g.nivel_tomate("agrozzi", "uniforme") == 2                                            # la mediana sigue natural
    with pytest.raises(ValueError):
        g.asignar(cid, est, "agrozzi", "uniforme", familia="tomate", tamano_id="chica")
    assert g.asignar(cid, est, "agrozzi", "uniforme", forzar=True, familia="tomate", tamano_id="chica")["avisos"]
    with pytest.raises(ValueError):
        g.fijar_compatibilidad_tomate("agrozzi", "uniforme", 1, "  ")


def test_manuales_conservadas_salen_del_reparto(g):
    cid = _curso(g, 3)
    est = [u["nombre_usuario"] for u in g.listar_usuarios(cid, "estudiante")]
    g.asignar(cid, est[0], "agrozzi", "normal", familia="tomate", tamano_id="grande")
    r = g.asignar_al_azar(cid, 5, familia="tomate")
    fila = {x["nombre_usuario"]: x for x in r["asignaciones"]}
    assert (fila[est[0]]["variante_tomate"], fila[est[0]]["tamano_tomate"], fila[est[0]]["modo"]) == ("agrozzi", "grande", "manual")
    assert all((fila[e]["variante_tomate"], fila[e]["tamano_tomate"], fila[e]["distribucion_tomate"]) != ("agrozzi", "grande", "normal") for e in est[1:])
    assert GE.combinacion(fila[est[0]]) == ("tomate", "agrozzi|grande", "normal")


def test_asignaciones_guardadas_con_id_vieja_siguen_mostrandose(g):
    """Una asignación hecha ayer (variante vieja, sin tamaño) conserva su planta, su nivel y su detalle."""
    cid = _curso(g, 2)
    est = [u["nombre_usuario"] for u in g.listar_usuarios(cid, "estudiante")]
    r = g.asignar(cid, est[0], "pequena_28", "bimodal", familia="tomate")                        # id vieja
    assert r["avisos"] == []
    fila = g.asignaciones(cid)[0]
    assert fila["variante_tomate"] == "pequena_28" and fila["tamano_tomate"] is None
    assert fila["planta"] == PT.variante("pequena_28")["nombre"] and fila["nivel"] == 2 and fila["familia"] == "tomate"
    a = g.asignacion_de(est[0])
    assert a["detalle_planta"]["temporada_t"] == 30000.0 and a["justificacion"] and a["variante_compuesta"] == "pequena_28"
    # lo que dejó PAT 139 de ayer: la fila escrita directamente con las columnas viejas
    with g._con() as con:
        con.execute("UPDATE asignaciones SET variante_tomate = 'grande_36cb', distribucion_tomate = 'beta', tamano_tomate = NULL "
                    "WHERE usuario_id = (SELECT id FROM usuarios WHERE nombre_usuario = ?)", (est[0],))
    assert g.asignaciones(cid)[0]["planta"] == PT.variante("grande_36cb")["nombre"]
    # una vieja «agrozzi» sin tamaño es la agrozzi mediana: entra en la combinación que el reparto debe evitar
    with g._con() as con:
        con.execute("UPDATE asignaciones SET variante_tomate = 'agrozzi', distribucion_tomate = 'normal' WHERE usuario_id = "
                    "(SELECT id FROM usuarios WHERE nombre_usuario = ?)", (est[0],))
    assert GE.combinacion(g.asignaciones(cid)[0]) == ("tomate", "agrozzi|mediana", "normal")
    assert g.asignacion_de(est[0])["detalle_planta"]["temporada_t"] == 450000.0
    r = g.asignar_al_azar(cid, 2, familia="tomate")
    assert len(r["asignaciones"]) == 2 and {x["familia"] for x in r["asignaciones"]} == {"tomate"}


def test_migra_base_de_pat139_de_ayer_sin_tamano(tmp_path):
    bd = BaseDatos(str(tmp_path / "ayer.db"))
    s = GE.ESQUEMA_GENERICOS.replace("    tamano_tomate TEXT,\n", "")
    i = s.index("CREATE TABLE IF NOT EXISTS modelos_tomate"); j = s.index("CREATE INDEX")
    s = s[:i] + s[j:]                                                                           # sin las tablas nuevas
    with bd._con() as con:
        con.executescript(s)
        assert "tamano_tomate" not in {f[1] for f in con.execute("PRAGMA table_info(asignaciones)")}
    g = GE.BaseGenericos(bd)
    g.sembrar_tomate()
    # base de ayer con una asignación vieja guardada (sin las columnas nuevas); se abre de nuevo y se migra
    cid = _curso(g, 2)
    g.asignar(cid, g.listar_usuarios(cid, "estudiante")[0]["nombre_usuario"], "mediana_30", "gamma", familia="tomate")
    g2 = GE.BaseGenericos(bd)
    with bd._con() as con:
        assert "tamano_tomate" in {f[1] for f in con.execute("PRAGMA table_info(asignaciones)")}
    c = g2.contar()
    assert (c["modelos_tomate"], c["tamanos_tomate"], c["compatibilidad_modelo_tomate"], c["compatibilidad_tomate"]) == (10, 3, 300, 100)
    assert g2.asignaciones(cid)[0]["planta"] == PT.variante("mediana_30")["nombre"]
    assert len(g2.asignar_al_azar(cid, 1, familia="tomate")["asignaciones"]) == 2
