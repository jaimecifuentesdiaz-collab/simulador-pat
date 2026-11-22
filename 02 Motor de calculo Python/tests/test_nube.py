"""PAT 144 b (tarea T8, 20-11-2026): conexión opcional a Supabase (pat_sim/datos/nube.py) con un cliente falso, sin red.
Sin claves o sin el paquete queda en modo local; la clave secreta se rechaza; ingreso con usuario corto; proyectos que van y
vuelven con la planta basada en Agrozzi; control de versión que rechaza el guardado de una sesión con una versión vieja; reglas de
cada rol (estudiante, docente, visita); guardado automático sin versiones; token vencido; la contraseña nunca queda guardada."""
import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from nube_falsa import ServidorFalso
from pat_sim.datos import nube as N
from pat_sim.datos.bd import NombreRepetido
from pat_sim.escenarios import agrozzi

SECRETOS = dict(SUPABASE_URL="https://falso.supabase.co", SUPABASE_KEY="sb_publishable_falsa", SUPABASE_DOMINIO="pat-sim.cl")
CLAVE = "Clave-de-prueba-123"


@pytest.fixture()
def servidor(monkeypatch):
    s = ServidorFalso()
    monkeypatch.setattr(N, "FABRICA", lambda url, key: s.cliente(url, key))
    for k in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_DOMINIO"):
        monkeypatch.delenv(k, raising=False)
    s.crear_cuenta("docente01@pat-sim.cl", CLAVE, "docente", "Docente uno")
    s.crear_cuenta("usuario01@pat-sim.cl", CLAVE, "estudiante", "Ana Pérez")
    s.crear_cuenta("usuario02@pat-sim.cl", CLAVE, "estudiante", "Benito Soto")
    s.crear_cuenta("visita01@pat-sim.cl", CLAVE, "visita")
    return s


@pytest.fixture(scope="module")
def agro():
    return agrozzi.crear()


def _entrar(usuario):
    return N.SesionNube.ingresar(usuario, CLAVE, secretos=SECRETOS)


def _estado():
    return dict(persona_nombre="Ana Pérez", cop=2.0, economia=dict(precio_gas=2.77, dolar=990.35, inversion=0.0))


