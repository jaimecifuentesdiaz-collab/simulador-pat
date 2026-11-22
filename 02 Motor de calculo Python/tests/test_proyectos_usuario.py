"""PAT 138 (pedido de Jaime, 13-11-2026): proyectos del usuario en la base. Guardar con nombre automático por persona, nombres
repetidos, 200 proyectos, ida y vuelta de la planta y del estado (Agrozzi y planta ideal de tomate con llegada Weibull),
historial de versiones, renombrar, eliminar y versiones antiguas de la fase 4 que siguen cargando."""
import json, math, shutil, sqlite3
from pathlib import Path
import pytest
from pat_sim.datos import bd as BD
from pat_sim.datos.bd import BaseDatos, NombreRepetido, NOMBRE_AGROZZI, nombre_automatico, leer_nombre_automatico
from pat_sim.datos import estado_sesion as ES
from pat_sim.escenarios import agrozzi
from pat_sim.motor.resumen import resumen_planta

RAIZ_BD = Path(BD.__file__).resolve().parents[3] / "03 Base de datos" / "simulador_pat.db"


@pytest.fixture()
def bd(tmp_path):
    return BaseDatos(tmp_path / "proyectos.db")


@pytest.fixture(scope="module")
def agro():
    return agrozzi.crear()


def _economia():
    return dict(precio_gas=2.77, dolar=990.35, inversion=0.0, costo_anual=0.0, anios=20, tasa=0.10, precio_biomasa=6750.0)


def _cifras(r):
    return {k: float(r[k]) for k in ("Qhb", "cascada", "pinch", "alt2", "Q_externo_min", "vapor_linea_kW")}


def _mismos_equipos(a, b) -> bool:
    """Mismos equipos y parámetros; los números con 1e-9 relativo (el solver recalcula algunos, como el °Brix de salida)."""
    if list(a.equipos) != list(b.equipos):
        return False
    for k in a.equipos:
        x, y = a.equipos[k].a_dict(), b.equipos[k].a_dict()
        if {c: v for c, v in x.items() if c != "params"} != {c: v for c, v in y.items() if c != "params"} or x["params"].keys() != y["params"].keys():
            return False
        for c, v in x["params"].items():
            w = y["params"][c]
            if isinstance(v, (int, float)) and isinstance(w, (int, float)) and not isinstance(v, bool):
                if not math.isclose(float(v), float(w), rel_tol=1e-9, abs_tol=1e-12):
                    return False
            elif v != w:
                return False
    return True


# ---------------------------------------------------------------- tablas
def test_tablas_nuevas_se_crean_solas(bd):
    con = sqlite3.connect(bd.ruta)
    tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"proyectos_usuario", "proyectos_usuario_versiones"} <= tablas
    cols = {r[1] for r in con.execute("PRAGMA table_info(proyectos_usuario)")}
    assert {"id", "nombre", "persona", "numero", "creado", "modificado", "nota", "planta_json", "estado_json", "resumen_json"} <= cols
    assert set(bd.contar()) == {"proyectos", "versiones", "corridas", "fuentes", "parametros_catalogo"}   # contar() no cambia
    assert bd.contar_proyectos_usuario() == dict(proyectos=0, versiones=0)


def _proyectos_previos(ruta) -> int:
    import sqlite3
    with sqlite3.connect(ruta) as con:
        ok = con.execute("SELECT name FROM sqlite_master WHERE name = 'proyectos_usuario'").fetchone()
        return con.execute("SELECT COUNT(*) FROM proyectos_usuario").fetchone()[0] if ok else 0


