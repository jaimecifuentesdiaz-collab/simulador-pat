"""Restricción de precedencia al conectar equipos en el lienzo (PAT 135, pedida por Jaime el 04-11-2026).

Antes solo se exigía que el tipo de corriente fuera compatible, así que la recepción de tomate se podía conectar directo a la
llenadora aséptica. Ahora el material de cada rubro pasa por una cadena ordenada de estados (tabla estados_material del
mantenedor: rubro, orden, código, nombre y la etapa que produce ese estado) y cada tipo de equipo declara qué estados acepta en
su entrada de producto y qué estado entrega (tabla precedencia: rubro, tipo, acepta, entrega, opcional). Una conexión de
producto es válida si el estado que sale del origen está entre los que acepta el destino.

Reglas:
- Un tipo sin fila en el rubro (bombas, estanques, intercambiadores, válvulas y demás equipos generales), o con «entrega»
  vacía, deja pasar el estado: su salida tiene el estado de lo que le entra (si no le entra nada, el estado es desconocido y
  no se restringe).
- «acepta» vacío o «*» significa cualquier estado. La fila del rubro «*» vale para todos los rubros que no tengan la suya.
- Una etapa opcional se puede saltar: quien acepta lo que ella entrega acepta también lo que ella acepta.
- Solo se revisan las corrientes de producto o biomasa; los subproductos (descarte, tomasa, rechazo, aserrín) y los servicios
  quedan libres, como antes.
- Si la planta es de un rubro sin estados, o no hay tabla, todo funciona como antes.

El motor no lee la base: recibe la tabla (Precedencia o el diccionario de datos/mantenedor.tabla_precedencia) como argumento
o como atributo «precedencia» de la planta, que la interfaz carga desde el mantenedor.
"""
from __future__ import annotations

PRODUCTO = ("producto", "biomasa")      # tipos de corriente que llevan el material del proceso
CUALQUIERA = "*"


def lista_codigos(v) -> tuple:
    """«a, b» o ["a", "b"] → ("a", "b"); vacío → ()."""
    if v is None:
        return ()
    if isinstance(v, str):
        v = v.replace(";", ",").split(",")
    return tuple(s for s in (str(x).strip() for x in v) if s)


def unir_y(xs) -> str:
    """["a", "b", "c"] → «a, b y c»."""
    xs = [str(x) for x in xs if x]
    if len(xs) <= 1:
        return "".join(xs)
    return ", ".join(xs[:-1]) + " y " + xs[-1]


