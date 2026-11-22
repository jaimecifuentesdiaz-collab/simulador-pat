"""PAT 144 b (tarea T8, 20-11-2026): ingreso a la nube y proyectos en Supabase con el probador de Streamlit, sin red (cliente
falso de 02 Motor de calculo Python/tests/nube_falsa.py). Sin claves todo sigue en modo local; con claves, ingreso con usuario
corto, rol visible en la barra lateral, guardado y apertura desde la nube, rechazo del guardado con una versión vieja, la visita
de solo lectura, la pestaña Docente con el rol de la nube y la asignación publicada que ve el estudiante. La contraseña no queda en
la sesión. Desde 04 Interfaz Streamlit: python -m pytest -q tests/test_nube_app.py

PAT 146 (22-11-2026): con la nube configurada el ingreso es obligatorio en una pantalla propia (ui/acceso.pantalla_ingreso_nube):
sin sesión no hay barra lateral, índice ni pantallas, tampoco con ?p=; la barra lateral ya no tiene el desplegable de ingreso y
«Salir» limpia la sesión y vuelve a la pantalla de ingreso."""
import shutil, sqlite3, sys
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parents[2]
for p in (RAIZ / "02 Motor de calculo Python", RAIZ / "02 Motor de calculo Python" / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
from nube_falsa import ServidorFalso            # noqa: E402
from pat_sim.datos import nube as N             # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app.py")
BD_ORIGEN = RAIZ / "03 Base de datos" / "simulador_pat.db"
CLAVE = "Clave-de-prueba-123"


@pytest.fixture()
def base(tmp_path, monkeypatch):
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    with sqlite3.connect(bd) as con:
        if con.execute("SELECT name FROM sqlite_master WHERE name = 'proyectos_usuario_autoguardado'").fetchone():
            con.execute("DELETE FROM proyectos_usuario_autoguardado")
        con.execute("DELETE FROM proyectos_usuario_versiones"); con.execute("DELETE FROM proyectos_usuario")
    monkeypatch.setenv("PAT_SIM_DB", str(bd)); monkeypatch.setenv("PAT_INICIO", "blanco")
    monkeypatch.delenv("PAT_TODAS_LAS_PAGINAS", raising=False)
    for k in ("PAT_ACCESO", "PAT_USUARIOS", "PAT_AUTOGUARDADO", "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_DOMINIO"):
        monkeypatch.delenv(k, raising=False)
    import streamlit as st
    st.cache_resource.clear()
    yield bd
    st.cache_resource.clear()


@pytest.fixture()
def nube(base, monkeypatch):
    s = ServidorFalso()
    s.crear_cuenta("docente01@pat-sim.cl", CLAVE, "docente", "Docente uno")
    s.crear_cuenta("usuario01@pat-sim.cl", CLAVE, "estudiante", "Ana Pérez")
    s.crear_cuenta("visita01@pat-sim.cl", CLAVE, "visita")
    monkeypatch.setattr(N, "FABRICA", lambda url, key: s.cliente(url, key))
    monkeypatch.setenv("SUPABASE_URL", "https://falso.supabase.co"); monkeypatch.setenv("SUPABASE_KEY", "sb_publishable_falsa")
    return s


def _n(bd, tabla):
    with sqlite3.connect(bd) as con:
        return con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]


def _abrir(pagina="Proyectos"):
    at = AppTest.from_file(APP, default_timeout=240)
    at.query_params["p"] = pagina
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _lateral(at):
    return [c.value for c in at.sidebar.caption]