def test_base_entregada_recibe_las_tablas_sin_perder_nada(tmp_path):
    """Una copia de simulador_pat.db (sin las tablas nuevas) las recibe al abrirse y sus 4 plantas precargadas siguen cargando."""
    copia = tmp_path / "copia.db"; shutil.copyfile(RAIZ_BD, copia)
    n_previos = _proyectos_previos(copia)          # PAT 140 h: la base real ya puede traer proyectos del guardado automático
    b = BaseDatos(copia)
    assert b.contar_proyectos_usuario()["proyectos"] == n_previos
    nombres = {p["nombre"] for p in b.listar_proyectos()}
    assert NOMBRE_AGROZZI in nombres and len(nombres) >= 4
    pid = b.obtener_proyecto(NOMBRE_AGROZZI)["id"]
    r = agrozzi.resumen(b.cargar_version(b.ultima_version(pid)))
    assert round(r["Qhb"], 1) == 15956.0 and round(r["cascada"], 1) == 9073.8 and round(r["pinch"], 1) == 9722.9


# ---------------------------------------------------------------- nombre automático
def test_nombre_automatico_por_persona(bd, agro):
    assert nombre_automatico("Ana Pérez", 1) == "Proyecto de Ana Pérez 1" and nombre_automatico("", 3) == "Proyecto 3"
    assert leer_nombre_automatico("Proyecto de Ana  Pérez 12") == ("Ana Pérez", 12)
    assert leer_nombre_automatico("Proyecto 4") == ("", 4) and leer_nombre_automatico("Mi planta") is None
    assert bd.nombre_sugerido("Ana Pérez") == "Proyecto de Ana Pérez 1"
    g1 = bd.guardar_proyecto_usuario(agro, persona="Ana Pérez")
    g2 = bd.guardar_proyecto_usuario(agro, persona="  ana   pérez ")          # misma persona con otras mayúsculas y espacios
    g3 = bd.guardar_proyecto_usuario(agro, persona="Luis Soto")
    g4 = bd.guardar_proyecto_usuario(agro)
    assert (g1["nombre"], g2["nombre"]) == ("Proyecto de Ana Pérez 1", "Proyecto de ana pérez 2")
    assert g3["nombre"] == "Proyecto de Luis Soto 1" and g4["nombre"] == "Proyecto 1"
    assert bd.nombre_sugerido("Ana Pérez") == "Proyecto de Ana Pérez 3" and bd.nombre_sugerido("") == "Proyecto 2"
    p = bd.obtener_proyecto_usuario(g1["id"])
    assert p["persona"] == "Ana Pérez" and p["numero"] == 1 and p["n_versiones"] == 1
    # un nombre propio no cuenta para el número; uno con la forma automática sí
    bd.guardar_proyecto_usuario(agro, nombre="Mi planta de prueba", persona="Ana Pérez")
    bd.guardar_proyecto_usuario(agro, nombre="Proyecto de Ana Pérez 7")
    assert bd.nombre_sugerido("Ana Pérez") == "Proyecto de Ana Pérez 8"


def test_nombre_repetido_avisa_y_ofrece_sobrescribir_o_el_siguiente(bd, agro):
    g = bd.guardar_proyecto_usuario(agro, persona="Ana Pérez", nota="primera")
    with pytest.raises(NombreRepetido) as e:
        bd.guardar_proyecto_usuario(agro, nombre="proyecto de ana pérez 1")      # sin distinguir mayúsculas
    assert e.value.existente["id"] == g["id"] and e.value.sugerido == "Proyecto de Ana Pérez 2"
    s = bd.guardar_proyecto_usuario(agro, nombre="Proyecto de Ana Pérez 1", sobrescribir=True, nota="segunda")
    assert s["id"] == g["id"] and s["version"] == 2 and not s["nuevo"]
    assert bd.contar_proyectos_usuario() == dict(proyectos=1, versiones=2)
    n = bd.guardar_proyecto_usuario(agro, nombre=e.value.sugerido)
    assert n["nombre"] == "Proyecto de Ana Pérez 2" and n["nuevo"]
    with pytest.raises(NombreRepetido):                                         # el abierto no puede tomar el nombre de otro
        bd.guardar_proyecto_usuario(agro, nombre="Proyecto de Ana Pérez 1", proyecto_id=n["id"])


