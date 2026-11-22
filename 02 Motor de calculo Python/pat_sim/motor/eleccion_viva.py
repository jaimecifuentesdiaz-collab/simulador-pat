"""Elección en vivo de los equipos reales (PAT 139, punto 6 de los comentarios del profesor Torres del 14-11-2026).

En la Planta real el estudiante elige los equipos de uno en uno: toma un candidato de la lista de su etapa (motor/costo_total.py,
candidatos_etapa, ordenados por C = C_inv + C_op + C_inef) y lo suelta sobre la etapa en el lienzo. Cada elección queda en la planta
única (seleccion.aplicar: modelo, n, k, MTBF, MTTR y capacidad instalada) y se puede deshacer, igual que mover un equipo en el lienzo.

La pila de deshacer es la misma de la Planta ficticia (motor/lienzo.Historial, instantáneas completas de la planta con
instantanea y restaurar): así «Deshacer» vuelve atrás el último cambio, sea una elección de equipo, «Generar automáticamente» o un
movimiento del layout, y el orden se respeta aunque el estudiante pase de una pantalla a otra. Después de deshacer, la planta queda sin
resolver (restaurar) y quien llama la resuelve de nuevo.

Este módulo no usa Streamlit: la pantalla (ui/p_seleccion.py) solo le pasa la planta, el historial y los candidatos.
"""
from __future__ import annotations
import math

from . import lienzo as LZ, seleccion as SEL

EVENTOS = ("elegir", "generar", "quitar", "mover", "deshacer", "rehacer")


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


# ---------------------------------------------------------------- pila de cambios
def con_historial(pl, hist, etiqueta: str, cambio) -> dict:
    """Ejecuta cambio(pl) y, si la planta cambió, apila el estado anterior con su etiqueta (un solo paso de deshacer).
    Devuelve {ok, cambio, mensaje, valor} con valor lo que devolvió cambio."""
    antes = LZ.instantanea(pl)
    valor = cambio(pl)
    cambio_ok = LZ.instantanea(pl) != antes
    if cambio_ok and hist is not None:
        hist.apilar(antes, etiqueta)
    return dict(ok=True, cambio=cambio_ok, mensaje=None, valor=valor)


def deshacer(pl, hist) -> dict:
    """Vuelve la planta al estado anterior al último cambio (elección, generar, quitar o mover). La planta queda sin resolver."""
    return LZ.aplicar_con_historial(pl, dict(evento="deshacer", datos={}), hist)


def rehacer(pl, hist) -> dict:
    return LZ.aplicar_con_historial(pl, dict(evento="rehacer", datos={}), hist)


def mover(pl, hist, eid: str, x: float, y: float) -> dict:
    """Cambio del layout desde el lienzo de la Planta real o de Equipos auxiliares, con deshacer."""
    return LZ.aplicar_con_historial(pl, dict(evento="mover", datos=dict(id=eid, x=x, y=y)), hist)


# ---------------------------------------------------------------- elección de la planta real
def _etiqueta(c: dict) -> str:
    return f"elegir {c.get('etiqueta') or c.get('modelo')} en {c.get('equipo')}"


def nombre_etapa(pl, eid: str) -> str:
    """Nombre completo de una etapa para los avisos: «etapa F1 Lavado y selección»."""
    eq = (getattr(pl, "equipos", None) or {}).get(eid)
    nom = str(getattr(eq, "nombre", "") or "").strip()
    return f"etapa {eid} {nom}" if nom and nom != eid else f"etapa {eid}"


def _posicion(pos, minimo: float | None = 0.0) -> tuple[float, float] | None:
    """(x, y) de una posición {x, y} del lienzo, o None si no viene o no es numérica. Con minimo (los equipos), no baja de ese valor; un
    auxiliar (minimo None) puede quedar a la izquierda o arriba del primer equipo."""
    if not isinstance(pos, dict):
        return None
    x, y = _num(pos.get("x")), _num(pos.get("y"))
    if x is None or y is None:
        return None
    return (x, y) if minimo is None else (max(minimo, x), max(minimo, y))


