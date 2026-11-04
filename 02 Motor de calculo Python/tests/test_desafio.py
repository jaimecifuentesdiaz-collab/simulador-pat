"""Pruebas del desafío en blanco y del mantenedor de la base (PAT 135, tarea T7.4). Cada prueba usa una base temporal."""
import copy, hashlib
import pytest
from pat_sim.datos.bd import BaseDatos
from pat_sim.datos import mantenedor as M
from pat_sim.motor import desafio as D
from pat_sim.motor.calculadoras import CEPCI_ACTUAL
from pat_sim.simbolos import iso10628


@pytest.fixture(scope="module")
def sembrada():
    # PAT 135: base en memoria sembrada una sola vez (la semilla de Agrozzi calcula la planta, cerca de 1 s)
    bd = BaseDatos(":memory:")
    m = M.Mantenedor(bd)
    return m, m.sembrar()


@pytest.fixture()
def man(tmp_path):
    return M.Mantenedor(BaseDatos(tmp_path / "man.db"))


def _desafio(**kw):
    d = dict(titulo="Prueba", enunciado="diseñar una planta de prueba", producto="Producto X", rubro="pellet", autor="Prueba",
             demanda=dict(periodo="mes", unidad="kg", valores=[1000.0, 2000.0, 3000.0], etiquetas=["a", "b", "c"], fuente="Supuesto de prueba"),
             precios=[dict(producto="Producto X", precio=5.0, moneda="US$", unidad="kg", fuente="Supuesto de prueba")])
    d.update(kw)
    return d


# ------------------------------------------------------------------ motor/desafio.py
def test_validar_desafio_correcto_y_errores():
    assert D.validar(_desafio()) == []
    malo = _desafio(titulo=" ", rubro="agar", precios=[dict(producto="", precio=-1, moneda="Peso", unidad="", fuente="")])
    malo["demanda"] = dict(periodo="quincena", unidad="litros", valores=[1.0, float("nan")], etiquetas=["x"], fuente="")
    err = D.validar(malo)
    assert any("título" in e for e in err) and any("Rubro" in e for e in err) and any("Período" in e for e in err)
    assert any("Unidad" in e for e in err) and any("mayor o igual" in e for e in err) and any("etiquetas" in e for e in err)
    assert sum(e.startswith("Precio 1") for e in err) == 5
    assert D.validar("no") == ["El desafío debe ser un diccionario"]
    assert any("total" in e for e in D.validar(_desafio(demanda=dict(periodo="día", unidad="t", valores=[0, 0], fuente="S"))))


def test_exigir_valido():
    d = _desafio()
    assert D.exigir_valido(d) is d
    with pytest.raises(ValueError):
        D.exigir_valido(_desafio(producto=""))


def test_serie_demanda_y_conversion():
    d = _desafio()
    assert D.serie_demanda(d) == [1000.0, 2000.0, 3000.0]
    assert D.serie_demanda(d, "t") == pytest.approx([1.0, 2.0, 3.0])
    assert D.serie_demanda(d, "kg") == [1000.0, 2000.0, 3000.0]
    d2 = _desafio(demanda=dict(periodo="día", unidad="m³ estéreo", valores=[5, 6], fuente="S"))
    with pytest.raises(ValueError):
        D.serie_demanda(d2, "t")


def test_horas_periodo_y_demanda_t_h():
    d = _desafio()                              # 1, 2 y 3 t por mes de 730 h
    assert D.horas_periodo(d) == 730.0
    assert D.demanda_t_h(d) == pytest.approx([1 / 730, 2 / 730, 3 / 730])
    t = _desafio(demanda=dict(periodo="temporada", unidad="t", valores=[1824.0], fuente="S"))
    with pytest.raises(ValueError):
        D.horas_periodo(t)
    assert D.demanda_t_h(t, horas_temporada=1824.0) == pytest.approx([1.0])


def test_estadisticas():
    e = D.estadisticas(_desafio())
    assert e["n"] == 3 and e["total"] == 6000.0 and e["media"] == 2000.0 and e["minimo"] == 1000.0 and e["maximo"] == 3000.0
    assert e["periodo_maximo"] == "c" and e["cv"] == pytest.approx(0.5) and e["unidad"] == "kg"


