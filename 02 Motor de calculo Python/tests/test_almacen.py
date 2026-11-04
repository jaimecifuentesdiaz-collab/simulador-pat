"""Almacenamiento común SQLite y SharePoint con bloqueo optimista (PAT 133, mejora 15).

SharePoint se prueba con un cliente HTTP simulado que imita la API de listas de Microsoft Graph (no hay acceso al sitio real)."""
import json, re, urllib.parse
import pytest
from pat_sim.datos import almacen as AL
from pat_sim.datos.bd import BaseDatos
from pat_sim.escenarios import agrozzi, pellet
from pat_sim.motor.resumen import resumen_planta


class GraphSimulado:
    """Listas de SharePoint en memoria: GET con $filter «fields/X eq 'v'», POST, PATCH con If-Match y eTag, paginación."""

    def __init__(self, pagina=2):
        self.listas = {}; self.n = 0; self.pagina = pagina; self.llamadas = []; self.antes_de_patch = None

    def solicitar(self, metodo, url, enc, cuerpo=None):
        self.llamadas.append((metodo, url, dict(enc)))
        assert enc["Authorization"] == "Bearer token-de-prueba"
        u = urllib.parse.urlparse(url); q = urllib.parse.parse_qs(u.query)
        m = re.match(r".*/sites/([^/]+)/lists/([^/]+)/items(?:/([^/]+))?(/fields)?$", u.path)
        lista = self.listas.setdefault(m.group(2), {}); item = m.group(3)
        if metodo == "POST":
            self.n += 1; i = str(self.n); lista[i] = dict(id=i, eTag=f'"{i},1"', fields=dict(cuerpo["fields"]))
            return 201, {}, lista[i]
        if metodo == "PATCH":
            if self.antes_de_patch:
                f, self.antes_de_patch = self.antes_de_patch, None; f(self)
            it = lista.get(item)
            if it is None: return 404, {}, {"error": {"message": "no existe"}}
            if enc.get("If-Match") and enc["If-Match"] != it["eTag"]: return 412, {}, {"error": {"message": "Precondition Failed"}}
            it["fields"].update(cuerpo); v = int(it["eTag"].strip('"').split(",")[1]) + 1; it["eTag"] = f'"{item},{v}"'
            return 200, {}, it["fields"]
        if item:
            return (200, {}, lista[item]) if item in lista else (404, {}, {"error": {"message": "no existe"}})
        vals = list(lista.values())
        if "$filter" in q:
            c, v = re.match(r"fields/(\w+) eq '(.*)'", q["$filter"][0]).groups(); v = v.replace("''", "'")
            vals = [x for x in vals if str(x["fields"].get(c)) == v]
        ini = int(q.get("skip", ["0"])[0]); trozo = vals[ini:ini + self.pagina]
        r = {"value": trozo}
        if ini + self.pagina < len(vals):
            q2 = {k: v[0] for k, v in q.items()}; q2["skip"] = str(ini + self.pagina)
            r["@odata.nextLink"] = u._replace(query=urllib.parse.urlencode(q2)).geturl()
        return 200, {}, r


CFG = dict(graph="https://graph.microsoft.com/v1.0", sitio="utalca.sharepoint.com,1,2", token="token-de-prueba",
           listas=dict(proyectos="LP", versiones="LV", corridas="LC"))


@pytest.fixture()
def sp():
    return AL.AlmacenSharePoint(dict(CFG, listas=dict(CFG["listas"])), cliente=GraphSimulado())


@pytest.fixture()
def lite(tmp_path):
    return AL.AlmacenSQLite(BaseDatos(tmp_path / "a.db"))


