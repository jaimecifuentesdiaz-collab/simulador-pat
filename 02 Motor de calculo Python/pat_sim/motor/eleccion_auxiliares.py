"""Elección en vivo de los equipos auxiliares por costo total (PAT 139, punto 6 de los comentarios del profesor Torres del 14-11-2026).

Igual que en la Planta real, cada equipo auxiliar (bomba, válvula de control, estanque pulmón y generación de vapor o calor) tiene una
lista de candidatos ordenada por C = C_inv + C_op + C_inef (motor/costo_total.costo_total_opcion) y el estudiante los elige de uno en
uno, con «Generar automáticamente» (menor C en cada uno) y «Deshacer» (la misma pila de la Planta ficticia y de la Planta real).

Candidatos de cada auxiliar:
- Equipos reales de datos/referencia_equipos.candidatos (equipo E2: Tavily en línea y base de respaldo), si el módulo existe y entrega
  equipos del tipo en la misma unidad; con cada uno se arma k = ⌈requerida/capacidad⌉ y la misma opción con una unidad de reserva.
- Esquemas de tamaño escalados con Williams desde el precio que ya usa la pantalla (el del costeo, motor/costeo.py, o el Supuesto del
  estanque de motor/auxiliares.py): un equipo del tamaño justo, uno más uno de reserva, dos de la mitad y dos de la mitad más uno de
  reserva. Su origen es «Williams» y su precio hereda la fuente del precio de partida.

La elección queda guardada en la planta (pl._p["eleccion_auxiliares"]), que entra en la instantánea de la planta: por eso «Deshacer»
la vuelve atrás junto con las elecciones de la Planta real y los movimientos del lienzo. No usa Streamlit.
"""
from __future__ import annotations
import math
from datetime import date

from . import auxiliares as AX, costeo as CO, costo_total as CT, seleccion as SEL
from .eleccion_viva import con_historial, calza, _posicion
from .operacion import Supuesto

CLAVE = "eleccion_auxiliares"
# PAT 140 g: posición en el lienzo de cada bomba, válvula o estanque soltado fuera de su línea ({id: {x, y}}, mismas unidades que la
# posición de los equipos) y línea que sirve cada bomba reconectada ({id de la bomba: clave de la conexión}). Ambas viajan con la planta.
CLAVE_POS = "posiciones_auxiliares"
CLAVE_LINEA = "lineas_auxiliares"
SUPUESTOS = {s.clave: s for s in [
    Supuesto("serie_aux", "Equipo auxiliar en serie con la línea", 1.0, "—",
             "Para el costo de ineficiencia C_inef cada equipo auxiliar se trata en serie con la línea de proceso: si se detiene, la planta "
             "deja de producir su producción planificada. Es el caso conservador; una bomba de una línea secundaria pesa menos, y se "
             "reemplaza con el análisis de cada línea"),
    Supuesto("esquemas", "Esquemas de tamaño de los auxiliares", 4.0, "esquemas",
             "Un equipo del tamaño justo (1 de 1), uno más uno de reserva (1 de 2), dos de la mitad (2 de 2) y dos de la mitad más uno de "
             "reserva (2 de 3), los arreglos usuales de bombas y calderas; la válvula de control se compara sola o con una de respaldo "
             "(1 de 2). El precio de cada tamaño se escala con Williams desde el precio de partida de la pantalla"),
]}
ESQUEMAS = {"bomba": ((1, 1), (1, 2), (2, 2), (2, 3)), "valvula": ((1, 1), (1, 2)), "estanque": ((1, 1), (1, 2), (2, 2)),
            "servicio": ((1, 1), (1, 2), (2, 2), (2, 3))}
GRUPOS = {"bomba": "Bombas", "valvula": "Válvulas de control", "estanque": "Estanques pulmón", "servicio": "Servicios"}
TIPO_COSTEO = {"bomba": "bomba_centrifuga", "valvula": "valvula_control", "estanque": "estanque_pulmon", "servicio": "caldera_gas"}


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _f(v, d=1):
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- economía común
def economia_aux(pl, economia: dict | None = None) -> dict:
    """Parámetros de la Planta real (seleccion.parametros) que usa C: tasa, años, dólar, factor de instalación, precio de la energía,
    mantenimiento, horas, producción planificada y margen (valor unitario en US$ por t de producto)."""
    P = SEL.parametros(pl, economia)
    return dict(P=P, economia=dict(tasa=P["tasa"], anios=P["anios"], dolar=P["dolar"], f_inst=P["f_inst"], precio_kwh=P.get("precio_kwh"),
                                   mantencion_pct=P.get("mantencion_pct"), valor_unitario_usd=P["margen"] / P["dolar"],
                                   fuente_valor=P.get("fuente_margen") or ""))