@pytest.mark.parametrize("rubro", ["tomate", "pellet", "chip", "lena", "general", "todos"])
def test_planta_vacia_por_rubro(rubro):
    pl = D.planta_vacia(_desafio(rubro=rubro))
    assert pl.equipos == {} and pl.conexiones == [] and pl.resuelta
    assert pl.rubro == ("general" if rubro == "todos" else rubro) and pl.nombre == "Desafío: Prueba"
    des = D.desafio_de_planta(pl)
    assert des["precios"][0]["precio"] == 5.0 and des["demanda"]["valores"] == [1000.0, 2000.0, 3000.0]


def test_planta_vacia_se_guarda_y_carga_con_el_desafio(tmp_path):
    bd = BaseDatos(tmp_path / "v.db"); pl = D.planta_vacia(_desafio(rubro="chip"))
    pid = bd.crear_proyecto(pl.nombre, pl.rubro); v = bd.guardar_version(pid, pl, "desafío")
    pl2 = bd.cargar_version(v["id"])
    assert pl2.rubro == "chip" and not pl2.equipos and D.desafio_de_planta(pl2)["titulo"] == "Prueba"


def test_desafio_de_planta_sin_desafio():
    from pat_sim.motor.planta import Planta
    assert D.desafio_de_planta(Planta()) is None


def test_saludo():
    assert D.saludo("Jaime  Cifuentes") == "don Jaime Cifuentes, su desafío es"
    assert D.saludo("Ana Pérez", "doña") == "doña Ana Pérez, su desafío es"
    assert D.saludo("Ana Pérez", "") == "Ana Pérez, su desafío es"
    assert D.saludo("  ") == "Su desafío es"


def test_estado_sesion():
    s = D.estado_sesion(_desafio(), "Jaime Cifuentes")
    assert s["demanda"] == [1000.0, 2000.0, 3000.0] and s["demanda_t_h"] == pytest.approx([1 / 730, 2 / 730, 3 / 730])
    assert s["unidad"] == "kg" and s["nombre"] == "Jaime Cifuentes" and s["precios"][0]["moneda"] == "US$"
    s2 = D.estado_sesion(_desafio(demanda=dict(periodo="día", unidad="unidades", valores=[3], fuente="S")))
    assert s2["demanda_t_h"] is None


# ------------------------------------------------------------------ semillas
def test_semilla_parametros_con_fuente_y_fecha():
    ps = {p["clave"]: p for p in M.semilla_parametros()}
    assert ps["cepci"]["valor"] == CEPCI_ACTUAL
    for k in ("dolar", "henry_hub", "precio_biomasa", "pmm_sen", "factor_red_sen"):
        assert k in ps, k
    assert all(p["fuente"] and p["fecha"] for p in ps.values())


def test_constantes_comun_sin_streamlit():
    c = M._constantes_comun()
    assert c["DOLAR"] > 0 and c["HENRY_HUB"] > 0 and len(c["PMM"]) == 3


def test_semilla_simbolos_y_catalogo():
    s = M.semilla_simbolos()
    iso = [x for x in s if x["norma"] == "ISO 10628"]
    assert len(iso) == len(iso10628.SIMBOLOS) and all(x["svg"] and x["fuente"] for x in iso)
    assert any(x["norma"] == "ISA-5.1" and x["svg"] for x in s) and any(x["norma"] == "ISA-5.1 primera letra" for x in s)
    from pat_sim.catalogos.registro import TIPOS
    c = M.semilla_catalogo()
    assert {e["tipo"] for e in c} == set(TIPOS)
    cal = next(e for e in c if e["tipo"] == "caldera_gas")
    assert cal["parametros"][0]["fuente"] and cal["simbolo"] == "caldera"


def test_semilla_desafios():
    a = M.desafio_agar(); g = M.desafio_agrozzi()
    assert D.validar(a) == [] and D.validar(g) == []
    assert a["rubro"] == "general" and len(a["demanda"]["valores"]) == 12 and "Supuesto" in a["demanda"]["fuente"]
    assert all("Supuesto" in p["fuente"] for p in a["precios"] + g["precios"])
    assert g["rubro"] == "tomate" and len(g["demanda"]["valores"]) == 76
    assert sum(g["demanda"]["valores"]) == pytest.approx(64500.0, rel=1e-4)      # pasta de la temporada del modelo
    assert len(M.semilla_desafios()) == 2