def _ciclo(al):
    pid = al.crear_proyecto("Prueba", "tomate", "desc")
    pl = agrozzi.crear(); r0 = resumen_planta(pl)
    v1 = al.guardar_version(pid, pl, "base", esperada=0)
    al.guardar_corrida(v1["id"], r0)
    pl2 = al.cargar_version(v1["id"])
    assert resumen_planta(pl2)["cascada"] == pytest.approx(r0["cascada"], rel=1e-9)
    v2 = al.guardar_version(pid, pl2, "segunda", esperada=1)
    assert (v1["numero"], v2["numero"]) == (1, 2) and al.ultima_version_numero(pid) == 2
    assert [v["numero"] for v in al.listar_versiones(pid)] == [2, 1]
    assert len(al.listar_corridas(v1["id"])) == 1
    with pytest.raises(AL.ConflictoVersion):           # otro usuario trabajaba sobre la versión 1
        al.guardar_version(pid, pl2, "tarde", esperada=1)
    assert al.ultima_version_numero(pid) == 2
    with pytest.raises(ValueError):
        al.crear_proyecto("Prueba")
    return pid


def test_sqlite_ciclo_completo_y_bloqueo_optimista(lite):
    pid = _ciclo(lite)
    assert lite.obtener_proyecto(pid)["nombre"] == "Prueba"


def test_sharepoint_ciclo_completo_con_cliente_simulado(sp):
    pid = _ciclo(sp)
    assert sp.obtener_proyecto("Prueba")["id"] == pid
    assert all(u.startswith("https://graph.microsoft.com/v1.0/sites/utalca.sharepoint.com,1,2/lists/") for _m, u, _e in sp.http.llamadas)
    assert any(m == "PATCH" and "If-Match" in e for m, _u, e in sp.http.llamadas)


def test_sharepoint_412_cuando_otro_usuario_guarda_en_medio(sp):
    pid = sp.crear_proyecto("Concurrente", "pellet"); pl = pellet.crear()
    sp.guardar_version(pid, pl, "v1")
    def otro_usuario(g):                                 # otro cliente sube la versión entre la lectura y el PATCH
        it = g.listas["LP"][pid]; it["fields"]["UltimaVersion"] = 2; it["eTag"] = f'"{pid},99"'
    sp.http.antes_de_patch = otro_usuario
    with pytest.raises(AL.ConflictoVersion) as e:
        sp.guardar_version(pid, pl, "mía")
    assert sp.ultima_version_numero(pid) == 2 and len(sp.listar_versiones(pid)) == 1


def test_sharepoint_paginacion_y_nombre_con_apostrofo(sp):
    for i in range(5):
        sp.crear_proyecto(f"P{i}")
    sp.crear_proyecto("Planta d'Agrozzi")
    assert len(sp.listar_proyectos()) == 6 and sp.obtener_proyecto("Planta d'Agrozzi")["nombre"] == "Planta d'Agrozzi"


def test_config_sin_secretos_y_variables_de_entorno():
    import os
    cfg = AL.leer_config(AL.CONFIG_SHAREPOINT)
    assert cfg["token"] == "" and "<" in cfg["sitio"]
    with pytest.raises(AL.ErrorAlmacen):
        AL.AlmacenSharePoint(cfg, cliente=GraphSimulado())
    claves = ("PAT_SP_TOKEN", "PAT_SP_SITIO", "PAT_SP_LISTA_PROYECTOS", "PAT_SP_LISTA_VERSIONES", "PAT_SP_LISTA_CORRIDAS")
    viejo = {k: os.environ.get(k) for k in claves}
    try:
        os.environ.update(PAT_SP_TOKEN="token-de-prueba", PAT_SP_SITIO="s,1,2", PAT_SP_LISTA_PROYECTOS="LP", PAT_SP_LISTA_VERSIONES="LV",
                          PAT_SP_LISTA_CORRIDAS="LC")
        a = AL.AlmacenSharePoint(AL.leer_config(AL.CONFIG_SHAREPOINT), cliente=GraphSimulado())
        assert a.cfg["sitio"] == "s,1,2" and a.cfg["listas"]["corridas"] == "LC"
    finally:
        for k, v in viejo.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v


def test_abrir_por_defecto_es_sqlite(tmp_path):
    assert isinstance(AL.abrir("sqlite", ruta=tmp_path / "x.db"), AL.AlmacenSQLite)
    with pytest.raises(ValueError):
        AL.abrir("otro")