class Precedencia:
    """Tabla de estados y precedencia ya leída (desde la base o desde la semilla)."""

    def __init__(self, estados=(), precedencia=(), libre: bool = False):
        self.estados: dict[str, list[dict]] = {}
        for e in estados or ():
            r = str(e.get("rubro") or "").strip(); c = str(e.get("codigo") or "").strip()
            if not r or not c:
                continue
            self.estados.setdefault(r, []).append(dict(rubro=r, orden=float(e.get("orden") or 0), codigo=c,
                                                       nombre=str(e.get("nombre") or c), etapa=str(e.get("etapa") or "")))
        for r in self.estados:
            self.estados[r].sort(key=lambda x: x["orden"])
        self.filas: dict[tuple, dict] = {}
        for f in precedencia or ():
            r = str(f.get("rubro") or "").strip(); t = str(f.get("tipo") or "").strip()
            if not r or not t:
                continue
            self.filas[(r, t)] = dict(acepta=lista_codigos(f.get("acepta")), entrega=str(f.get("entrega") or "").strip(),
                                      opcional=bool(f.get("opcional")))
        self.libre = bool(libre)

    @classmethod
    def desde(cls, t):
        """Precedencia, diccionario {estados, precedencia, libre} o None."""
        if t is None or isinstance(t, cls):
            return t
        return cls(t.get("estados"), t.get("precedencia"), t.get("libre", False))

    # ---------------------------------------------------------------- consultas
    def activa(self, rubro) -> bool:
        return bool(self.estados.get(rubro))

    def estado(self, rubro, codigo) -> dict | None:
        return next((e for e in self.estados.get(rubro, ()) if e["codigo"] == codigo), None)

    def nombre(self, rubro, codigo) -> str:
        e = self.estado(rubro, codigo)
        return e["nombre"] if e else codigo

    def orden(self, rubro, codigo):
        e = self.estado(rubro, codigo)
        return e["orden"] if e else None

    def fila(self, rubro, tipo) -> dict | None:
        return self.filas.get((rubro, tipo)) or self.filas.get((CUALQUIERA, tipo))

    def entrega(self, rubro, tipo) -> str | None:
        """Estado que entrega un tipo de equipo; None si deja pasar el estado."""
        f = self.fila(rubro, tipo)
        return f["entrega"] if f and f["entrega"] else None

    def acepta(self, rubro, tipo) -> set | None:
        """Estados que acepta la entrada de producto de un tipo, con las etapas opcionales saltadas. None = cualquiera."""
        f = self.fila(rubro, tipo)
        if f is None or not f["acepta"] or CUALQUIERA in f["acepta"]:
            return None
        s = set(f["acepta"]); cambio = True
        while cambio:                           # quien acepta lo que entrega una etapa opcional acepta también lo que ella acepta
            cambio = False
            for (r, _t), g in self.filas.items():
                if r in (rubro, CUALQUIERA) and g["opcional"] and g["entrega"] in s and g["acepta"] and CUALQUIERA not in g["acepta"]:
                    nuevos = set(g["acepta"]) - s
                    if nuevos:
                        s |= nuevos; cambio = True
        return s

    def faltan(self, rubro, desde, hasta) -> list[str]:
        """Etapas que producen los estados posteriores a «desde» hasta «hasta» inclusive (en el orden de la cadena). Las que
        se pueden saltar llevan «(opcional)»."""
        a, b = self.orden(rubro, desde), self.orden(rubro, hasta)
        if a is None or b is None:
            return []
        opc = {g["entrega"] for (r, _t), g in self.filas.items() if r in (rubro, CUALQUIERA) and g["opcional"]}
        out = []
        for e in self.estados.get(rubro, ()):
            if a < e["orden"] <= b:
                et = (e["etapa"] or e["nombre"]) + (" (opcional)" if e["codigo"] in opc else "")
                if et not in out:
                    out.append(et)
        return out

    def cadena(self, rubro) -> str:
        """«tomate fresco → tomate lavado y seleccionado → …» para la ayuda y el informe."""
        return " → ".join(e["nombre"] for e in self.estados.get(rubro, ()))


def regla(pl, precedencia=None) -> Precedencia | None:
    """Tabla que rige la planta (argumento o atributo «precedencia»), o None si no hay o el rubro no tiene estados."""
    t = Precedencia.desde(precedencia if precedencia is not None else getattr(pl, "precedencia", None))
    return t if t is not None and t.activa(pl.rubro) else None


def _tipo_puerto(ps, nombre):
    return next((p.tipo for p in ps if p.nombre == nombre), None)


def de_producto(pl, c) -> bool:
    """La conexión lleva el material del proceso (sale de un puerto de producto o biomasa y entra en otro igual)."""
    a, b = pl.equipos.get(c.origen), pl.equipos.get(c.destino)
    return (a is not None and b is not None and _tipo_puerto(a.salidas, c.puerto_origen) in PRODUCTO
            and _tipo_puerto(b.entradas, c.puerto_destino) in PRODUCTO)


def estados_salida(pl, t: Precedencia, equipo: str, _vistos=None) -> frozenset | None:
    """Estados del material que sale de un equipo. None si no se sabe (equipo de paso sin nada aguas arriba)."""
    eq = pl.equipos[equipo]
    e = t.entrega(pl.rubro, eq.tipo)
    if e:
        return frozenset([e])
    vistos = (_vistos or frozenset()) | {equipo}
    out = set()
    for c in pl.conexiones:
        if c.destino == equipo and c.origen not in vistos and de_producto(pl, c):
            s = estados_salida(pl, t, c.origen, vistos)
            if s:
                out |= s
    return frozenset(out) or None


def _quien(eq) -> str:
    return f"{eq.id} · {eq.nombre}"