def _ingresar(at, usuario, clave=CLAVE):
    # PAT 146: el ingreso es en la pantalla de ingreso (área principal), no en la barra lateral
    at.text_input(key="ing_usuario").input(usuario)
    next(t for t in at.text_input if t.label == "Contraseña").input(clave)
    next(b for b in at.button if b.label == "Ingresar").click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def _en_ingreso(at):
    """PAT 146: la página muestra solo la pantalla de ingreso: sin barra lateral, sin índice de pantallas y sin la barra de etapas."""
    assert [t.value for t in at.title] == ["Simulador PAT"]
    assert any(m.value == "Simulador de diseño de plantas de proceso y recuperación de calor" for m in at.markdown)
    assert any(t.key == "ing_usuario" for t in at.text_input)
    assert len(at.sidebar.children) == 0 and not at.radio            # ni barra lateral ni índice
    assert not any(b.key in ("pry_guardar_lateral", "partida_continuar", "nube_salir") for b in at.button)
    assert "pl" not in at.session_state and "pagina" not in at.session_state   # no se construyó la aplicación
    assert any("Las cuentas las crea el administrador" in c.value for c in at.caption)
    return True


def test_sin_claves_sigue_en_modo_local(base):
    at = _abrir()
    assert any(c.startswith(":gray[Modo local]") for c in _lateral(at))
    assert not any(e.label == "Ingresar a la nube" for e in at.sidebar.expander)
    at.sidebar.button(key="pry_guardar_lateral").click(); at.run()       # el guardado sigue en la base local
    assert not at.exception and _n(base, "proyectos_usuario_versiones") == 1
    assert "usuario_nube" not in at.session_state


def test_ingreso_guarda_y_abre_desde_la_nube(nube, base):
    at = _abrir()
    assert _en_ingreso(at)
    _ingresar(at, "usuario01")
    assert any("Nube: **usuario01**, rol estudiante" in c for c in _lateral(at))
    assert at.sidebar.button(key="nube_salir").label == "Salir"
    assert not any(e.label == "Ingresar a la nube" for e in at.sidebar.expander + at.expander)   # PAT 146: sin desplegable
    assert at.sidebar.radio and not any(t.key in ("ing_usuario", "nube_usuario") for t in at.text_input)
    assert CLAVE not in repr({k: at.session_state[k] for k in at.session_state if k != "_nube_sesion"})
    assert at.session_state["persona_nombre"] == "Ana Pérez"              # el nombre de la cuenta es la persona del nombre automático
    at.session_state["persona_nombre"] = "Ana María"; at.run()          # el primer cambio: guardado automático en la nube
    assert len(nube.proyectos) == 1 and _n(base, "proyectos_usuario") == 0
    p = next(iter(nube.proyectos.values()))
    assert p["version"] == 0 and p["autoguardado"] and p["nombre"] == "Proyecto de Ana María 1"
    at.sidebar.button(key="pry_guardar_lateral").click(); at.run()
    assert not at.exception and p["version"] == 1 and len(nube.versiones) == 1 and _n(base, "proyectos_usuario_versiones") == 0
    assert any("Guardado «Proyecto de Ana María 1»" in s.value for s in at.sidebar.success)
    textos = [c.value for c in at.caption]
    assert any("Los proyectos de esta cuenta quedan en la nube" in t for t in textos)
    assert any("Se ven sus proyectos y los ejemplos" in t for t in textos)
    # otra sesión de la misma cuenta guarda la versión 2: esta sesión, que conoce la 1, no la pisa
    otra = N.SesionNube.ingresar("usuario01", CLAVE, secretos=dict(SUPABASE_URL="https://falso.supabase.co",
                                                                     SUPABASE_KEY="sb_publishable_falsa"))
    otra.rpc("guardar_proyecto", dict(p_id=p["id"], p_nombre="", p_datos=p["datos"], p_resumen={}, p_persona="", p_nota="otra",
                                      p_version_esperada=1))
    at.sidebar.button(key="pry_guardar_lateral").click(); at.run()
    assert not at.exception and p["version"] == 2
    assert any("otra sesión guardó la versión 2" in e.value for e in at.sidebar.error)
    # sesión nueva del navegador: ingresa y ofrece continuar con la partida guardada en la nube
    at2 = _abrir("Desafío")
    assert _en_ingreso(at2)                                                 # PAT 146: sin sesión solo la pantalla de ingreso
    _ingresar(at2, "usuario01@pat-sim.cl")
    assert any(b.key == "partida_continuar" for b in at2.button)
    at2.button(key="partida_continuar").click(); at2.run()
    assert not at2.exception and at2.session_state["persona_nombre"] == "Ana María"
    # PAT 146: salir vuelve a la pantalla de ingreso con la sesión limpia
    at2.sidebar.button(key="nube_salir").click(); at2.run()
    assert not at2.exception and "usuario_nube" not in at2.session_state and "proyecto_abierto" not in at2.session_state
    assert _en_ingreso(at2) and "persona_nombre" not in at2.session_state