def test_guardar_200_proyectos_sin_limite(bd):
    pl = agrozzi.crear()
    ids = [bd.guardar_proyecto_usuario(pl, persona="Curso ICI")["id"] for _ in range(200)]
    assert len(set(ids)) == 200 and bd.contar_proyectos_usuario()["proyectos"] == 200
    lista = bd.listar_proyectos_usuario()
    assert len(lista) == 200 and len({p["nombre"] for p in lista}) == 200
    assert {p["numero"] for p in lista} == set(range(1, 201))
    assert bd.nombre_sugerido("Curso ICI") == "Proyecto de Curso ICI 201"
    assert len(bd.listar_proyectos_usuario(buscar="ici 17")) == 11                    # 17 y 170 a 179
    assert len(bd.listar_proyectos_usuario(buscar="curso ici 1")) == 1 + 10 + 100     # 1, 10 a 19 y 100 a 199
    assert "planta_json" not in lista[0] and isinstance(lista[0]["resumen"], dict)


def test_buscar_sin_tildes_ni_mayusculas(bd, agro):
    bd.guardar_proyecto_usuario(agro, persona="Ana Pérez"); bd.guardar_proyecto_usuario(agro, persona="Luis Soto")
    assert [p["persona"] for p in bd.listar_proyectos_usuario(buscar="perez")] == ["Ana Pérez"]
    assert [p["persona"] for p in bd.listar_proyectos_usuario(buscar="SOTO")] == ["Luis Soto"]
    assert len(bd.listar_proyectos_usuario(persona="ana pérez")) == 1


# ---------------------------------------------------------------- ida y vuelta
def test_ida_y_vuelta_agrozzi_mismas_cifras(bd):
    pl = agrozzi.crear(); r0 = agrozzi.resumen(pl)
    ss = dict(economia=_economia(), cop=2.0, temporada={"tomate": {"dias": 76}}, alt_pesos=(0.5, 0.3, 0.2))
    est = ES.capturar(ss); res = ES.resumen(pl, est, cop=2.0)
    assert round(res["kw_recuperados"], 1) == 9073.8 and res["equipos"] == len(pl.equipos)
    g = bd.guardar_proyecto_usuario(pl, estado=est, resumen=res, persona="Ana Pérez")
    d = bd.cargar_proyecto_usuario(g["id"])
    pl2 = d["planta"]; r1 = agrozzi.resumen(pl2)
    c0, c1 = _cifras(r0), _cifras(r1)
    for k in c0:
        assert math.isclose(c0[k], c1[k], rel_tol=1e-9), k
    assert round(c1["Qhb"], 1) == 15956.0 and round(c1["cascada"], 1) == 9073.8 and round(c1["pinch"], 1) == 9722.9
    assert [c.__dict__ for c in pl2.conexiones] == [c.__dict__ for c in pl.conexiones]
    assert _mismos_equipos(pl, pl2)
    assert BD.a_json(pl2._p) == BD.a_json(pl._p)
    ss2 = dict(economia=dict(_economia(), precio_gas=9.9), op_resultado="viejo", desafio={"titulo": "otro"})
    ES.restaurar(ss2, d["estado"])
    assert ss2["economia"] == _economia() and ss2["cop"] == 2.0 and ss2["alt_pesos"] == (0.5, 0.3, 0.2)
    assert "desafio" not in ss2 and ss2["op_resultado"] == "viejo"      # el desafío del trabajo anterior no queda; lo ajeno no se toca
    assert d["resumen"]["kw_recuperados"] == res["kw_recuperados"]