def revisar(pl, t: Precedencia, origen, puerto_origen, destino, puerto_destino) -> str | None:
    """None si la conexión cumple la precedencia; si no, el mensaje que nombra lo que necesita el destino y las etapas que faltan."""
    a, b = pl.equipos[origen], pl.equipos[destino]
    if _tipo_puerto(a.salidas, puerto_origen) not in PRODUCTO or _tipo_puerto(b.entradas, puerto_destino) not in PRODUCTO:
        return None
    acepta = t.acepta(pl.rubro, b.tipo)
    if acepta is None:
        return None
    sale = estados_salida(pl, t, origen)
    if not sale:
        return None
    malos = sorted((s for s in sale if s not in acepta), key=lambda s: (t.orden(pl.rubro, s) is None, t.orden(pl.rubro, s) or 0))
    if not malos:
        return None
    s = malos[0]
    conocidos = [x for x in acepta if t.orden(pl.rubro, x) is not None]
    if not conocidos:
        return f"{_quien(b)} no acepta {t.nombre(pl.rubro, s)}, que entrega {_quien(a)}."
    nec = min(conocidos, key=lambda x: t.orden(pl.rubro, x))
    msg = f"{_quien(b)} necesita {t.nombre(pl.rubro, nec)}; {_quien(a)} entrega {t.nombre(pl.rubro, s)}."
    os_, on = t.orden(pl.rubro, s), t.orden(pl.rubro, nec)
    if os_ is None:
        return msg + " Ese estado no es de la cadena de este rubro."
    if os_ < on:
        f = t.faltan(pl.rubro, s, nec)
        return msg + (f" Faltan: {unir_y(f)}." if f else "")
    return msg + " Ese material ya pasó por esa etapa: conecte este equipo antes en la línea."


def violaciones(pl, precedencia=None) -> list[tuple]:
    """Conexiones existentes que no cumplen la precedencia: [(índice, conexión, mensaje)]."""
    t = regla(pl, precedencia)
    if t is None:
        return []
    out = []
    for i, c in enumerate(pl.conexiones):
        if c.origen in pl.equipos and c.destino in pl.equipos and de_producto(pl, c):
            m = revisar(pl, t, c.origen, c.puerto_origen, c.destino, c.puerto_destino)
            if m:
                out.append((i, c, m))
    return out


# ---------------------------------------------------------------- PAT 136 (T22): precedencia en los equipos de las 10 plantas
# Punto 8 de los comentarios del profesor Torres (13-11-2026): «restricciones en todos los equipos». La tabla del mantenedor trae
# los cuatro rubros de PAT 135; los seis tipos de planta nuevos (catalogos/plantas_genericas.py) traen sus estados del material y su
# cadena de operaciones. tabla_plantas() las junta en una sola tabla para el motor, sin cambiar las filas que ya existían.
PREFIJO_SIMPLE = "simple_"      # versiones de balance simplificado de catalogos/iso_generico.py


def _filas_planta(planta_id: str) -> list[dict]:
    """Filas de precedencia de un tipo de planta: las de su cadena, las de sus alternativas y las de sus versiones simplificadas.
    Un estado de entrada que ninguna operación entrega (la rama del licor de prensa en la harina de pescado) se acepta también
    con el estado anterior de la cadena: el equipo que lo produce entrega una sola corriente (Supuesto declarado)."""
    from ..catalogos import plantas_genericas as PG
    p = PG.planta(planta_id)
    filas = [dict(f) for f in PG.precedencia(planta_id)]
    entregados = {o["salida"] for o in p["operaciones"]}
    codigos = [e["codigo"] for e in PG.estados_material(planta_id)]
    for f, o in zip(filas, p["operaciones"]):
        acepta = list(lista_codigos(f["acepta"]))
        for c in list(acepta):
            if c not in entregados and c in codigos and codigos.index(c) > 0:
                previo = codigos[codigos.index(c) - 1]
                if previo not in acepta:
                    acepta.append(previo)
                    f["fuente"] = (f.get("fuente") or "") + (f"; PAT 136: «{c}» sale del mismo equipo que «{previo}», que entrega una sola "
                                                             "corriente (Supuesto de la planta automática)")
        f["acepta"] = ", ".join(acepta)
    tipos = {f["tipo"] for f in filas}
    extra = []
    for f, o in zip(list(filas), p["operaciones"]):
        # PAT 143 b: los equivalentes (equipos con modelo propio del escenario del rubro) llevan la misma fila que las alternativas
        for alt in tuple(o.get("alternativas") or ()) + tuple(o.get("equivalentes") or ()):
            if alt not in tipos:
                extra.append(dict(f, tipo=alt)); tipos.add(alt)
    for f in filas + extra:
        s = PREFIJO_SIMPLE + f["tipo"]
        if s not in tipos:
            extra.append(dict(f, tipo=s)); tipos.add(s)
    return filas + extra