def aplicar_candidato(pl, hist, candidato: dict, pos: dict | None = None) -> dict:
    """Aplica un candidato de costo_total.candidatos_etapa a su etapa (seleccion.aplicar) con un paso de deshacer.
    PAT 140 g: pos = {x, y} (candidato soltado en un lugar libre del lienzo) deja la etapa en ese lugar, en el mismo paso de deshacer."""
    if not candidato or candidato.get("equipo") not in getattr(pl, "equipos", {}):
        return dict(ok=False, cambio=False, mensaje="Ese candidato no corresponde a una etapa de la planta.")
    eid = candidato["equipo"]
    xy = _posicion(pos)

    def cambio(p):
        v = SEL.aplicar(p, {eid: candidato})
        if v and xy is not None:
            LZ.aplicar_evento(p, dict(evento="mover", datos=dict(id=eid, x=xy[0], y=xy[1])))
        return v
    r = con_historial(pl, hist, _etiqueta(candidato), cambio)
    if not r["valor"]:
        return dict(ok=False, cambio=False, mensaje=f"{eid} no admite la elección de un equipo comercial.")
    etq = candidato.get("etiqueta") or candidato.get("modelo")
    r["mensaje"] = (f"Se aplicó {etq} a la {nombre_etapa(pl, eid)}" + (", en el lugar donde lo soltó." if xy is not None else ".")
                    if r["cambio"] else f"La {nombre_etapa(pl, eid)} ya tenía ese equipo.")
    r["id"] = eid
    return r


CALZA = 0.20       # PAT 140 g: un candidato se puede aplicar a otra etapa del mismo tipo si su capacidad difiere en ±20 % o menos


def calza(capacidad_total, requerida, unidad: str = "", tol: float = CALZA) -> tuple[bool, str]:
    """¿La capacidad de las k unidades en operación calza con lo que pide el destino (±tol)? Devuelve (calza, motivo en palabras)."""
    cap, req = _num(capacidad_total), _num(requerida)
    if cap is None or req is None or req <= 0 or cap <= 0:
        return False, "no se conoce la capacidad que necesita"
    r = cap / req
    if abs(r - 1.0) <= tol + 1e-9:
        return True, ""
    f = lambda v: f"{v:,.{0 if (v >= 100 or abs(v - round(v)) < 1e-9) else 1}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    u = f" {unidad}" if unidad else ""
    if r < 1:
        return False, (f"entrega {f(cap)}{u} y necesita {f(req)}{u}: le falta un {f(100 * (1 - r))} % (se acepta hasta "
                       f"{f(100 * tol)} % de diferencia)")
    return False, (f"entrega {f(cap)}{u} y necesita {f(req)}{u}: queda un {f(100 * (r - 1))} % sobredimensionado (se acepta hasta "
                   f"{f(100 * tol)} % de diferencia)")


def adaptar_candidato(pl, candidato: dict, destino: str, candidatos: dict | None = None, economia: dict | None = None,
                      forzar: bool = False) -> tuple[dict | None, str]:
    """PAT 140 g: el mismo equipo (modelo, n y k) de un candidato, evaluado para otra etapa del mismo tipo (soltado sobre ella en el
    lienzo). Calza si la capacidad de las k unidades queda a ±20 % de lo que pide la etapa. Usa el candidato de la lista de la etapa si
    ya está (mismo modelo, n y k) y, si no, lo evalúa con seleccion.evaluar. Devuelve (candidato o None, motivo en palabras).
    PAT 143 (conexión libre): con forzar=True se aplica aunque no calce; devuelve (candidato, motivo de por qué no calza) y el
    validador (motor/validador.py) marca la etapa si la capacidad no alcanza."""
    reqs = {r["equipo"]: r for r in SEL.requerimientos(pl)} if getattr(pl, "equipos", None) else {}
    ro, rd = reqs.get(candidato.get("equipo")), reqs.get(destino)
    if rd is None:
        return None, "esa etapa no tiene capacidad que elegir"
    if ro is not None and (ro.get("tipo_catalogo") != rd.get("tipo_catalogo") or ro.get("unidad") != rd.get("unidad")):
        return None, "es otro tipo de equipo"
    cap, k, n = _num(candidato.get("capacidad")) or _num(candidato.get("capacidad_modelo")), int(candidato.get("k") or 0), int(candidato.get("n") or 0)
    if not cap or k < 1 or n < k:
        return None, "el candidato no trae su capacidad"
    ok, motivo = calza(cap * k, rd["requerida"], rd.get("unidad") or "")
    if not ok and not forzar:
        return None, motivo
    motivo = "" if ok else motivo
    for c in (candidatos or {}).get(destino) or []:
        if c.get("modelo") == candidato.get("modelo") and int(c.get("n") or 0) == n and int(c.get("k") or 0) == k:
            return c, motivo
    try:
        P = SEL.parametros(pl, economia)
        fila = dict(tipo=candidato.get("tipo_catalogo") or rd.get("tipo_catalogo"), modelo=candidato.get("modelo"), capacidad=cap,
                    unidad=candidato.get("unidad") or rd.get("unidad"), mtbf_h=candidato.get("mtbf_h"), mttr_h=candidato.get("mttr_h"),
                    fuente_confiabilidad=candidato.get("fuente_confiabilidad") or "", categoria=candidato.get("categoria") or "Supuesto",
                    potencia_kw=candidato.get("potencia_unidad_kw"), _generico=bool(candidato.get("generico")))
        precio = dict(precio_usd=float(candidato.get("precio_usd") or candidato.get("precio_unitario_usd")),
                      fuente=candidato.get("fuente_precio") or candidato.get("fuente") or "", anio=candidato.get("anio_precio"))
        a = SEL.evaluar(rd, fila, n, k, P, precio, SEL.referencia_potencia(pl, destino))
    except Exception as e:                       # sin datos para evaluarlo: se avisa, no se aplica
        return None, f"no se pudo evaluar el equipo en esa etapa ({type(e).__name__})"
    return dict(a, id=f"{destino}|{a['modelo']}|{n}", fabricante=candidato.get("fabricante") or "", capacidad=a["capacidad_modelo"],
                precio_usd=a["precio_unitario_usd"], origen=candidato.get("origen") or "", eta_operacion=a["eta"], url=candidato.get("url") or "",
                fuente=a.get("fuente_precio") or "", origen_precio=candidato.get("origen_precio") or candidato.get("origen") or ""), motivo


