"""Pruebas del proceso de diseño iterativo (PAT 135, tarea T16): estados de las nueve etapas, desactualización al cambiar
una etapa anterior, navegación y la franja de la interfaz con el sustituto de Streamlit del banco de pruebas."""
import sys
from pathlib import Path
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import flujo as F
from pat_sim.motor.planta import Instrumento

ESCENARIOS = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}
UI = Path(__file__).resolve().parents[2] / "04 Interfaz Streamlit"
PAGINAS = ["Desafío", "Escenario", "Diseño", "Instrumentación", "Balances", "Recuperación de calor", "Alternativas", "Layout",
           "Costeo", "Economía", "Riesgo económico", "Operación"]


def _sesion(rubro="tomate", resolver=True):
    pl = ESCENARIOS[rubro].crear()
    if resolver:
        pl.resolver()
    else:
        pl.resuelta = False
    return dict(pl=pl, economia=dict(inversion=0.0, tasa=0.1))


def pl_tiene_instrumentos(rubro):
    return bool(ESCENARIOS[rubro].crear().instrumentos)


def _completa(rubro="tomate"):
    s = _sesion(rubro)
    s["desafio"] = dict(titulo="Pasta", rubro=rubro, demanda=[10, 12], precios=[])
    s["seleccion"] = dict(equipos={"E1": 2}, redundancias=[])
    s["redundancias"] = ["E1"]
    s["costeo"] = dict(total_clp=1000.0)
    s["mce_resultado"] = ("llave", object())
    s["layout"] = dict(posiciones={"E1": (0, 0)}, dims={}, overrides={}, longitudes_m={})
    s["pl"].instrumentos.append(Instrumento("TIC", "101", next(iter(s["pl"].equipos))))
    return s


def test_nueve_etapas_en_orden():
    assert F.NUMEROS == tuple(range(1, 10))
    assert [e.corto for e in F.ETAPAS][0] == "Desafío" and F.etapa(9).paginas == ("Layout",)
    assert F.etapa(3).paginas == F.etapa(4).paginas == ("Selección de equipos",)


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_estados_sesion_inicial(rubro):
    e = F.estados(_sesion(rubro))
    assert e[2] == e[5] == F.HECHA
    assert e[6] == (F.HECHA if pl_tiene_instrumentos(rubro) else F.PENDIENTE)
    assert e[1] == e[3] == e[4] == e[7] == e[8] == e[9] == F.PENDIENTE


def test_planta_sin_resolver_deja_pendientes():
    e = F.estados(_sesion(resolver=False))
    assert e[2] == e[5] == F.PENDIENTE


def test_todas_hechas():
    s = _completa()
    F.sincronizar(s)
    assert set(F.estados(s).values()) == {F.HECHA}


def test_seleccion_por_unidades_en_equipos():
    s = _sesion()
    eq = next(iter(s["pl"].equipos.values()))
    assert not F.seleccion_aplicada(s)
    from pat_sim.motor.equipos import P
    eq.params["unidades"] = P("unidades", "Unidades en paralelo", 2)
    assert F.seleccion_aplicada(s) and F.estados(s)[3] == F.HECHA
    assert F.estados(s)[4] == F.PENDIENTE


def test_cambiar_diseno_deja_costeo_y_riesgo_por_revisar():
    s = _completa(); F.sincronizar(s)
    assert F.estados(s)[7] == F.HECHA
    eq = next(iter(s["pl"].equipos.values()))
    k = next(k for k, p in eq.params.items() if isinstance(p.valor, (int, float)) and k not in ("capacidad", "estado", "costo", "consumo_especifico"))
    eq.params[k].valor = eq.params[k].valor + 1.0
    e = F.estados(s)
    assert e[5] == F.HECHA and e[1] == F.HECHA          # la etapa cambiada y las anteriores siguen
    assert e[6] == e[7] == e[8] == e[9] == F.POR_REVISAR
    assert F.etapas_cambiadas(7, s) == [5]
    assert F.por_revisar(s) == [6, 7, 8, 9]


def test_cambiar_conexiones_afecta_desde_etapa_2():
    s = _completa(); F.sincronizar(s)
    s["pl"].conexiones.pop()
    assert 2 in F.etapas_cambiadas(5, s) and F.estados(s)[3] == F.POR_REVISAR


def test_cambiar_desafio_deja_el_resto_por_revisar():
    s = _completa(); F.sincronizar(s)
    s["desafio"] = dict(s["desafio"], demanda=[99, 100])
    e = F.estados(s)
    assert e[1] == F.HECHA and all(e[n] == F.POR_REVISAR for n in range(2, 10))


def test_volver_a_registrar_limpia_por_revisar():
    s = _completa(); F.sincronizar(s)
    s["costeo"] = dict(total_clp=2000.0)                 # cambia solo la etapa 7
    e = F.estados(s)
    assert e[7] == F.HECHA and e[8] == e[9] == F.POR_REVISAR
    F.registrar_huella(s, 8); F.registrar_huella(s, 9)
    assert F.estados(s)[8] == F.estados(s)[9] == F.HECHA