def _reales(tipo: str, requerida: float, unidad: str, buscar_en_linea: bool, secretos=None) -> tuple[list[dict], list[str]]:
    """Equipos reales del tipo (datos/referencia_equipos, equipo E2) en la unidad pedida. Sin el módulo o si falla: lista vacía."""
    try:
        from ..datos import referencia_equipos as RE
    except Exception:
        return [], []
    try:
        kw = dict(en_linea=bool(buscar_en_linea))
        if secretos is not None:
            kw["secretos"] = secretos
        res = RE.candidatos(tipo, requerida, unidad, **kw) or []
    except Exception as e:
        return [], [f"referencia_equipos no respondió para {tipo} ({type(e).__name__}): se usan los tamaños escalados con Williams."]
    out = []
    for c in res:
        cap, pr = _num(c.get("capacidad")), _num(c.get("precio_usd"))
        if not cap or cap <= 0 or (c.get("unidad") or unidad) != unidad or pr is None or pr <= 0:
            continue
        out.append(dict(modelo=str(c.get("modelo") or "Sin modelo"), fabricante=c.get("fabricante") or "", capacidad=cap, precio_usd=pr,
                        origen=c.get("origen") or ("Tavily" if c.get("url") else "Respaldo"), url=c.get("url") or "",
                        fuente=c.get("fuente") or c.get("fuente_precio") or "", potencia_kw=_num(c.get("potencia_kw")),
                        mtbf_h=_num(c.get("mtbf_h")), mttr_h=_num(c.get("mttr_h"))))
    return out, []


def _opcion(obj: dict, modelo: str, fabricante: str, cap: float, precio: float, n: int, k: int, origen: str, fuente: str, url: str,
            pot_unidad: float | None, E: dict, horas: float, prod: float, mtbf=None, mttr=None) -> dict:
    opc = dict(modelo=modelo, tipo=TIPO_COSTEO[obj["clase"]], n=n, k=k, capacidad=cap, precio_usd=precio, potencia_kw=pot_unidad,
               mtbf_h=mtbf, mttr_h=mttr, produccion_anual=prod)
    ct = CT.costo_total_opcion(opc, obj["requerida"], horas, E)
    etq = f"{n} × {modelo}" + (f" ({k} de {n}, con reserva)" if n > k else "")
    return dict(id=f"{obj['id']}|{modelo}|{n}", objetivo=obj["id"], equipo=obj["id"], modelo=modelo, fabricante=fabricante, n=n, k=k,
                capacidad=cap, unidad=obj["unidad"], precio_usd=precio, origen=origen, fuente=fuente, url=url, etiqueta=etq,
                C=ct["C"], C_inv=ct["C_inv"], C_op=ct["C_op"], C_inef=ct["C_inef"], C_clp=ct["C_clp"], A=ct["A"], A_equipo=ct["A_equipo"],
                eta_operacion=ct["eta"], eta_relativa=ct["eta_relativa"], q_unidad=ct["q_unidad"], avisos_costo=ct["avisos"],
                fuentes_costo=ct["fuentes"], detalle_costo=ct["detalle"])     # PAT 140 c: para la ficha comparativa de 3 opciones