def tabla_plantas(base=None) -> dict:
    """Tabla {estados, precedencia, libre} con los rubros de la base (la del mantenedor; sin ella, su semilla) más los tipos de planta
    de catalogos/plantas_genericas.py cuyo rubro no tenga estados en la base. A los rubros de la base se les agregan solo las filas
    de las versiones simplificadas que falten. Lista para Precedencia.desde()."""
    from ..catalogos import plantas_genericas as PG
    if base is None:
        from ..datos.mantenedor import semilla_estados, semilla_precedencia
        base = dict(estados=semilla_estados(), precedencia=semilla_precedencia(), libre=False)
    elif isinstance(base, Precedencia):
        base = dict(estados=[e for es in base.estados.values() for e in es],
                    precedencia=[dict(rubro=r, tipo=t, acepta=", ".join(f["acepta"]), entrega=f["entrega"], opcional=f["opcional"])
                                 for (r, t), f in base.filas.items()], libre=base.libre)
    estados = [dict(e) for e in base.get("estados") or ()]
    filas = [dict(f) for f in base.get("precedencia") or ()]
    con_estados = {str(e.get("rubro") or "").strip() for e in estados}
    claves = {(str(f.get("rubro") or "").strip(), str(f.get("tipo") or "").strip()) for f in filas}
    for pid, p in PG.PLANTAS.items():
        r = p["rubro"]
        if r not in con_estados:
            estados += PG.estados_material(pid); con_estados.add(r)
            for f in _filas_planta(pid):
                if (r, f["tipo"]) not in claves:
                    filas.append(f); claves.add((r, f["tipo"]))
        else:
            for f in [f for f in filas if str(f.get("rubro") or "").strip() == r]:
                s = PREFIJO_SIMPLE + str(f.get("tipo") or "").strip()
                if (r, s) not in claves:
                    filas.append(dict(f, tipo=s)); claves.add((r, s))
    return dict(estados=estados, precedencia=filas, libre=bool(base.get("libre", False)))


def de_planta(planta_id: str, base=None) -> Precedencia:
    """Precedencia lista para el motor con los rubros de la base y los 10 tipos de planta."""
    return Precedencia.desde(tabla_plantas(base))


def cobertura(t: Precedencia | dict | None = None) -> list[dict]:
    """Por tipo de planta: cuántas operaciones tienen fila de precedencia en su rubro y cuáles faltan (para la prueba y la ayuda)."""
    from ..catalogos import plantas_genericas as PG
    t = Precedencia.desde(t) if t is not None else Precedencia.desde(tabla_plantas())
    out = []
    for pid, p in PG.PLANTAS.items():
        faltan = [o["tipo_equipo"] for o in p["operaciones"] if t.fila(p["rubro"], o["tipo_equipo"]) is None]
        out.append(dict(planta_id=pid, rubro=p["rubro"], operaciones=len(p["operaciones"]), con_fila=len(p["operaciones"]) - len(faltan),
                        faltan=faltan, activa=t.activa(p["rubro"]), cadena=t.cadena(p["rubro"])))
    return out


def mensaje_claro(m: str | None) -> str | None:
    """Mensaje de una conexión rechazada, para la interfaz: dice qué hacer (el motor lo devuelve sin cambiar su texto)."""
    if not m:
        return None
    return "No se conectó. " + m + " Conecte primero los equipos de las etapas que faltan, en el orden del proceso."