def test_contrasena_incorrecta(nube):
    at = _abrir()
    _ingresar(at, "usuario01", "otra")
    assert "usuario_nube" not in at.session_state
    assert any("Usuario o contraseña incorrectos" in e.value for e in at.error)   # PAT 146: error en la pantalla de ingreso
    assert _en_ingreso(at)
    assert "otra" not in repr({k: at.session_state[k] for k in at.session_state})


def test_sin_red_avisa_y_sigue_en_ingreso(nube, base):
    # PAT 146: con claves y sin red no se abre la aplicación: el error lo dice y la página no se cae
    nube.sin_red = True
    at = _abrir()
    _ingresar(at, "usuario01")
    assert "usuario_nube" not in at.session_state
    err = [e.value for e in at.error]
    assert any("No hay conexión con la nube" in e for e in err) and not any("modo local" in e for e in err)
    assert _en_ingreso(at)
    nube.sin_red = False                                                    # vuelve la red: el mismo ingreso funciona
    _ingresar(at, "usuario01")
    assert any("Nube: **usuario01**, rol estudiante" in c for c in _lateral(at))


def test_visita_solo_lectura(nube):
    at = _abrir()
    assert _en_ingreso(at)                                                  # PAT 146: la visita también pasa por el ingreso
    _ingresar(at, "visita01")
    assert any("Nube: **visita01**, rol" in c for c in _lateral(at))
    assert at.sidebar.button(key="pry_guardar_lateral").disabled
    assert any("La cuenta de visita es de solo lectura" in i.value for i in at.info)
    at.session_state["persona_nombre"] = "Visita"; at.run()
    assert not at.exception and nube.proyectos == {}                       # no se guarda sola
    assert not any(f.key == "pys_partida_subir" for f in at.get("file_uploader"))


def test_docente_con_rol_de_la_nube_y_asignacion_del_estudiante(nube):
    at = _abrir("Docente")
    _ingresar(at, "docente01")
    assert not any(t.key == "doc_clave" for t in at.text_input)            # sin clave local: manda el rol de la nube
    assert any(e.label == "Cuentas de la nube y sus roles" for e in at.expander)
    v = next(p for p in nube.perfiles.values() if p["usuario"] == "visita01")
    at.selectbox(key="doc_nube_cuenta").set_value(v["id"]); at.run()
    at.selectbox(key=f"doc_nube_rol_{v['id']}").set_value("estudiante"); at.run()
    at.button(key="doc_nube_asignar").click(); at.run()
    assert not at.exception and v["rol"] == "estudiante"
    assert not any(o == next(p for p in nube.perfiles.values() if p["usuario"] == "docente01")["id"]
                   for o in at.selectbox(key="doc_nube_cuenta").options)   # el docente no se ofrece a sí mismo
    # el docente publica una asignación (como la de la base local) y el estudiante la ve sin escribir su usuario
    est = next(p for p in nube.perfiles.values() if p["usuario"] == "usuario01")
    from pat_sim.datos import genericos as GE
    from ui import comun as C
    g = GE.genericos(C.obtener_bd())
    cid = g.crear_curso("PAT nube", None, "2026-2")
    g.cargar_estudiantes(cid, "usuario01;Ana Pérez")
    g.asignar_al_azar(cid, 7, 1, True, "docente01", familia="tomate")
    at.run()
    if at.selectbox(key="doc_curso").value != "PAT nube":
        at.selectbox(key="doc_curso").set_value("PAT nube"); at.run()
    at.button(key="doc_nube_publicar").click(); at.run()
    assert not at.exception and est["id"] in nube.asignaciones
    assert any("Publicadas 1 asignaciones" in s.value for s in at.success)
    at2 = _abrir("Docente")
    _ingresar(at2, "usuario01")
    assert any("Esta pestaña es solo para las cuentas con el rol docente" in i.value for i in at2.info)
    assert at2.session_state["asignacion_docente"]["familia"] == "tomate"
    assert at2.session_state["asignacion_docente"]["usuario"] == "usuario01"