def candidatos_objetivo(obj: dict, E: dict, horas: float, prod: float, buscar_en_linea: bool = True, secretos=None) -> tuple[list[dict], list[str]]:
    """Candidatos de un auxiliar ordenados por C: los reales de referencia_equipos y los esquemas escalados con Williams."""
    out, avisos = [], []
    S = obj["requerida"]
    reales, av = _reales(TIPO_COSTEO[obj["clase"]], S, obj["unidad"], buscar_en_linea, secretos)
    avisos += av
    for c in reales:
        k = max(1, math.ceil(S / c["capacidad"] - 1e-9))
        if k > SEL.N_MAX:
            continue
        pot = c["potencia_kw"] if c["potencia_kw"] else (obj["potencia_kw"] * c["capacidad"] / S if obj.get("potencia_kw") else None)
        for n in (k, k + 1):
            out.append(_opcion(obj, c["modelo"], c["fabricante"], c["capacidad"], c["precio_usd"], n, k, c["origen"], c["fuente"], c["url"],
                               pot, E, horas, prod, c["mtbf_h"], c["mttr_h"]))
    if obj.get("precio_ref_usd"):
        nw = obj.get("n_williams") or CO.N_SEIS_DECIMOS
        for k, n in ESQUEMAS[obj["clase"]]:
            cap = S / k
            precio = obj["precio_unitario"](cap) if obj.get("precio_unitario") else obj["precio_ref_usd"] * (1.0 / k) ** nw
            pot = obj["potencia_kw"] / k if obj.get("potencia_kw") else None
            modelo = f"{obj['nombre_modelo']} de {_f(cap, 1 if cap < 100 else 0)} {obj['unidad']}"
            fuente = f"Williams (n = {_f(nw, 2)}) desde {obj['fuente_precio']}"
            out.append(_opcion(obj, modelo, "", cap, precio, n, k, "Williams", fuente, "", pot, E, horas, prod))
        # PAT 140 c: siempre 3 opciones de distinto número de unidades n (motor/tres_opciones.py): si los esquemas no llegan a 3 valores
        # de n (válvulas y estanques), se agrega la etapa dividida en n unidades iguales que operan todas, escalada con Williams.
        ns = {c["n"] for c in out}
        for n in (1, 2, 3):
            if len(ns) >= 3:
                break
            if n in ns:
                continue
            cap = S / n
            precio = obj["precio_unitario"](cap) if obj.get("precio_unitario") else obj["precio_ref_usd"] * (1.0 / n) ** nw
            pot = obj["potencia_kw"] / n if obj.get("potencia_kw") else None
            modelo = f"{obj['nombre_modelo']} de {_f(cap, 1 if cap < 100 else 0)} {obj['unidad']}"
            fuente = f"Williams (n = {_f(nw, 2)}) desde {obj['fuente_precio']}; la etapa dividida en {n} unidades iguales (PAT 140 c)"
            out.append(_opcion(obj, modelo, "", cap, precio, n, n, "Williams", fuente, "", pot, E, horas, prod))
            ns.add(n)
    else:
        avisos.append(f"{obj['id']}: sin precio de partida en el costeo; no hay tamaños que escalar con Williams.")
    vistos, unicos = set(), []
    for c in sorted(out, key=lambda c: (c["C"], c["n"])):
        if c["id"] not in vistos:
            vistos.add(c["id"]); unicos.append(c)
    return unicos, avisos