# ---------------------------------------------------------------- configuración y modo local
def test_sin_claves_queda_en_modo_local(monkeypatch):
    for k in ("SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.delenv(k, raising=False)
    e = N.estado(secretos={})
    assert e["disponible"] is False and e["motivo"] == "sin_claves" and e["aviso"].startswith("Modo local")
    assert N.configuracion(secretos={}) is None
    with pytest.raises(N.ErrorNube):
        N.SesionNube.ingresar("usuario01", CLAVE, secretos={})


def test_variables_de_entorno_sirven_igual_que_los_secretos(monkeypatch, servidor):
    monkeypatch.setenv("SUPABASE_URL", "https://falso.supabase.co"); monkeypatch.setenv("SUPABASE_KEY", "sb_publishable_falsa")
    assert N.estado(secretos={})["disponible"] is True
    assert N.configuracion(secretos={})["dominio"] == N.DOMINIO_DEFECTO


def test_clave_secreta_no_se_usa(servidor):
    import base64
    carga = base64.urlsafe_b64encode(json.dumps({"role": "service_role"}).encode()).decode().rstrip("=")
    for clave in ("sb_secret_abc", f"xx.{carga}.yy"):
        e = N.estado(secretos=dict(SECRETOS, SUPABASE_KEY=clave))
        assert e["motivo"] == "clave_secreta" and not e["disponible"]
    anon = base64.urlsafe_b64encode(json.dumps({"role": "anon"}).encode()).decode().rstrip("=")
    assert not N.clave_es_secreta(f"xx.{anon}.yy") and not N.clave_es_secreta("sb_publishable_x")


def test_url_invalida_y_sin_paquete(monkeypatch):
    assert N.estado(secretos=dict(SECRETOS, SUPABASE_URL="http://inseguro"))["motivo"] == "url_invalida"
    monkeypatch.setattr(N, "FABRICA", None)
    monkeypatch.setitem(sys.modules, "supabase", None)          # «import supabase» falla como si no estuviera instalado
    e = N.estado(secretos=SECRETOS)
    assert e["motivo"] == "sin_paquete" and "supabase" in e["aviso"]


def test_usuario_corto_y_correo():
    assert N.correo_de("usuario01", "pat-sim.cl") == "usuario01@pat-sim.cl"
    assert N.correo_de(" Usuario01 ", "@pat-sim.cl") == "usuario01@pat-sim.cl"
    assert N.correo_de("ana@utalca.cl", "pat-sim.cl") == "ana@utalca.cl"
    assert N.correo_de("", "pat-sim.cl") == ""


def test_fecha_en_hora_de_chile():
    f = N.fecha_local("2026-11-20T19:39:05.12345+00:00")
    assert f in ("2026-11-20T16:39:05", "2026-11-20T19:39:05")    # sin datos de zonas horarias queda en UTC
    assert N.fecha_local(None) is None


# ---------------------------------------------------------------- ingreso
def test_ingreso_con_usuario_corto_trae_el_rol(servidor):
    s = _entrar("usuario01")
    assert s.rol == "estudiante" and s.usuario == "usuario01" and s.puede_editar() and not s.es_docente()
    assert _entrar("docente01@pat-sim.cl").rol == "docente"
    v = _entrar("visita01")
    assert v.rol == "visita" and not v.puede_editar()


def test_contrasena_incorrecta_y_sin_red(servidor):
    with pytest.raises(N.CredencialesInvalidas):
        N.SesionNube.ingresar("usuario01", "otra", secretos=SECRETOS)
    with pytest.raises(N.CredencialesInvalidas):
        N.SesionNube.ingresar("usuario01", "", secretos=SECRETOS)
    servidor.sin_red = True
    with pytest.raises(N.SinConexion):
        _entrar("usuario01")


def test_la_contrasena_no_queda_guardada(servidor):
    s = _entrar("usuario01")
    vistos = json.dumps(s.datos_sesion()) + repr(vars(s)) + repr(s.perfil) + repr(servidor.llamadas)
    assert CLAVE not in vistos
    assert "token" not in json.dumps(s.datos_sesion())


def test_cerrar_sesion(servidor):
    s = _entrar("usuario01"); c = s.cliente
    s.cerrar()
    assert c.uid is None


# ---------------------------------------------------------------- proyectos
def test_guardar_listar_y_cargar_la_planta_basada_en_agrozzi(servidor, agro):
    a = _entrar("usuario01").almacen()
    r0 = agrozzi.resumen(agro)
    g = a.guardar_proyecto_usuario(agro, estado=_estado(), resumen={"equipos": len(agro.equipos)}, persona="Ana Pérez", nota="primera")
    assert g["nuevo"] and g["version"] == 1 and g["nombre"] == "Proyecto de Ana Pérez 1"
    filas = a.listar_proyectos_usuario()
    assert [f["nombre"] for f in filas] == ["Proyecto de Ana Pérez 1"] and filas[0]["usuario"] == "usuario01"
    d = a.cargar_proyecto_usuario(g["id"])
    assert d["version"] == 1 and d["estado"]["persona_nombre"] == "Ana Pérez" and list(d["planta"].equipos) == list(agro.equipos)
    r1 = agrozzi.resumen(d["planta"])
    for k in ("Qhb", "cascada", "pinch"):
        assert float(r1[k]) == pytest.approx(float(r0[k]), rel=1e-9)
    assert round(float(r1["cascada"]), 1) == 9073.8 and round(float(r1["pinch"]), 1) == 9722.9
    assert a.nombre_sugerido("Ana Pérez") == "Proyecto de Ana Pérez 2"
    v = a.listar_versiones_usuario(g["id"])
    assert [x["numero"] for x in v] == [1] and v[0]["nota"] == "primera"


def test_conflicto_de_version_entre_dos_sesiones(servidor, agro):
    a1 = _entrar("usuario01").almacen(); a2 = _entrar("usuario01").almacen()
    g = a1.guardar_proyecto_usuario(agro, nombre="Planta compartida", estado=_estado())
    a2.cargar_proyecto_usuario(g["id"])
    a1.guardar_proyecto_usuario(agro, estado=_estado(), proyecto_id=g["id"], nota="sesión uno")          # versión 2
    with pytest.raises(N.ConflictoVersion) as e:
        a2.guardar_proyecto_usuario(agro, estado=_estado(), proyecto_id=g["id"], nota="sesión dos")
    assert e.value.version_nube == 2 and e.value.version_sesion == 1 and "Planta compartida" in str(e.value)
    assert len(a1.listar_versiones_usuario(g["id"])) == 2                     # no se pisó nada
    a2.cargar_proyecto_usuario(g["id"])                                       # al volver a cargar, guarda sobre la 2
    assert a2.guardar_proyecto_usuario(agro, estado=_estado(), proyecto_id=g["id"])["version"] == 3
    assert a2.guardar_proyecto_usuario(agro, nombre="Planta de la sesión dos", estado=_estado())["nuevo"]


def test_nombre_repetido_y_sobrescribir(servidor, agro):
    a = _entrar("usuario01").almacen()
    a.guardar_proyecto_usuario(agro, nombre="Mi planta", estado=_estado())
    with pytest.raises(NombreRepetido) as e:
        a.guardar_proyecto_usuario(agro, nombre="mi planta", estado=_estado())
    assert e.value.sugerido
    g = a.guardar_proyecto_usuario(agro, nombre="Mi planta", estado=_estado(), sobrescribir=True)
    assert not g["nuevo"] and g["version"] == 2
    b = _entrar("usuario02").almacen()                                        # el mismo nombre en otra cuenta no choca
    assert b.guardar_proyecto_usuario(agro, nombre="Mi planta", estado=_estado())["nuevo"]


def test_renombrar_y_eliminar(servidor, agro):
    a = _entrar("usuario01").almacen()
    g1 = a.guardar_proyecto_usuario(agro, nombre="Uno", estado=_estado())
    a.guardar_proyecto_usuario(agro, nombre="Dos", estado=_estado())
    assert a.renombrar_proyecto_usuario(g1["id"], "Uno bis") == "Uno bis"
    with pytest.raises(NombreRepetido):
        a.renombrar_proyecto_usuario(g1["id"], "Dos")
    a.eliminar_proyecto_usuario(g1["id"])
    assert [f["nombre"] for f in a.listar_proyectos_usuario()] == ["Dos"]


def test_cada_rol_ve_y_cambia_lo_suyo(servidor, agro):
    e1 = _entrar("usuario01").almacen(); e2 = _entrar("usuario02").almacen()
    doc = _entrar("docente01").almacen(); vis = _entrar("visita01").almacen()
    g = e1.guardar_proyecto_usuario(agro, nombre="De Ana", estado=_estado())
    assert e2.listar_proyectos_usuario() == [] and e2.obtener_proyecto_usuario(g["id"]) is None
    with pytest.raises(N.SinPermiso):                                         # el servidor rechaza aunque la pantalla lo intente
        e2.s.rpc("guardar_proyecto", dict(p_id=g["id"], p_nombre="", p_datos={}, p_resumen={}, p_persona="", p_nota="",
                                          p_version_esperada=1))
    vistos = doc.listar_proyectos_usuario()
    assert [f["nombre"] for f in vistos] == ["De Ana"] and vistos[0]["usuario"] == "usuario01" and not vistos[0]["propio"]
    assert doc.cargar_proyecto_usuario(g["id"])["version"] == 1               # el docente lo abre
    with pytest.raises(N.SinPermiso):                                         # pero no lo sobrescribe
        doc.guardar_proyecto_usuario(agro, estado=_estado(), proyecto_id=g["id"])
    with pytest.raises(N.SinPermiso):
        doc.renombrar_proyecto_usuario(g["id"], "Cambiado por el docente")
    assert vis.listar_proyectos_usuario() == [] and vis.solo_lectura
    with pytest.raises(N.SinPermiso):
        vis.guardar_proyecto_usuario(agro, nombre="De la visita", estado=_estado())
    with pytest.raises(N.SinPermiso):
        vis.autoguardar_proyecto_usuario(agro, estado=_estado())
    doc.marcar_ejemplo(g["id"], True)
    vis._invalidar(); e2._invalidar()
    assert [f["nombre"] for f in vis.listar_proyectos_usuario()] == ["De Ana"]
    assert vis.cargar_proyecto_usuario(g["id"])["planta"].equipos             # la visita abre el ejemplo
    assert [f["nombre"] for f in e2.listar_proyectos_usuario(usuario="usuario02")] == ["De Ana"]   # los ejemplos se ven igual
    with pytest.raises(N.SinPermiso):
        e1.marcar_ejemplo(g["id"], False)


def test_nadie_cambia_su_propio_rol(servidor):
    doc = _entrar("docente01"); est = _entrar("usuario01")
    with pytest.raises(N.SinPermiso):
        doc.asignar_perfil(doc.id, "visita")
    with pytest.raises(N.SinPermiso):
        est.asignar_perfil(est.id, "docente")
    with pytest.raises(N.SinPermiso):
        est._ejecutar(lambda: est.cliente.table("perfiles").update({"rol": "docente"}).eq("id", est.id).execute())
    v = next(p for p in doc.listar_perfiles() if p["usuario"] == "visita01")
    assert doc.asignar_perfil(v["id"], "estudiante")["rol"] == "estudiante"
    assert _entrar("visita01").rol == "estudiante"
    assert len(doc.listar_perfiles()) == 4 and len(est.listar_perfiles()) == 1


def test_asignaciones_publicadas_por_el_docente(servidor):
    doc = _entrar("docente01"); est = _entrar("usuario01")
    assert est.mi_asignacion() is None
    n = doc.publicar_asignaciones([dict(estudiante_id=est.id, curso="PAT 2026-2", familia="tomate",
                                        datos=dict(planta_id="tomate", modelo_tomate="m1", nombre_usuario="usuario01"))])
    assert n == 1
    a = est.mi_asignacion()
    assert a["curso"] == "PAT 2026-2" and a["datos"]["modelo_tomate"] == "m1"
    assert _entrar("usuario02").mi_asignacion() is None
    with pytest.raises(N.SinPermiso):
        est.publicar_asignaciones([dict(estudiante_id=est.id, datos={})])


def test_json_seguro_descarta_lo_que_no_es_json():
    import numpy as np
    d = N.json_seguro(dict(a=np.float64(1.5), b=(1, 2), c=lambda x: x, d={"e": {3}, "f": object()}, g=[np.int64(2), print]))
    assert d == dict(a=1.5, b=[1, 2], d={"e": [3]}, g=[2]) and json.dumps(d)


# ---------------------------------------------------------------- guardado automático
def test_guardado_automatico_sin_versiones(servidor, agro):
    a = _entrar("usuario01").almacen()
    g = a.autoguardar_proyecto_usuario(agro, estado=_estado(), persona="", huella="h1")
    assert g["nuevo"] and g["nombre"] == "Proyecto 1"
    p = a.obtener_proyecto_usuario(g["id"])
    assert p["n_versiones"] == 0 and p["autoguardado_en"]
    assert a.listar_versiones_usuario(g["id"]) == []
    g2 = a.autoguardar_proyecto_usuario(agro, estado=_estado(), proyecto_id=g["id"], persona="Ana Pérez", huella="h2")
    assert g2["id"] == g["id"] and not g2["nuevo"] and g2["nombre"] == "Proyecto de Ana Pérez 1"   # toma el nombre de la persona
    u = a.ultimo_autoguardado(usuario="usuario01")
    assert u["proyecto_id"] == g["id"]
    d = a.cargar_autoguardado(g["id"])
    assert d["autoguardado"] and d["version"] == 0 and list(d["planta"].equipos) == list(agro.equipos)
    a.guardar_proyecto_usuario(agro, estado=_estado(), proyecto_id=g["id"])
    a.autoguardar_proyecto_usuario(agro, estado=dict(_estado(), _meta={"fecha": "x"}), proyecto_id=g["id"])
    assert a.autoguardado_igual_a_version(g["id"]) is True
    assert _entrar("usuario02").almacen().ultimo_autoguardado() is None       # la partida es de cada cuenta


def test_token_vencido_se_renueva_y_sin_red_avisa(servidor, agro):
    s = _entrar("usuario01"); a = s.almacen()
    servidor.vencidos.add(s.id)
    assert a.listar_proyectos_usuario() == []                                 # renovó la sesión y repitió el pedido
    servidor.sin_red = True; a._invalidar()
    with pytest.raises(N.SinConexion):
        a.listar_proyectos_usuario()