# ---------------------------------------------------------------- PAT 146: pantalla de ingreso obligatoria con la nube
def test_sin_claves_no_hay_pantalla_de_ingreso(base):
    at = _abrir("Costeo")
    assert not any(t.key == "ing_usuario" for t in at.text_input)
    assert at.sidebar.radio and at.session_state["pagina"] == "Costeo"
    assert any(c.startswith(":gray[Modo local]") for c in _lateral(at))
    assert not any(b.key == "nube_salir" for b in at.sidebar.button)


@pytest.mark.parametrize("pagina", ["Costeo", "Docente", "Proyectos", "Lazos de control", "Instrumentación", "no existe"])
def test_con_claves_ninguna_pantalla_antes_de_ingresar(nube, pagina):
    at = _abrir(pagina)
    assert _en_ingreso(at)


def test_ingreso_abre_la_pantalla_pedida_y_salir_limpia(nube):
    at = _abrir("Costeo")
    _ingresar(at, "usuario01")
    assert at.session_state["pagina"] == "Costeo" and "pl" in at.session_state
    assert not any(e.label == "Ingresar a la nube" for e in at.sidebar.expander)
    at.sidebar.button(key="nube_salir").click(); at.run()
    assert not at.exception and _en_ingreso(at)
    assert not any(k in at.session_state for k in ("pl", "pagina", "usuario_nube", "_nube_sesion", "persona_nombre"))
    _ingresar(at, "docente01")                                              # otra cuenta en la misma pestaña
    assert any("Nube: **docente01**, rol docente" in c for c in _lateral(at))


def test_clave_secreta_sigue_en_modo_local(base, monkeypatch):
    # sin nube utilizable (clave secreta rechazada o URL inválida) no hay pantalla de ingreso: todo como en modo local
    monkeypatch.setenv("SUPABASE_URL", "https://falso.supabase.co"); monkeypatch.setenv("SUPABASE_KEY", "sb_secret_no_se_usa")
    at = _abrir("Costeo")
    assert not any(t.key == "ing_usuario" for t in at.text_input) and at.sidebar.radio
    assert any(c.startswith(":gray[Modo local]") for c in _lateral(at))
    monkeypatch.setenv("SUPABASE_URL", "no es una dirección"); monkeypatch.setenv("SUPABASE_KEY", "sb_publishable_falsa")
    at = _abrir("Costeo")
    assert not any(t.key == "ing_usuario" for t in at.text_input) and at.sidebar.radio


def test_acceso_t25_sin_nube_sigue_igual(base, monkeypatch):
    # PAT_ACCESO=usuarios sin nube: el ingreso T25 de siempre (Nombre de usuario, Clave, «Entrar»)
    monkeypatch.setenv("PAT_ACCESO", "usuarios"); monkeypatch.setenv("PAT_USUARIOS", "est01;estudiante;clave-est-01;Ana")
    at = _abrir("Costeo")
    assert any(t.key == "acc_usuario" for t in at.text_input) and not any(t.key == "ing_usuario" for t in at.text_input)
    at.text_input(key="acc_usuario").input("est01"); at.text_input(key="acc_clave").input("clave-est-01")
    next(b for b in at.button if b.label == "Entrar").click(); at.run()
    assert not at.exception and at.session_state["usuario_acceso"]["usuario"] == "est01"
    assert any("Sesión: est01 (estudiante)" in c for c in _lateral(at))