def objetivos(pl, aux: dict | None, economia: dict | None = None, buscar_en_linea: bool = True, secretos=None) -> dict:
    """Auxiliares que se eligen (bombas, válvulas de control, estanques pulmón y generación de vapor o calor), cada uno con id, clase,
    grupo, nombre, requerida, unidad, dianas (ids que el lienzo dibuja: bomba, válvula o estanque, o el equipo de la planta) y
    candidatos ordenados por C. aux: resultado de motor/auxiliares.auxiliares. Planta vacía, sin resolver o sin aux: lista vacía y aviso."""
    if not getattr(pl, "equipos", None):
        return dict(objetivos=[], avisos=["La planta está vacía: no hay equipos auxiliares que elegir."])
    if not getattr(pl, "resuelta", False) or not aux:
        return dict(objetivos=[], avisos=["Resuelva la planta para elegir sus equipos auxiliares."])
    ee = economia_aux(pl, economia)
    E, P = ee["economia"], ee["P"]
    horas = P["horas"]
    objs, avisos = [], []
    nb = CO.exponente("bomba_centrifuga")[0]
    for x in (aux.get("bombas") or {}).get("filas") or []:
        Q = _num(x.get("Q_m3h"))
        if not Q or Q <= 0:
            continue
        objs.append(dict(id=x["id"], clase="bomba", nombre=f"Bomba {x['id']} (línea {x['linea']}, {x['origen']} → {x['destino']})",
                         nombre_largo=f"Bomba {x['id']} de la línea {x['linea']}, de {equipo_txt(pl, x['origen'])} a {equipo_txt(pl, x['destino'])}",
                         requerida=Q, unidad="m³/h", dianas=[x["id"]], potencia_kw=_num(x.get("potencia_kW")),
                         precio_ref_usd=_num(x.get("costo_usd")), n_williams=nb, fuente_precio=x.get("fuente_costo") or "costeo.py",
                         nombre_modelo="Bomba centrífuga", carga=None, linea=str(x["linea"]), origen=x["origen"], destino=x["destino"],
                         con=_con_bomba(pl, x), en_diagrama=bool(x.get("en_diagrama"))))
    for x in (aux.get("valvulas") or {}).get("control") or []:
        cv = _num(x.get("Cv"))
        if not cv or cv <= 0:
            continue
        objs.append(dict(id=x["id"], clase="valvula", nombre=x.get("nombre") or x["id"], requerida=cv, unidad="Cv", dianas=[x["id"]],
                         nombre_largo=f"Válvula de control {x['id']}" + (f" ({x['nombre']})" if x.get("nombre") else ""),
                         potencia_kw=None, precio_ref_usd=_num(x.get("costo_usd")), n_williams=CO.exponente("valvula_control")[0],
                         fuente_precio=x.get("fuente_costo") or "costeo.py", nombre_modelo="Válvula de control"))
    cepci = (aux.get("cepci_hoy") or CO.CEPCI_HOY)
    for x in (aux.get("estanques") or {}).get("filas") or []:
        v = _num(x.get("v_geo_m3"))
        if not v or v <= 0:
            continue
        objs.append(dict(id="TK " + x["id"], clase="estanque", nombre=f"Estanque pulmón entre {x['nombre_antes']} y {x['nombre_despues']}",
                         nombre_largo=f"Estanque pulmón TK {x['id']} entre {equipo_txt(pl, x.get('antes'), x['nombre_antes'])} y "
                                      f"{equipo_txt(pl, x.get('despues'), x['nombre_despues'])}",
                         requerida=v, unidad="m³", dianas=["TK " + x["id"]], potencia_kw=None, precio_ref_usd=_num(x.get("costo_usd")),
                         n_williams=AX.precio_estanque(v, cepci)["n"], fuente_precio=x.get("fuente_costo") or "Supuesto de motor/auxiliares.py",
                         nombre_modelo="Estanque pulmón", precio_unitario=lambda s, c=cepci: AX.precio_estanque(s, c)["costo_usd"]))
    gens = [k for k, eq in pl.equipos.items() if eq.tipo.startswith(("caldera", "generador"))]
    for x in (aux.get("servicios") or {}).get("filas") or []:
        dem = _num(x.get("demanda"))
        if x.get("servicio") not in ("Vapor", "Calor (aire caliente)") or not dem or dem <= 0 or not _num(x.get("costo_usd")):
            continue
        vapor = x["servicio"] == "Vapor"
        objs.append(dict(id="Generación de vapor" if vapor else "Generación de calor", clase="servicio",
                         nombre=("Generación de vapor" if vapor else "Generación de calor") + f" ({x.get('genera', '')})",
                         nombre_largo=("Generación de vapor" if vapor else "Generación de calor")
                                      + (f" en {', '.join(equipo_txt(pl, g) for g in gens)}" if gens else f" ({x.get('genera', '')})"),
                         requerida=dem, unidad="kW", dianas=gens, potencia_kw=None, precio_ref_usd=_num(x["costo_usd"]),
                         n_williams=CO.exponente("caldera_gas")[0], fuente_precio=x.get("fuente") or "costeo.py",
                         nombre_modelo="Caldera" if vapor else "Generador de calor"))
    prod = (P["plan"] or 0.0) * horas if P.get("plan") else None
    if not prod:                             # sin producto final: la mayor carga de la línea (t de carga por año)
        cargas = [r["carga_t_h"] for r in SEL.requerimientos(pl)]
        prod = max(cargas) * horas if cargas else None
    for o in objs:
        o["grupo"] = GRUPOS[o["clase"]]
        o["ctx"] = dict(E=E, horas=horas, prod=prod or 0.0)            # PAT 140 g: para evaluar un candidato en otro auxiliar
        o["candidatos"], av = candidatos_objetivo(o, E, horas, prod or 0.0, buscar_en_linea, secretos)
        avisos += av
        o.pop("precio_unitario", None)
    if not P.get("plan"):
        avisos.append("Sin producto final identificado: C_inef de los auxiliares usa la mayor carga de la línea (t de carga por año) como producción.")
    if not objs:
        avisos.append("La planta no tiene bombas, válvulas de control, estanques pulmón ni generación de vapor o calor que elegir.")
    return dict(objetivos=objs, avisos=list(dict.fromkeys(avisos)), parametros=P)


# ---------------------------------------------------------------- PAT 140 g: nombres, posiciones y línea de cada auxiliar
def equipo_txt(pl, eid, respaldo: str | None = None) -> str:
    """«B1 Recepción de tomate»: id y nombre del equipo, para que los avisos se entiendan sin buscar el código en el lienzo."""
    eq = (getattr(pl, "equipos", None) or {}).get(eid)
    nom = str(getattr(eq, "nombre", "") or respaldo or "").strip()
    if not eid:
        return nom or "?"
    return f"{eid} {nom}" if nom and nom != eid else str(eid)


def _con_bomba(pl, x: dict) -> str | None:
    """Clave de la conexión (línea del lienzo) de una fila de bomba de motor/auxiliares.bombas."""
    from . import lienzo as LZ
    c = LZ._con_entre(pl, x.get("origen"), x.get("destino"), x.get("linea"))
    return LZ._clave_conexion(c) if c is not None else None


def _p(pl) -> dict:
    if not isinstance(getattr(pl, "_p", None), dict):
        pl._p = {}
    return pl._p