def test_huella_estable_y_sensible():
    s = _completa()
    h = [F.huella_etapa(n, s) for n in F.NUMEROS]
    assert h == [F.huella_etapa(n, _completa()) for n in F.NUMEROS]
    s["economia"]["tasa"] = 0.12
    assert F.huella_etapa(8, s) != h[7] and F.huella_etapa(9, s) == h[8]


def test_sincronizar_borra_registro_si_se_pierde_la_etapa():
    s = _completa(); F.sincronizar(s)
    assert 7 in s[F.CLAVE_REGISTRO]
    s.pop("costeo"); s.pop("layout"); F.sincronizar(s)
    e = F.estados(s)
    assert e[7] == e[9] == F.PENDIENTE and 7 not in s[F.CLAVE_REGISTRO]


def test_etapa_4_manual_solo_con_seleccion():
    s = _sesion(); s["seleccion"] = dict(equipos={})
    assert F.estados(s)[4] == F.PENDIENTE
    F.registrar_huella(s, 4)
    assert F.estados(s)[4] == F.HECHA
    s.pop("seleccion")
    assert F.estados(s)[4] == F.PENDIENTE


def test_navegacion_paginas():
    assert F.etapa_de_pagina("Costeo") == 7 and F.etapa_de_pagina("Operación") is None
    assert F.etapa_de_pagina("Selección de equipos") == 3 and F.etapa_de_pagina("Selección de equipos", 4) == 4
    assert F.etapa_de_pagina("Diseño", 4) == 2
    assert F.pagina_de_etapa(5) == "Balances" and F.pagina_de_etapa(8, PAGINAS) == "Economía"
    assert F.pagina_de_etapa(3, PAGINAS) is None


def test_etapa_vecina_salta_pantallas_inexistentes():
    assert F.etapa_vecina(2, +1, PAGINAS) == 5 and F.etapa_vecina(5, -1, PAGINAS) == 2
    assert F.etapa_vecina(2, +1) == 3 and F.etapa_vecina(1, -1) is None and F.etapa_vecina(9, +1) is None
    assert F.etapa_vecina(None, +1) is None


# ---------------------------------------------------------------- franja de la interfaz con el sustituto de Streamlit
@pytest.fixture
def ui():
    for r in (str(UI),):
        if r not in sys.path:
            sys.path.insert(0, r)
    import streamlit as st
    from ui import flujo as UF
    st.REG["error"].clear(); st.REG["exception"].clear(); st.PRESS.clear()
    st.session_state.clear()
    st.session_state.update(_completa())
    return st, UF


def test_barra_dibuja_sin_errores(ui):
    st, UF = ui
    st.session_state["pagina"] = "Costeo"
    UF.barra("Costeo", PAGINAS)
    assert not st.REG["error"] and not st.REG["exception"]
    assert F.CLAVE_REGISTRO in st.session_state


def test_barra_navega_a_la_etapa(ui):
    st, UF = ui
    st.session_state["pagina"] = "Costeo"
    st.PRESS.add("flujo_paso_9")
    lanzo = None
    try:
        UF.barra("Costeo", PAGINAS)
    except BaseException as ex:
        lanzo = type(ex).__name__
    assert lanzo == "Rerun"
    assert st.session_state["pagina"] == "Layout" and st.session_state[F.CLAVE_ETAPA] == 9


def test_barra_anterior_y_siguiente(ui):
    st, UF = ui
    st.session_state["pagina"] = "Costeo"
    st.PRESS.add("flujo_ant")
    with pytest.raises(BaseException):
        UF.barra("Costeo", PAGINAS)
    assert st.session_state["pagina"] == "Instrumentación"
    st.PRESS.clear(); st.PRESS.add("flujo_sig")
    with pytest.raises(BaseException):
        UF.barra("Instrumentación", PAGINAS)
    assert st.session_state["pagina"] == "Costeo"


def test_barra_marcar_revisada(ui):
    st, UF = ui
    UF.barra("Costeo", PAGINAS)
    st.session_state["pl"].globales["dT_min"] = 9.0       # cambia la etapa 5
    assert F.estados(st.session_state)[7] == F.POR_REVISAR
    st.PRESS.add("flujo_revisada")
    with pytest.raises(BaseException):
        UF.barra("Costeo", PAGINAS)
    assert F.estados(st.session_state)[7] == F.HECHA


def test_barra_pagina_fuera_del_proceso(ui):
    st, UF = ui
    UF.barra("Operación", PAGINAS)
    assert not st.REG["error"] and not st.REG["exception"]


def test_registrar_de_la_interfaz(ui):
    st, UF = ui
    UF.registrar(4)
    assert 4 in st.session_state[F.CLAVE_REGISTRO]