def test_ida_y_vuelta_planta_ideal_de_tomate_weibull(bd):
    from pat_sim.motor import demanda as DM, sintesis as SI
    res = DM.llegada_tomate("mediana_36cb", "weibull")
    des = DM.desafio_tomate(res, "Ana Pérez")
    pl = SI.armar_planta("tomate", res, economia=_economia(), desafio=des, variante="mediana_36cb")
    assert pl.resuelta and len(pl.equipos) > 0
    r0 = resumen_planta(pl)
    ss = dict(desafio=des, economia=dict(_economia(), inversion=1500.0), cop=2.5, persona_nombre="Ana Pérez")
    est = ES.capturar(ss); resu = ES.resumen(pl, est, cop=2.5)
    assert resu["tipo_planta"] == "tomate" and resu["variante_tomate"] == "mediana_36cb" and resu["distribucion_tomate"] == "weibull"
    assert resu["capacidad_t_h"] and resu["capacidad_t_h"] > 0
    g = bd.guardar_proyecto_usuario(pl, estado=est, resumen=resu, persona="Ana Pérez")
    assert g["nombre"] == "Proyecto de Ana Pérez 1"
    d = bd.cargar_proyecto_usuario(g["id"]); pl2 = d["planta"]
    assert pl2.resuelta and SI.variante_de(pl2) == "mediana_36cb"
    assert BD.a_json(SI.informe(pl2)) == BD.a_json(SI.informe(pl))
    assert _mismos_equipos(pl, pl2)
    r1 = resumen_planta(pl2)
    for k in ("Qsumidero", "cascada", "pinch"):
        if r0.get(k) is not None:
            assert math.isclose(float(r0[k]), float(r1[k]), rel_tol=1e-9, abs_tol=1e-9), k
    ss2 = {}
    ES.restaurar(ss2, d["estado"])
    assert ss2["desafio"]["distribucion_tomate"] == "weibull" and ss2["desafio"]["variante_tomate"] == "mediana_36cb"
    assert ss2["desafio"]["demanda"] == list(des["demanda"]) and ss2["economia"]["inversion"] == 1500.0 and ss2["cop"] == 2.5
    assert d["proyecto"]["tipo_planta"] == "tomate" and d["proyecto"]["resumen"]["capacidad_t_h"] == resu["capacidad_t_h"]


def test_metadatos_de_parametros_vuelven(bd):
    pl = agrozzi.crear(); eq = next(iter(pl.equipos.values())); k = next(iter(eq.params))
    eq.set(k, eq.params[k].valor, categoria="Medido", fuente="Prueba PAT 138, 13-11-2026")
    g = bd.guardar_proyecto_usuario(pl, nombre="Con metadatos")
    p2 = bd.cargar_proyecto_usuario(g["id"])["planta"].equipos[eq.id].params[k]
    assert (p2.categoria, p2.fuente) == ("Medido", "Prueba PAT 138, 13-11-2026")


def test_carta_en_blanco_se_guarda_y_carga(bd):
    from pat_sim.motor import sintesis as SI
    pl = SI.planta_en_blanco("tomate", "agricola_tomate", None)
    g = bd.guardar_proyecto_usuario(pl, estado=ES.capturar({"economia": _economia()}), resumen=ES.resumen(pl))
    pl2 = bd.cargar_proyecto_usuario(g["id"])["planta"]
    assert not pl2.equipos and pl2.rubro == "tomate" and SI.es_carta_en_blanco(pl2)


# ---------------------------------------------------------------- historial, renombrar y eliminar
def test_historial_de_versiones(bd):
    pl = agrozzi.crear()
    g1 = bd.guardar_proyecto_usuario(pl, persona="Ana Pérez", nota="base")
    pl.equipos["W1"].set("T_salida", 96.0); pl.resolver()
    g2 = bd.guardar_proyecto_usuario(pl, proyecto_id=g1["id"], nota="hot break a 96 °C")
    assert (g1["version"], g2["version"], g2["id"]) == (1, 2, g1["id"]) and g2["nombre"] == g1["nombre"]
    assert [v["numero"] for v in bd.listar_versiones_usuario(g1["id"])] == [2, 1]
    assert bd.cargar_proyecto_usuario(g1["id"])["planta"].equipos["W1"].v("T_salida") == 96.0
    assert bd.cargar_proyecto_usuario(g1["id"], version=1)["planta"].equipos["W1"].v("T_salida") == 90.0
    assert bd.obtener_proyecto_usuario(g1["id"])["n_versiones"] == 2
    with pytest.raises(KeyError):
        bd.cargar_proyecto_usuario(g1["id"], version=9)