def posiciones(pl) -> dict:
    """{id del auxiliar: {x, y}} de los auxiliares que el estudiante dejó en otro lugar del lienzo (copia)."""
    p = getattr(pl, "_p", None)
    return {k: dict(v) for k, v in ((p or {}).get(CLAVE_POS) or {}).items()} if isinstance(p, dict) else {}


def lineas(pl) -> dict:
    """{id de la bomba: clave de la conexión que sirve} de las bombas reconectadas a otra línea (copia, en el orden en que se hicieron)."""
    p = getattr(pl, "_p", None)
    return dict((p or {}).get(CLAVE_LINEA) or {}) if isinstance(p, dict) else {}


def _guardar_dict(pl, clave: str, d: dict) -> None:
    if d:
        _p(pl)[clave] = d
    else:
        _p(pl).pop(clave, None)


def _fijar_pos(pl, aid: str, pos) -> None:
    ps = posiciones(pl)
    xy = _posicion(pos, None)
    if xy is None:
        ps.pop(aid, None)
    else:
        ps[aid] = dict(x=round(xy[0], 1), y=round(xy[1], 1))
    _guardar_dict(pl, CLAVE_POS, ps)


def mover(pl, hist, aid: str, pos) -> dict:
    """Deja el símbolo de un auxiliar en otro lugar del lienzo (pos = {x, y}) o, con pos None, de vuelta sobre su línea. Un paso de
    deshacer. El auxiliar sigue conectado a su línea (el lienzo dibuja el trazo que los une) y su cálculo no cambia."""
    if not aid:
        return dict(ok=False, cambio=False, mensaje="Falta el equipo auxiliar que se movió.")
    r = con_historial(pl, hist, f"mover {aid}", lambda p: _fijar_pos(p, aid, pos))
    r["mensaje"] = None if _posicion(pos) is not None else (f"{aid} volvió a su lugar sobre la línea." if r["cambio"] else None)
    return r


def aplicar_lineas(pl, aux: dict | None) -> dict | None:
    """Resultado de motor/auxiliares.auxiliares con las bombas reconectadas por el estudiante: cada línea de líquido sigue con una bomba
    (el cálculo de caudal, altura, diámetro, potencia y costo de cada línea no cambia), pero la bomba reconectada toma la fila de su
    nueva línea y la que estaba en ella pasa a la línea que dejó (se intercambian los nombres). Sin reconexiones devuelve aux tal cual."""
    m = lineas(pl)
    if not m or not aux or not (aux.get("bombas") or {}).get("filas"):
        return aux
    filas = [dict(f) for f in aux["bombas"]["filas"]]
    cons = [_con_bomba(pl, f) for f in filas]
    for aid, con in m.items():
        ix = next((i for i, f in enumerate(filas) if f["id"] == aid and not f.get("en_diagrama")), None)
        il = next((i for i, c in enumerate(cons) if c == con and not filas[i].get("en_diagrama")), None)
        if ix is None or il is None or ix == il:
            continue
        filas[ix]["id"], filas[il]["id"] = filas[il]["id"], filas[ix]["id"]
    out = dict(aux)
    out["bombas"] = dict(aux["bombas"], filas=filas)
    return out


def adaptar_candidato(c: dict, destino: dict, forzar: bool = False) -> tuple[dict | None, str]:
    """El mismo equipo (modelo, n y k) de un candidato evaluado para otro auxiliar de la misma clase (destino: un objetivo de
    objetivos()). Calza si la capacidad de las k unidades queda a ±20 % de lo que pide el destino. Devuelve (candidato o None, motivo).
    PAT 143 (conexión libre): con forzar=True se evalúa aunque no calce y el motivo dice por qué no calza."""
    if not destino or not destino.get("ctx"):
        return None, "no hay datos para evaluarlo en ese equipo"
    if c.get("unidad") and destino.get("unidad") and c["unidad"] != destino["unidad"]:
        return None, "es otro tipo de equipo"
    cap, k, n = _num(c.get("capacidad")), int(c.get("k") or 0), int(c.get("n") or 0)
    if not cap or k < 1 or n < k:
        return None, "el candidato no trae su capacidad"
    ok, motivo = calza(cap * k, destino["requerida"], destino.get("unidad") or "")
    if not ok and not forzar:
        return None, motivo
    motivo = "" if ok else motivo
    S = destino["requerida"]
    pot = destino["potencia_kw"] * cap / S if destino.get("potencia_kw") else None
    x = destino["ctx"]
    return _opcion(destino, c["modelo"], c.get("fabricante") or "", cap, float(c["precio_usd"]), n, k, c.get("origen") or "",
                   c.get("fuente") or "", c.get("url") or "", pot, x["E"], x["horas"], x["prod"]), motivo