def generar_automaticamente(pl, hist, candidatos: dict) -> dict:
    """«Generar automáticamente»: en cada etapa aplica la opción de menor C (la primera de su lista, como mejor_opcion), todo en
    un solo paso de deshacer. candidatos: {equipo: lista ordenada por C}. Etapas sin candidatos quedan como estaban."""
    mejores = {e: cs[0] for e, cs in (candidatos or {}).items() if cs}
    if not mejores:
        return dict(ok=False, cambio=False, n=0, mensaje="No hay candidatos que aplicar: la planta está vacía o sin etapas resueltas.")
    r = con_historial(pl, hist, "generar automáticamente (criterio: menor C en cada etapa)", lambda p: SEL.aplicar(p, mejores))
    r["n"] = int(r["valor"] or 0)
    r["mensaje"] = (f"Generado: la opción de menor C en {r['n']} etapas." if r["cambio"]
                    else "Cada etapa ya tenía la opción de menor C.")
    return r


def quitar_todo(pl, hist) -> dict:
    """Quita todas las elecciones (seleccion.quitar) con un paso de deshacer."""
    r = con_historial(pl, hist, "quitar los equipos elegidos", lambda p: SEL.quitar(p))
    r["mensaje"] = "Elecciones quitadas: la planta vuelve a los equipos teóricos." if r["cambio"] else "No había equipos elegidos."
    return r


def buscar_candidato(candidatos: dict, cid: str) -> dict | None:
    for cs in (candidatos or {}).values():
        for c in cs or []:
            if c.get("id") == cid:
                return c
    return None


def elegido(cands: list[dict], actual: dict | None) -> dict | None:
    """El candidato que coincide con la elección aplicada en el equipo (mismo modelo y n), o None."""
    if not actual:
        return None
    return next((c for c in cands or [] if c.get("modelo") == actual.get("modelo") and int(c.get("n") or 0) == int(actual.get("n") or 0)), None)