# ------------------------------------------------------------------ mantenedor: tablas y siembra
def test_tablas_en_la_misma_base(tmp_path):
    bd = BaseDatos(tmp_path / "x.db"); m = M.Mantenedor(bd)
    assert m.ruta == bd.ruta and m.contar() == {t: 0 for t in M.TABLAS}
    import sqlite3
    con = sqlite3.connect(bd.ruta)
    nombres = {f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert set(M.TABLAS) <= nombres and "proyectos" in nombres
    M.Mantenedor(bd)                              # abrir de nuevo no falla (CREATE TABLE IF NOT EXISTS)


def test_sembrar_idempotente_y_sin_pisar_lo_editado(sembrada):
    m, primera = sembrada
    from pat_sim.catalogos.registro import TIPOS
    assert primera["desafios"] == 2 and primera["simbolos"] > 100 and primera["catalogo_equipos"] == len(TIPOS) and primera["parametros"] >= 9
    m.guardar_parametro("cepci", 820.0, "—", "Editado por el profesor", "2026-11-04", "CEPCI")
    otra = m.sembrar()
    assert otra == dict(parametros=0, simbolos=0, catalogo_equipos=0, desafios=0)
    assert m.obtener_parametro("cepci")["valor"] == 820.0
    m.guardar_parametro("cepci", CEPCI_ACTUAL, "—", "Restaurado", "2024-03-25", "CEPCI")


def test_crud_parametros(man):
    man.guardar_parametro("dolar", "950,5", "$/US$", "Banco Central", "2026-11-04", "Dólar observado", "Oficial")
    assert man.obtener_parametro("dolar")["valor"] == 950.5
    man.guardar_parametro("dolar", 960, "$/US$", "Banco Central", "2026-11-05", "Dólar observado")
    assert [p["valor"] for p in man.listar_parametros()] == [960.0]
    with pytest.raises(ValueError):
        man.guardar_parametro("x", "abc")
    with pytest.raises(ValueError):
        man.guardar_parametro("", 1)
    man.eliminar_parametro("dolar")
    assert man.obtener_parametro("dolar") is None


def test_crud_simbolos(man):
    i = man.guardar_simbolo("ISO 10628", "secador_agar", "Secador de bandejas", "9. Secadores", "T", '<rect x="5" y="5" width="50" height="50"/>',
                            dict(caja="60 x 60"), "Supuesto")
    assert i > 0 and man.obtener_simbolo("secador_agar")["parametros"] == {"caja": "60 x 60"}
    man.guardar_simbolo("ISA-5.1", "TI", "Indicador", fuente="x")
    assert man.normas() == ["ISA-5.1", "ISO 10628"] and len(man.listar_simbolos("ISO 10628")) == 1
    with pytest.raises(ValueError):
        man.guardar_simbolo("ISO 10628", "malo", svg="<script>alert(1)</script>")
    man.eliminar_simbolo("secador_agar", "ISO 10628")
    assert man.obtener_simbolo("secador_agar") is None


def test_crud_catalogo(man):
    ps = [dict(clave="T_aire", nombre="Temperatura del aire", valor=80.0, unidad="°C", categoria="Supuesto", fuente="Supuesto", minimo="40", maximo=None),
          dict(clave="", nombre="vacía")]
    man.guardar_equipo("secador_agar", "general", "Secador de agar", "secador", ps, "Supuesto", ["general"], 9, "T")
    e = man.obtener_equipo("secador_agar")
    assert e["iso_categoria"] == 9 and e["rubros"] == ["general"] and len(e["parametros"]) == 1 and e["parametros"][0]["minimo"] == 40.0
    man.guardar_equipo("molino_pellet", "biomasa", "Molino", "molino_martillos", [], "x", ["pellet"])
    assert [x["tipo"] for x in man.listar_catalogo("pellet")] == ["molino_pellet", "secador_agar"]
    assert [x["tipo"] for x in man.listar_catalogo("chip")] == ["secador_agar"]
    with pytest.raises(ValueError):
        man.guardar_equipo(" ")
    man.eliminar_equipo("molino_pellet")
    assert man.obtener_equipo("molino_pellet") is None


def test_crud_desafios(man):
    i = man.guardar_desafio(_desafio())
    d = man.obtener_desafio(i)
    assert d["titulo"] == "Prueba" and d["activo"] and d["demanda"]["valores"] == [1000.0, 2000.0, 3000.0] and d["fecha"]
    d["enunciado"] = "diseñar otra planta"; man.guardar_desafio(d)
    assert man.obtener_desafio("Prueba")["enunciado"] == "diseñar otra planta"
    with pytest.raises(ValueError):
        man.guardar_desafio(_desafio())                       # título repetido
    with pytest.raises(ValueError):
        man.guardar_desafio(_desafio(titulo="Otro", rubro="agar"))   # no válido
    with pytest.raises(KeyError):
        man.guardar_desafio(dict(_desafio(titulo="Z"), id=999))
    j = man.guardar_desafio(_desafio(titulo="Segundo", activo=False))
    assert [x["id"] for x in man.listar_desafios(solo_activos=True)] == [i]
    man.activar_desafio(j, True); man.activar_desafio(i, False)
    assert [x["id"] for x in man.listar_desafios(solo_activos=True)] == [j] and len(man.listar_desafios()) == 2
    man.eliminar_desafio(j)
    assert man.obtener_desafio(j) is None


def test_usuarios_con_rol(man):
    man.guardar_usuario("Carlos.Torres@utalca.cl", "profesor", "clave-segura")
    assert man.rol_de("carlos.torres@utalca.cl", "clave-segura") == "profesor"
    assert man.rol_de("carlos.torres@utalca.cl", "otra") is None and man.rol_de("nadie", "x") is None
    man.guardar_usuario("carlos.torres@utalca.cl", "profesor")                 # sin clave: conserva la anterior
    assert man.rol_de("carlos.torres@utalca.cl", "clave-segura") == "profesor"
    assert man.listar_usuarios()[0]["con_clave"] and "clave" not in str(man.listar_usuarios()[0].get("clave_hash", ""))
    with pytest.raises(ValueError):
        man.guardar_usuario("x", "rector")


# ------------------------------------------------------------------ funciones de módulo
def test_mantenedor_y_sembrar_de_modulo(tmp_path):
    bd = BaseDatos(tmp_path / "m.db")
    assert M.mantenedor(bd) is M.mantenedor(bd)
    m = M.mantenedor(bd)
    assert M.mantenedor(m) is m
    r = M.sembrar(bd, desafios=False)
    from pat_sim.catalogos.registro import TIPOS
    assert r["desafios"] == 0 and r["catalogo_equipos"] == len(TIPOS) and m.contar()["desafios"] == 0


def test_obtener_desde_la_base_y_con_respaldo(sembrada, tmp_path):
    m, _ = sembrada
    m.guardar_parametro("dolar", 1000.0, "$/US$", "Editado", "2026-11-04", "Dólar")
    assert M.obtener("parametro", "dolar", bd=m) == 1000.0
    assert M.obtener("parametro", "dolar", bd=m, fila=True)["fuente"] == "Editado"
    malo = tmp_path / "no_es_base.db"; malo.write_bytes(b"esto no es una base SQLite" * 100)
    assert M.obtener("parametro", "cepci", bd=str(malo)) == CEPCI_ACTUAL               # la base falla: semilla
    vacia = BaseDatos(tmp_path / "vacia.db")
    assert M.obtener("simbolo", "bomba", bd=vacia)["svg"] == iso10628.SIMBOLOS["bomba"][3]   # sin la fila: semilla
    assert M.obtener("equipo", "caldera_gas", bd=vacia)["nombre"] == "Caldera a gas natural"
    assert M.obtener("desafio", "Secado de agar agar (desafío en blanco)", bd=vacia)["rubro"] == "general"
    assert M.obtener("desafio", 12345, bd=vacia, defecto="nada") == "nada"
    assert M.obtener("parametro", "no_existe", bd=vacia, defecto=7.0) == 7.0
    with pytest.raises(ValueError):
        M.obtener("color", "x", bd=vacia)
    m.guardar_parametro("dolar", 990.35, "$/US$", "Restaurado", "2026-10-26", "Dólar")


def test_parametro_atajo(sembrada):
    m, _ = sembrada
    assert M.parametro("cepci", bd=m) == pytest.approx(CEPCI_ACTUAL)
    assert M.parametro("inexistente", 3.5, bd=m) == 3.5


def test_svg_equipo_desde_la_base(sembrada):
    m, _ = sembrada
    m.guardar_simbolo("ISO 10628", "bomba", "Bomba editada", "14. Bombas de líquido", "P", '<circle cx="30" cy="30" r="9"/>', {}, "Profesor")
    g = M.svg_equipo("bomba", 10, 20, 30, bd=m)
    assert 'r="9"' in g and "translate(10,20) scale(0.5,0.5)" in g and "Bomba editada" in g
    assert "Equipo o máquina, general" in M.svg_equipo("no_existe_en_ninguna", bd=m)
    nombre, cat, letra, dib = iso10628.SIMBOLOS["bomba"]
    m.guardar_simbolo("ISO 10628", "bomba", nombre, f"{cat}. Bombas de líquido", letra, dib, {}, "Restaurado")


def test_defectos_y_aplicar_defectos(sembrada):
    m, _ = sembrada
    from pat_sim.catalogos.servicios import CalderaGas
    assert M.defectos_equipo("caldera_gas", bd=m)["eta_pci"] == 0.85
    e = m.obtener_equipo("caldera_gas")
    e["parametros"] = [dict(p, valor=0.9, fuente="Profesor, 04-11-2026") if p["clave"] == "eta_pci" else p for p in e["parametros"]]
    m.guardar_equipo(**{k: e[k] for k in ("tipo", "rubro", "nombre", "simbolo", "parametros", "fuente", "rubros", "iso_categoria", "iso_letra")})
    eq = CalderaGas("D9", "Caldera")
    assert M.aplicar_defectos(eq, bd=m) == 1 and eq.v("eta_pci") == 0.9 and "Profesor" in eq.params["eta_pci"].fuente
    assert M.aplicar_defectos(eq, bd=m) == 0
    e["parametros"] = [dict(p, valor=0.85) if p["clave"] == "eta_pci" else p for p in e["parametros"]]
    m.guardar_equipo(**{k: e[k] for k in ("tipo", "rubro", "nombre", "simbolo", "parametros", "fuente", "rubros", "iso_categoria", "iso_letra")})


def test_desafios_sembrados_parten_en_blanco(sembrada):
    m, _ = sembrada
    for d in m.listar_desafios(solo_activos=True):
        pl = D.planta_vacia(d)
        assert pl.resuelta and not pl.equipos and D.serie_demanda(d)
    g = m.obtener_desafio("Planta basada en Agrozzi: pasta de tomate")
    assert D.planta_vacia(g).rubro == "tomate" and D.estadisticas(g)["periodo_maximo"].startswith("Día")


# ------------------------------------------------------------------ clave del profesor
def test_hash_sha256_y_clave_por_defecto():
    assert M.hash_sha256("torres2026") == hashlib.sha256(b"torres2026").hexdigest() == M.HASH_CLAVE_DEFECTO


def test_hash_esperado_orden_de_prioridad():
    h = M.hash_sha256("otra")
    assert M.hash_esperado({"PROFESOR_CLAVE_SHA256": h.upper()}, {}) == (h, "secrets")
    assert M.hash_esperado({"PROFESOR_CLAVE_SHA256": ""}, {"PROFESOR_CLAVE_SHA256": h}) == (h, "entorno")
    assert M.hash_esperado(None, {}) == (M.HASH_CLAVE_DEFECTO, "defecto")

    class SinArchivo:                      # como st.secrets cuando no hay secrets.toml
        def get(self, k):
            raise FileNotFoundError("sin secrets.toml")
    assert M.hash_esperado(SinArchivo(), {}) == (M.HASH_CLAVE_DEFECTO, "defecto")


def test_verificar_profesor():
    assert M.verificar_profesor("torres2026") and not M.verificar_profesor("Torres2026") and not M.verificar_profesor("")
    assert M.verificar_profesor("otra", M.hash_sha256("otra")) and not M.verificar_profesor("torres2026", M.hash_sha256("otra"))