def _readaptar(el: dict, aid: str, destino: dict | None) -> bool:
    """La elección guardada de aid evaluada otra vez con lo que pide su nueva línea (destino). False si ya no calza."""
    g = el.get(aid)
    if not g or not destino:
        return True
    c2, _m = adaptar_candidato(g, dict(destino, id=aid))
    if c2 is None:
        return False
    el[aid] = _registro(c2)
    return True


def reconectar(pl, hist, aid: str, con: str, objs: list[dict], pos=None) -> dict:
    """Conecta la bomba aid a otra línea del lienzo (con: clave de la conexión). Cada línea de líquido lleva una bomba: aid toma el caudal,
    la altura, el diámetro y la potencia de la nueva línea y la bomba que estaba en ella pasa a la línea que aid deja. Las elecciones
    de las dos se evalúan otra vez con su nueva línea (C, A y η). Un paso de deshacer. Las válvulas de control (de su lazo) y los
    estanques pulmón (entre dos equipos) no cambian de línea: solo se mueve su símbolo."""
    o = next((x for x in objs or [] if x["id"] == aid), None)
    if o is None or o.get("clase") != "bomba":
        r = mover(pl, hist, aid, pos) if _posicion(pos) is not None else dict(ok=True, cambio=False)
        tipo = "La válvula de control sigue en su lazo de control" if (o or {}).get("clase") == "valvula" or str(aid).startswith(("FV", "TV", "LV", "PV")) \
            else ("El estanque pulmón sigue entre sus dos equipos" if str(aid).startswith("TK") else f"{aid} sigue en su lugar")
        return dict(r, ok=False, mensaje=f"Solo las bombas se cambian de línea. {tipo}; su símbolo quedó donde lo soltó.")
    if o.get("en_diagrama"):
        return dict(ok=False, cambio=False, mensaje=f"{aid} es un equipo del diagrama: su línea se cambia en Planta ficticia (Diseño).")
    o2 = next((x for x in objs if x.get("clase") == "bomba" and x.get("con") == con), None)
    if o2 is None:
        return dict(ok=False, cambio=False, mensaje=f"Esa línea no lleva bomba (no mueve líquido por cañería): {o.get('nombre_largo') or aid} sigue donde estaba.")
    if o2["id"] == aid:
        r = mover(pl, hist, aid, pos)
        r["mensaje"] = None
        return r
    if o2.get("en_diagrama"):
        return dict(ok=False, cambio=False, mensaje=f"La bomba de esa línea ({o2['id']}) es un equipo del diagrama: se cambia en Planta ficticia (Diseño).")
    avisos = []

    def cambio(p):
        ls = lineas(p); ls.pop(aid, None); ls[aid] = con
        _guardar_dict(p, CLAVE_LINEA, ls)
        el = elecciones(p)
        if not _readaptar(el, aid, o2):
            avisos.append(f"El equipo elegido para {aid} no calza con el caudal de su nueva línea: revise su elección.")
        if not _readaptar(el, o2["id"], o):
            avisos.append(f"El equipo elegido para {o2['id']} no calza con el caudal de su nueva línea: revise su elección.")
        _guardar(p, el)
        _fijar_pos(p, aid, pos)
        _fijar_pos(p, o2["id"], None)                # la bomba que cambia de línea queda sobre su nueva línea
    r = con_historial(pl, hist, f"conectar {aid} a la línea {o2.get('linea')}", cambio)
    f = lambda v: _f(v, 1 if v < 100 else 0)
    r["mensaje"] = (f"{aid} ahora sirve la línea {o2.get('linea')}, de {equipo_txt(pl, o2.get('origen'))} a {equipo_txt(pl, o2.get('destino'))}: "
                    f"toma su caudal ({f(o2['requerida'])} m³/h), su diámetro y su potencia. {o2['id']} pasa a la línea {o.get('linea')}, "
                    "porque cada línea de líquido lleva una bomba. Se recalcularon los candidatos y el C de las dos." + (" " + " ".join(avisos) if avisos else ""))
    return r


# ---------------------------------------------------------------- elección guardada en la planta
def elecciones(pl) -> dict:
    """{id del auxiliar: elección} guardadas en la planta (copia)."""
    p = getattr(pl, "_p", None)
    return dict((p or {}).get(CLAVE) or {}) if isinstance(p, dict) else {}


def _guardar(pl, nuevas: dict) -> None:
    if not isinstance(getattr(pl, "_p", None), dict):
        pl._p = {}
    if nuevas:
        pl._p[CLAVE] = nuevas
    else:
        pl._p.pop(CLAVE, None)