def estado_planta_real(pl, candidatos: dict, plan: float | None = None) -> dict:
    """Lo que se muestra arriba de la Planta real, recalculado en cada elección.
    filas: por etapa, el candidato elegido (o None), el mejor (menor C) y si la elección es la mejor.
    A_sist: producto de las disponibilidades A de las etapas elegidas (serie, costo_total); capacidad_t_h: capacidad efectiva de la
    línea con lo elegido (cuello de botella, seleccion.analizar_linea); C, C_inv, C_op y C_inef: suma de las etapas elegidas (US$/año).
    Con la planta vacía o sin etapas: todo en None y n_etapas = 0, sin fallar."""
    reqs = {r["equipo"]: r for r in SEL.requerimientos(pl)} if getattr(pl, "equipos", None) else {}
    filas, elegidas = [], []
    for eid, cs in (candidatos or {}).items():
        req = reqs.get(eid)
        act = req.get("actual") if req else None
        e = elegido(cs, act)
        mejor = cs[0] if cs else None
        filas.append(dict(equipo=eid, nombre=(req or {}).get("nombre", eid), requerida=(req or {}).get("requerida"), unidad=(req or {}).get("unidad", ""),
                          elegido=e, mejor=mejor, es_mejor=bool(e is not None and mejor is not None and e.get("id") == mejor.get("id")),
                          aplicado_fuera=bool(act and e is None), n_candidatos=len(cs or [])))
        if e is not None:
            elegidas.append(e)
    tot = {k: (float(sum(_num(c.get(k)) or 0.0 for c in elegidas)) if elegidas else None) for k in ("C", "C_inv", "C_op", "C_inef", "C_clp")}
    A = float(math.prod(_num(c.get("A")) or 0.0 for c in elegidas)) if elegidas else None
    cap = cuello = None
    if elegidas:
        try:
            L = SEL.analizar_linea(elegidas, plan)
            cap, cuello = L["capacidad_linea"], L["cuello"]
        except Exception:
            cap = cuello = None
    c_min = float(sum(_num(f["mejor"].get("C")) or 0.0 for f in filas if f["mejor"])) if any(f["mejor"] for f in filas) else None
    return dict(filas=filas, n_etapas=len(filas), n_elegidas=len(elegidas), A_sist=A, capacidad_t_h=cap, cuello=cuello, C_min=c_min,
                **tot)


def procesar_evento(pl, hist, ev: dict, candidatos: dict, economia: dict | None = None, libre: bool = False) -> dict:
    """Evento del lienzo de la Planta real: «elegir» {objetivo, candidato, destino?, pos?}, «generar», «quitar», «mover» {id, x, y},
    «deshacer» y «rehacer». Devuelve {ok, mensaje, recalcular} (recalcular: hay que resolver la planta otra vez).
    PAT 140 g: con «pos» (soltado en un lugar libre) la etapa queda en ese lugar; con «destino» (soltado sobre otra etapa del mismo
    tipo) el mismo equipo se aplica a esa etapa si su capacidad calza (±20 %). PAT 143: con libre=True (conexión libre) se aplica
    aunque no calce, con un aviso, y el validador marca la etapa si su capacidad no alcanza."""
    e = ev.get("evento"); d = ev.get("datos") or {}
    if e == "elegir":
        c = buscar_candidato(candidatos, d.get("candidato"))
        if c is None:
            return dict(ok=False, mensaje="El candidato ya no está en la lista: vuelva a elegirlo.", recalcular=False)
        if d.get("objetivo") and d["objetivo"] != c.get("equipo"):
            return dict(ok=False, mensaje=f"Ese candidato es para la {nombre_etapa(pl, c.get('equipo'))}: suéltelo en un lugar libre del lienzo "
                                          "o sobre esa etapa.", recalcular=False)
        dest = d.get("destino")
        if dest and dest != c.get("equipo"):                 # PAT 140 g: soltado sobre otra etapa del mismo tipo
            c2, motivo = adaptar_candidato(pl, c, dest, candidatos, economia, forzar=libre)
            if c2 is None:
                return dict(ok=False, mensaje=f"No se aplicó {c.get('etiqueta') or c.get('modelo')} a la {nombre_etapa(pl, dest)}: {motivo}.",
                            recalcular=False)
            r = aplicar_candidato(pl, hist, c2)
            msg = r["mensaje"] + (f" No calza: {motivo}; la advertencia lo marca si no alcanza la carga." if motivo and r["ok"] else "")
            return dict(ok=r["ok"], mensaje=msg, recalcular=False, id=dest)
        r = aplicar_candidato(pl, hist, c, d.get("pos"))
        return dict(ok=r["ok"], mensaje=r["mensaje"], recalcular=False, id=c.get("equipo"))
    if e == "generar":
        r = generar_automaticamente(pl, hist, candidatos)
        return dict(ok=r["ok"], mensaje=r["mensaje"], recalcular=False)
    if e == "quitar":
        r = quitar_todo(pl, hist)
        return dict(ok=r["ok"], mensaje=r["mensaje"], recalcular=False)
    if e == "mover":
        return mover(pl, hist, d.get("id"), d.get("x"), d.get("y"))
    if e in ("deshacer", "rehacer"):
        return LZ.aplicar_con_historial(pl, dict(evento=e, datos={}), hist)
    return dict(ok=False, mensaje=f"Evento desconocido en la Planta real: {e}.", recalcular=False)