def test_renombrar(bd, agro):
    a = bd.guardar_proyecto_usuario(agro, persona="Ana Pérez"); b = bd.guardar_proyecto_usuario(agro, persona="Ana Pérez")
    assert bd.renombrar_proyecto_usuario(a["id"], "  Planta   de Ana ") == "Planta de Ana"
    p = bd.obtener_proyecto_usuario(a["id"])
    assert p["nombre"] == "Planta de Ana" and p["numero"] is None and p["persona"] == "Ana Pérez"
    with pytest.raises(NombreRepetido):
        bd.renombrar_proyecto_usuario(a["id"], "PROYECTO DE ANA PÉREZ 2")
    assert bd.renombrar_proyecto_usuario(a["id"], "Proyecto de Ana Pérez 5") and bd.obtener_proyecto_usuario(a["id"])["numero"] == 5
    with pytest.raises(ValueError):
        bd.renombrar_proyecto_usuario(b["id"], "   ")


def test_eliminar(bd, agro):
    a = bd.guardar_proyecto_usuario(agro, persona="Ana Pérez"); b = bd.guardar_proyecto_usuario(agro, persona="Ana Pérez")
    bd.guardar_proyecto_usuario(agro, proyecto_id=a["id"])
    bd.eliminar_proyecto_usuario(a["id"])
    assert bd.obtener_proyecto_usuario(a["id"]) is None and bd.contar_proyectos_usuario() == dict(proyectos=1, versiones=1)
    assert [p["id"] for p in bd.listar_proyectos_usuario()] == [b["id"]]
    g = bd.guardar_proyecto_usuario(agro, proyecto_id=a["id"], persona="Ana Pérez")   # el abierto ya no existe: se crea otro
    assert g["nuevo"] and g["nombre"] == "Proyecto de Ana Pérez 3"


def test_versiones_antiguas_siguen_cargando(bd):
    bd.precargar()
    pl = agrozzi.crear()
    pid = bd.crear_proyecto("Proyecto antiguo", "tomate"); v = bd.guardar_version(pid, pl, "antes de PAT 138")
    bd.guardar_proyecto_usuario(pl, persona="Ana Pérez")
    r = agrozzi.resumen(bd.cargar_version(v["id"]))
    assert round(r["cascada"], 1) == 9073.8
    assert {p["nombre"] for p in bd.listar_proyectos()} >= {NOMBRE_AGROZZI, "Proyecto antiguo"}
    assert all(p["nombre"] != "Proyecto de Ana Pérez 1" for p in bd.listar_proyectos())   # los nuevos van en su propia tabla


# ---------------------------------------------------------------- estado de la sesión
def test_estado_omite_lo_que_no_vuelve_igual_y_pone_al_dia_los_resultados():
    class Obj: pass
    ss = dict(economia=_economia(), cop=2.0, tableros=Obj(), costeo=dict(version=7, total_clp=10.0), layout=dict(pl_version=3, x=1),
              distribuciones={1: "clave entera", "a": 2}, flujo_registro={1: dict(propia="x", previas={}), 2: dict(propia="y", previas={1: "x"})},
              sel_usar_tomate_W1=["a", "b"], pl="planta", op="operación", des_nombre="Ana")
    est = ES.capturar(ss, version_planta=7)
    assert set(est["_meta"]["omitidas"]) == {"tableros", "distribuciones"} and est["_meta"]["codificadas"] == ["flujo_registro"]
    assert est["_meta"]["vigentes"] == ["costeo"] and "pl" not in est and "op" not in est and "des_nombre" not in est
    assert est["sel_usar_tomate_W1"] == ["a", "b"]
    json.dumps(est)                                                   # todo es JSON
    ss2 = dict(costeo=dict(version=1), sel_usar_tomate_W9=["z"], tableros="viejo")
    ES.restaurar(ss2, json.loads(json.dumps(est)), version_planta=42, defectos=dict(cop=9.0))
    assert ss2["costeo"]["version"] == 42 and ss2["layout"]["pl_version"] == 3
    assert "sel_usar_tomate_W9" not in ss2 and "tableros" not in ss2 and ss2["cop"] == 2.0
    assert ss2["flujo_registro"] == ss["flujo_registro"]                # claves enteras vuelven enteras