def _registro(c: dict) -> dict:
    return dict(id=c["id"], modelo=c["modelo"], fabricante=c.get("fabricante") or "", n=int(c["n"]), k=int(c["k"]), capacidad=float(c["capacidad"]),
                unidad=c.get("unidad") or "", precio_usd=float(c["precio_usd"]), origen=c.get("origen") or "", etiqueta=c.get("etiqueta") or "",
                C=float(c["C"]), C_inv=float(c["C_inv"]), C_op=float(c["C_op"]), C_inef=float(c["C_inef"]), A=float(c["A"]),
                fuente=c.get("fuente") or "", url=c.get("url") or "", fecha=date.today().isoformat())


def aplicar_candidato(pl, hist, candidato: dict, pos=None, diana: str | None = None, nombre: str | None = None) -> dict:
    """Guarda la elección de un auxiliar en la planta con un paso de deshacer. PAT 140 g: pos = {x, y} (soltado en un lugar libre del
    lienzo) deja el símbolo de diana en ese lugar en el mismo paso; nombre: nombre completo del auxiliar para el aviso."""
    if not candidato or not candidato.get("objetivo"):
        return dict(ok=False, cambio=False, mensaje="Ese candidato no corresponde a un equipo auxiliar.")
    oid = candidato["objetivo"]
    con_pos = bool(diana) and _posicion(pos) is not None

    def cambio(p):
        el = elecciones(p); el[oid] = _registro(candidato); _guardar(p, el)
        if con_pos:
            _fijar_pos(p, diana, pos)
    r = con_historial(pl, hist, f"elegir {candidato['etiqueta']} en {oid}", cambio)
    quien = nombre or oid
    r["mensaje"] = ((f"Se aplicó {candidato['etiqueta']} a {con_articulo(quien)}" + (", en el lugar donde lo soltó." if con_pos else "."))
                    if r["cambio"] else f"{quien} ya tenía ese equipo.")
    return r


def con_articulo(nombre: str) -> str:
    """«la bomba P-101 de la línea 1, …», «el estanque pulmón TK …»: el nombre completo dentro de una frase."""
    t = str(nombre or "")
    for pal, art in (("Bomba", "la"), ("Válvula", "la"), ("Generación", "la"), ("Estanque", "el")):
        if t.startswith(pal):
            return f"{art} {t[:1].lower()}{t[1:]}"
    return t


def generar_automaticamente(pl, hist, objs: list[dict]) -> dict:
    """Menor C en cada auxiliar, en un solo paso de deshacer."""
    mejores = {o["id"]: o["candidatos"][0] for o in objs or [] if o.get("candidatos")}
    if not mejores:
        return dict(ok=False, cambio=False, n=0, mensaje="No hay equipos auxiliares con candidatos.")

    def cambio(p):
        el = elecciones(p)
        for k, c in mejores.items():
            el[k] = _registro(c)
        _guardar(p, el)
    r = con_historial(pl, hist, "generar automáticamente los auxiliares (criterio: menor C)", cambio)
    r["n"] = len(mejores)
    r["mensaje"] = f"Generado: la opción de menor C en {len(mejores)} equipos auxiliares." if r["cambio"] else "Cada auxiliar ya tenía la opción de menor C."
    return r


def quitar_todo(pl, hist) -> dict:
    r = con_historial(pl, hist, "quitar los auxiliares elegidos", lambda p: _guardar(p, {}))
    r["mensaje"] = "Elecciones de auxiliares quitadas." if r["cambio"] else "No había auxiliares elegidos."
    return r


def estado(pl, objs: list[dict]) -> dict:
    """Totales de los auxiliares elegidos: C, C_inv, C_op, C_inef (US$/año), A_sist (producto de A) y cuántos faltan. Cada fila trae
    el candidato elegido (el de la lista vigente con el mismo id o, si cambió la lista, el registro guardado) y el mejor."""
    el = elecciones(pl)
    filas, elegidos = [], []
    for o in objs or []:
        cs = o.get("candidatos") or []
        g = el.get(o["id"])
        e = next((c for c in cs if g and c["id"] == g.get("id")), None) or (dict(g, vigente=False) if g else None)
        mejor = cs[0] if cs else None
        filas.append(dict(objetivo=o["id"], grupo=o.get("grupo"), nombre=o.get("nombre"), requerida=o.get("requerida"), unidad=o.get("unidad"),
                          elegido=e, mejor=mejor, es_mejor=bool(e and mejor and e.get("id") == mejor.get("id")), n_candidatos=len(cs)))
        if e is not None:
            elegidos.append(e)
    tot = {k: (float(sum(_num(c.get(k)) or 0.0 for c in elegidos)) if elegidos else None) for k in ("C", "C_inv", "C_op", "C_inef")}
    A = float(math.prod(_num(c.get("A")) or 0.0 for c in elegidos)) if elegidos else None
    c_min = float(sum(f["mejor"]["C"] for f in filas if f["mejor"])) if any(f["mejor"] for f in filas) else None
    return dict(filas=filas, n_objetivos=len(filas), n_elegidos=len(elegidos), A_sist=A, C_min=c_min, **tot)


def buscar_candidato(objs: list[dict], cid: str) -> dict | None:
    for o in objs or []:
        for c in o.get("candidatos") or []:
            if c["id"] == cid:
                return c
    return None


def procesar_evento(pl, hist, ev: dict, objs: list[dict], libre: bool = False) -> dict:
    """Evento del lienzo de Equipos auxiliares: «elegir» {objetivo, candidato, destino?, pos?, diana?}, «generar», «quitar», «mover»,
    «mover_aux» {id, pos}, «conectar_aux» {id, con, pos?}, «deshacer» y «rehacer».
    PAT 140 g: con «pos» (soltado en un lugar libre del lienzo) el símbolo queda en ese lugar; con «destino» (soltado sobre otro
    auxiliar de la misma clase) el mismo equipo se aplica a ese auxiliar si su capacidad calza (±20 %). PAT 143: con libre=True
    (conexión libre) se aplica aunque no calce, con un aviso, y el validador lo marca si no alcanza lo que pide su línea."""
    from . import eleccion_viva as EV
    e = ev.get("evento"); d = ev.get("datos") or {}
    nombres = {o["id"]: o.get("nombre_largo") or o.get("nombre") or o["id"] for o in objs or []}
    if e == "elegir":
        c = buscar_candidato(objs, d.get("candidato"))
        if c is None:
            return dict(ok=False, mensaje="El candidato ya no está en la lista: vuelva a elegirlo.", recalcular=False)
        if d.get("objetivo") and d["objetivo"] != c["objetivo"]:
            return dict(ok=False, mensaje=f"Ese candidato es para {con_articulo(nombres.get(c['objetivo'], c['objetivo']))}: suéltelo en un lugar libre "
                                          "del lienzo o sobre ese equipo.", recalcular=False)
        dest = d.get("destino")
        if dest and dest != c["objetivo"]:
            od = next((o for o in objs or [] if o["id"] == dest), None)
            oo = next((o for o in objs or [] if o["id"] == c["objetivo"]), None)
            if od is None or (oo is not None and od.get("clase") != oo.get("clase")):
                return dict(ok=False, mensaje=f"{nombres.get(dest, dest)} es otro tipo de equipo: el candidato no se aplicó.", recalcular=False)
            # (el lienzo solo marca como destino los auxiliares de la misma clase)
            c2, motivo = adaptar_candidato(c, od, forzar=libre)
            if c2 is None:
                return dict(ok=False, mensaje=f"No se aplicó {c['etiqueta']} a {con_articulo(nombres.get(dest, dest))}: {motivo}.", recalcular=False)
            r = aplicar_candidato(pl, hist, c2, nombre=nombres.get(dest))
            msg = r["mensaje"] + (f" No calza: {motivo}; la advertencia lo marca si no alcanza lo que pide su línea." if motivo and r["ok"] else "")
            return dict(ok=r["ok"], mensaje=msg, recalcular=False, id=dest)
        r = aplicar_candidato(pl, hist, c, d.get("pos"), d.get("diana"), nombres.get(c["objetivo"]))
        return dict(ok=r["ok"], mensaje=r["mensaje"], recalcular=False)
    if e == "mover_aux":
        r = mover(pl, hist, d.get("id"), d.get("pos"))
        return dict(ok=r["ok"], mensaje=r.get("mensaje"), recalcular=False)
    if e == "conectar_aux":
        r = reconectar(pl, hist, d.get("id"), d.get("con"), objs, d.get("pos"))
        return dict(ok=r["ok"], mensaje=r.get("mensaje"), recalcular=False)
    if e == "generar":
        r = generar_automaticamente(pl, hist, objs)
        return dict(ok=r["ok"], mensaje=r["mensaje"], recalcular=False)
    if e == "quitar":
        r = quitar_todo(pl, hist)
        return dict(ok=r["ok"], mensaje=r["mensaje"], recalcular=False)
    return EV.procesar_evento(pl, hist, ev, {}) if e in ("mover", "deshacer", "rehacer") else \
        dict(ok=False, mensaje=f"Evento desconocido en Equipos auxiliares: {e}.", recalcular=False)