def test_huella_cambia_con_la_economia_y_no_con_los_resultados():
    ss = dict(economia=_economia(), cop=2.0, costeo=dict(version=1))
    h = ES.huella(ss)
    ss["costeo"] = dict(version=2); ss["flujo_etapa"] = 3
    assert ES.huella(ss) == h
    f = ES.foto(ss)
    ss["economia"] = dict(_economia(), alternativa="A4")             # una pantalla completa un valor por omisión: no es un cambio
    assert not ES.cambio(f, ES.foto(ss))
    ss["economia"] = dict(_economia(), tasa=0.12)
    assert ES.huella(ss) != h and ES.cambio(f, ES.foto(ss))
    ss["temporada"] = {}                                              # vacío es lo mismo que no tenerlo
    assert ES.foto(ss) == ES.foto({k: v for k, v in ss.items() if k != "temporada"})


# ---------------------------------------------------------------- PAT 139: dueño por proyecto con acceso controlado
def test_pat139_dueno_ve_y_escribe_solo_sus_proyectos(tmp_path):
    from pat_sim.datos.bd import BaseDatos, NombreRepetido
    from pat_sim.escenarios import agrozzi
    import pytest as _pt
    bd = BaseDatos(str(tmp_path / "d.db")); pl = agrozzi.crear()
    a = bd.guardar_proyecto_usuario(pl, nombre="Proyecto de Ana 1", usuario="ana.perez", dueno="ana.perez")
    b = bd.guardar_proyecto_usuario(pl, nombre="Proyecto de Beto 1", usuario="beto.soto", dueno="beto.soto")
    bd.guardar_proyecto_usuario(pl, nombre="Proyecto sin acceso")                        # computador de Jaime: sin dueño
    assert [p["nombre"] for p in bd.listar_proyectos_usuario(usuario="ana.perez")] == ["Proyecto de Ana 1"]
    assert [p["nombre"] for p in bd.listar_proyectos_usuario(usuario="Ana.Perez")] == ["Proyecto de Ana 1"]
    assert len(bd.listar_proyectos_usuario()) == 3                                     # docente o sin acceso: todos
    with _pt.raises(PermissionError):
        bd.guardar_proyecto_usuario(pl, usuario="ana.perez", proyecto_id=b["id"], dueno="ana.perez")
    with _pt.raises(NombreRepetido):
        bd.guardar_proyecto_usuario(pl, nombre="Proyecto de Beto 1", usuario="ana.perez", sobrescribir=True, dueno="ana.perez")
    r = bd.guardar_proyecto_usuario(pl, usuario="ana.perez", proyecto_id=a["id"], dueno="ana.perez")
    assert r["id"] == a["id"] and r["version"] == 2
    assert bd.es_dueno(bd.obtener_proyecto_usuario(a["id"]), "ana.perez") and not bd.es_dueno(bd.obtener_proyecto_usuario(b["id"]), "ana.perez")
    assert bd.es_dueno(None, None) and not bd.es_dueno(bd.listar_proyectos_usuario(buscar="sin acceso")[0], "ana.perez")
