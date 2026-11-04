"""Edición interactiva de la planta desde el lienzo de la pestaña Diseño (simulador de planta, PAT 128).

Dos piezas sin interfaz, que se pueden probar solas:
- aplicar_evento(pl, ev): aplica a la planta un evento del lienzo (agregar, mover, conectar, reparto, quitar_conexion,
  quitar_equipo, parametro, renombrar, global) y dice si hay que recalcular.
- datos_lienzo(pl, ...): arma lo que el lienzo necesita para dibujar la planta y sus resultados.
PAT 133: Historial (deshacer y rehacer con tope), instantanea y restaurar (estado completo de la planta en JSON),
aplicar_con_historial (aplica un evento y apila el estado anterior si la planta cambió) y duplicar_equipos (copiar y pegar).
PAT 134: instrumentos ISA-5.1 y elementos de lazo ISA-5.4 en el lienzo (eventos agregar_instrumento, instrumento,
mover_instrumento, quitar_instrumento, conectar_senal, senal y quitar_senal; ver pat_sim.motor.instrumentacion). Un parámetro
escrito fuera de su rango se acota y vuelve con el aviso «Mínimo …» o «Máximo …».
Además resolver_parcial(pl): si la planta no se puede resolver (por ejemplo, un equipo recién agregado sin alimentación),
resuelve la parte que sí tiene alimentación para que el lienzo siga mostrando los flujos; la planta queda sin resolver.
PAT 135: restricción de precedencia al conectar (motor/precedencia.py). Si la planta trae la tabla (argumento «precedencia» o
atributo pl.precedencia, que la interfaz carga desde el mantenedor), una conexión de producto se rechaza cuando el estado del
material que sale del origen no está entre los que acepta el destino, con un mensaje que nombra las etapas que faltan. La
misma regla rige «Secuencia sugerida» y «Diagnóstico». Sin tabla, o con «Permitir conexiones libres», todo es como antes.
"""
from __future__ import annotations
import json, math, time
from .planta import Planta, TIPOS_SERVICIO
from .corrientes import TIPOS as TIPOS_CORRIENTE
from ..simbolos import iso10628
from .equipos import OPCIONALES
from . import instrumentacion as IN
from ..simbolos import isa51
from . import precedencia as PR          # PAT 135

# Prefijo del número de corriente de servicio (las corrientes de proceso se numeran 1, 2, 3...)
PREFIJO_SERVICIO = {"vapor": "V", "calor": "Q", "electricidad": "E", "gas": "G", "aire": "A"}
TAM = 64           # tamaño del símbolo en el lienzo (igual que diagrama.py)
GRILLA = 20


def compatibles(tipo_salida: str, tipo_entrada: str) -> bool:
    """Una salida se puede conectar a una entrada del mismo tipo de corriente; un subproducto puede volver a proceso."""
    if tipo_salida == tipo_entrada:
        return True
    return tipo_salida == "subproducto" and tipo_entrada in ("producto", "biomasa")


def siguiente_id(pl: Planta, letra: str) -> str:
    n = 1
    while f"{letra}{n}" in pl.equipos:
        n += 1
    return f"{letra}{n}"


def _siguiente_numero(pl: Planta, tipo: str) -> str:
    pref = PREFIJO_SERVICIO.get(tipo, "") if tipo in TIPOS_SERVICIO else ""
    usados = set()
    for c in pl.conexiones:
        n = c.nombre or ""
        if pref and n.startswith(pref) and n[len(pref):].isdigit():
            usados.add(int(n[len(pref):]))
        elif not pref and n.isdigit():
            usados.add(int(n))
    return f"{pref}{max(usados, default=0) + 1}"


def _clave_conexion(c) -> str:
    return f"{c.origen}.{c.puerto_origen}>{c.destino}.{c.puerto_destino}"


def _buscar_conexion(pl: Planta, d: dict):
    if d.get("clave"):
        for i, c in enumerate(pl.conexiones):
            if _clave_conexion(c) == d["clave"]:
                return i, c
        raise ValueError("La conexión ya no existe")
    i = int(d["indice"])
    if not 0 <= i < len(pl.conexiones):
        raise ValueError("La conexión ya no existe")
    return i, pl.conexiones[i]


def _convertir(p, valor):
    """Convierte el valor que llega del lienzo al tipo del parámetro y lo deja dentro de su rango."""
    actual = p.valor
    if isinstance(actual, bool):
        return bool(valor)
    if valor is None or valor == "":
        if p.clave in OPCIONALES:
            return None
        raise ValueError(f"{p.nombre}: falta el valor")
    if isinstance(actual, str):
        return str(valor)
    v = float(valor)
    if not math.isfinite(v):
        raise ValueError(f"{p.nombre}: valor no válido")
    if p.minimo is not None:
        v = max(v, float(p.minimo))
    if p.maximo is not None:
        v = min(v, float(p.maximo))
    if p.clave in OPCIONALES and v <= 0:
        return None
    return int(round(v)) if isinstance(actual, int) else v


def _g(v) -> str:
    """Número corto en formato chileno (0.03 → 0,03), para los avisos de rango."""
    return f"{float(v):.6g}".replace(".", ",")


def aviso_rango(p, pedido, usado) -> str | None:
    """PAT 134: si el valor escrito quedó fuera del rango del parámetro, el aviso que ve el usuario y el valor que usó el motor."""
    try:
        v = float(pedido)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or isinstance(p.valor, bool) or usado is None:
        return None
    if p.minimo is not None and v < float(p.minimo):
        return f"{p.nombre}: Mínimo {_g(p.minimo)}. El motor usa {_g(usado)} y no {_g(v)}."
    if p.maximo is not None and v > float(p.maximo):
        return f"{p.nombre}: Máximo {_g(p.maximo)}. El motor usa {_g(usado)} y no {_g(v)}."
    return None


def _regla_conectar(pl: Planta, precedencia=None):
    """PAT 135: tabla de precedencia que restringe las conexiones (None si no hay, si el rubro no tiene estados o si son libres)."""
    t = PR.regla(pl, precedencia)
    return None if t is None or t.libre else t


def aplicar_evento(pl: Planta, ev: dict, tipos: dict | None = None, precedencia=None) -> dict:
    """Aplica un evento del lienzo a la planta. Devuelve {ok, mensaje, recalcular}.

    Los errores de edición (puerto inexistente, tipos incompatibles, ciclo, precedencia) no lanzan excepción: vuelven con
    ok=False y la planta queda como estaba. precedencia: tabla de motor/precedencia.py (si no, pl.precedencia o ninguna).
    """
    if tipos is None:
        from ..catalogos.registro import TIPOS as tipos
    e = ev.get("evento"); d = ev.get("datos") or {}
    try:
        if e == "agregar":
            cls = tipos[d["tipo"]]
            nid = siguiente_id(pl, cls.iso_letra)
            x = round(float(d.get("x", 40)) / GRILLA) * GRILLA; y = round(float(d.get("y", 120)) / GRILLA) * GRILLA
            pl.agregar(cls(nid, cls.nombre_tipo, x, y))
            return dict(ok=True, mensaje=f"Agregado {nid} · {cls.nombre_tipo}. Conéctelo arrastrando desde un puerto de salida.",
                        recalcular=True, id=nid)
        if e == "mover":
            eq = pl.equipos[d["id"]]; x0, y0 = float(eq.x), float(eq.y)
            eq.x = round(float(d["x"]) / GRILLA) * GRILLA; eq.y = round(float(d["y"]) / GRILLA) * GRILLA
            IN.desplazar_de_equipo(pl, eq.id, eq.x - x0, eq.y - y0)      # PAT 134: sus instrumentos lo acompañan
            return dict(ok=True, mensaje=None, recalcular=False)
        if e == "conectar":
            o, po, de, pd_ = d["origen"], d["puerto_origen"], d["destino"], d["puerto_destino"]
            if o == de:
                raise ValueError("Un equipo no se puede conectar consigo mismo")
            a, b = pl.equipos[o], pl.equipos[de]
            ps = next((p for p in a.salidas if p.nombre == po), None); pe = next((p for p in b.entradas if p.nombre == pd_), None)
            if ps is None or pe is None:
                raise ValueError("Puerto inexistente")
            if not compatibles(ps.tipo, pe.tipo):
                raise ValueError(f"Tipos incompatibles: la salida {o}.{po} es {TIPOS_CORRIENTE[ps.tipo][0].lower()} "
                                 f"y la entrada {de}.{pd_} espera {TIPOS_CORRIENTE[pe.tipo][0].lower()}")
            if any((c.origen, c.puerto_origen, c.destino, c.puerto_destino) == (o, po, de, pd_) for c in pl.conexiones):
                raise ValueError(f"Ya existe la conexión {o}.{po} → {de}.{pd_}")
            regla = _regla_conectar(pl, precedencia)              # PAT 135: precedencia de los estados del material
            if regla is not None:
                m_ = PR.revisar(pl, regla, o, po, de, pd_)
                if m_:
                    raise ValueError(m_)
                antes_ = {_clave_conexion(c_) for _, c_, _m in PR.violaciones(pl, regla)}
            usado = sum(c.reparto for c in pl.conexiones if c.origen == o and c.puerto_origen == po)
            rep = d.get("reparto")
            rep = float(rep) if rep is not None else (100.0 - usado if usado < 99.99 else 100.0)
            nombre = (d.get("nombre") or "").strip() or _siguiente_numero(pl, ps.tipo)
            c = pl.conectar(o, po, de, pd_, max(0.0, min(100.0, rep)), nombre)
            if not pl.es_servicio(c):
                try:
                    pl.orden()
                except ValueError:
                    pl.conexiones.remove(c)
                    raise ValueError("Esa conexión cierra un ciclo de corrientes de proceso; declare la recirculación como especificación")
            if regla is not None:                                  # PAT 135: un equipo de paso lleva el estado aguas abajo
                nuevas = [m for _, c_, m in PR.violaciones(pl, regla) if _clave_conexion(c_) not in antes_]
                if nuevas:
                    pl.conexiones.remove(c)
                    raise ValueError(nuevas[0])
            msg = f"Conectado {o}.{po} → {de}.{pd_} (corriente {nombre}, {c.reparto:g} %)."
            if usado + c.reparto > 100.01:
                msg += f" El puerto {o}.{po} reparte ahora {usado + c.reparto:g} %: ajuste los repartos."
            return dict(ok=True, mensaje=msg, recalcular=True)
        if e == "reparto":
            _, c = _buscar_conexion(pl, d)
            if d.get("reparto") is not None:
                c.reparto = max(0.0, min(100.0, float(d["reparto"])))
            if d.get("nombre") is not None:
                c.nombre = str(d["nombre"]).strip()
            return dict(ok=True, mensaje=None, recalcular=True)
        if e == "quitar_conexion":
            i, c = _buscar_conexion(pl, d)
            pl.conexiones.pop(i)
            IN.limpiar(pl)                                               # PAT 134: y las líneas de señal que llegaban a ella
            return dict(ok=True, mensaje=f"Quitada la conexión {c.origen}.{c.puerto_origen} → {c.destino}.{c.puerto_destino}.", recalcular=True)
        if e == "quitar_equipo":
            q = d["id"]; nombre = pl.equipos[q].nombre
            pl.quitar(q)
            pl.instrumentos = [i for i in pl.instrumentos if i.equipo != q]
            pl.especs = [s for s in pl.especs if q not in (s.equipo_var, s.equipo_obj)]
            IN.limpiar(pl)
            return dict(ok=True, mensaje=f"Quitado {q} · {nombre} con sus conexiones.", recalcular=True)
        if e == "parametro":
            eq = pl.equipos[d["id"]]; clave = d["clave"]
            if clave not in eq.params:
                raise ValueError(f"{eq.id} no tiene el parámetro {clave}")
            if any(s.equipo_var == eq.id and s.param == clave for s in pl.especs):
                raise ValueError(f"{eq.params[clave].nombre} lo calcula la especificación de diseño")
            usado = _convertir(eq.params[clave], d.get("valor"))
            eq.set(clave, usado)
            av = aviso_rango(eq.params[clave], d.get("valor"), usado)     # PAT 134: el campo muestra lo que usó el motor
            return dict(ok=True, mensaje=av, recalcular=True, tipo="aviso" if av else None)
        if e == "renombrar":
            eq = pl.equipos[d["id"]]; n = str(d.get("nombre", "")).strip()
            if n:
                eq.nombre = n
            return dict(ok=True, mensaje=None, recalcular=False)
        if e == "global":
            clave = d["clave"]
            if clave not in pl.globales:
                raise ValueError(f"Variable de planta desconocida: {clave}")
            pl.globales[clave] = float(d["valor"])
            return dict(ok=True, mensaje=None, recalcular=True)
        if e == "espec":
            es = pl.especs[int(d["indice"])]
            es.valor = float(d["valor"])
            return dict(ok=True, mensaje=None, recalcular=True)
        if e == "alimentacion":
            eq = pl.equipos[d["id"]]; t_h = max(0.001, float(d["valor"]))
            if "temporada_t" in eq.params and hasattr(eq, "horas"):
                eq.set("temporada_t", t_h * eq.horas())
            elif "carga_t_h" in eq.params:
                eq.set("carga_t_h", t_h)
            else:
                raise ValueError(f"{eq.id} no tiene una alimentación editable")
            return dict(ok=True, mensaje=None, recalcular=True)
        if e == "secuencia":
            n = secuencia_sugerida(pl, precedencia)
            return dict(ok=True, mensaje=f"Secuencia sugerida: {n} conexión(es) nuevas." if n else
                        "Secuencia sugerida: no quedaban entradas libres que conectar.", recalcular=n > 0)
        if e == "capacidades":
            n = asignar_capacidades(pl, float(d.get("holgura", 10.0)) / 100, bool(d.get("solo_vacias", True)))
            return dict(ok=True, mensaje=f"Capacidad nominal asignada a {n} equipo(s): carga actual + {float(d.get('holgura', 10.0)):g} % "
                                         "(categoría Supuesto). Baje la de un equipo para ver cómo pasa a naranjo, a rojo y a sobrecarga." if n else
                        "No hay equipos con carga y sin capacidad nominal (resuelva la planta o borre una capacidad).", recalcular=n > 0)
        if e == "duplicar":                                   # PAT 133: copiar y pegar o botón Duplicar
            ids = d.get("ids") or ([d["id"]] if d.get("id") else [])
            mapa = duplicar_equipos(pl, ids, float(d.get("dx", 100)), float(d.get("dy", 100)))
            nuevos = list(mapa.values())
            return dict(ok=True, mensaje=f"Duplicado {', '.join(f'{a} → {b}' for a, b in mapa.items())} con sus parámetros "
                                         "(sin conexiones externas). Conéctelo arrastrando desde un puerto.",
                        recalcular=True, id=nuevos[0], ids=nuevos)
        # ------------------------------------------------ PAT 134: instrumentos ISA-5.1 y elementos de lazo ISA-5.4
        if e == "agregar_instrumento":
            ins = IN.agregar(pl, d["clave"], d.get("x", 100), d.get("y", 60), d.get("equipo") or None, d.get("corriente") or None)
            k = IN.ident(ins); nm = isa51.ELEMENTOS[d["clave"]]["nombre"]
            que = "sus letras ISA-5.1" if isa51.valida_isa51(ins.simbolo) else "su código"
            return dict(ok=True, mensaje=f"Agregado {k} · {nm}" + (f", unido a {ins.equipo}" if ins.equipo else "") +
                        f". Escriba en Propiedades {que}, el número de lazo, la ubicación y la descripción; conéctelo arrastrando "
                        "desde el punto azul de su borde.", recalcular=False, id=k, sel="ins")
        if e == "instrumento":
            cambios = {c: v for c, v in d.items() if c in ("letras", "numero", "ubicacion", "descripcion", "equipo", "parametro", "elemento_final", "simbolo")}
            nid = IN.editar(pl, d["id"], cambios)
            msg = f"{nid}: {IN.lectura(IN.buscar(pl, nid))}." if nid != d["id"] or "letras" in cambios else None
            return dict(ok=True, mensaje=msg, recalcular=False, id=nid, sel="ins")
        if e == "mover_instrumento":
            IN.mover(pl, d["id"], d["x"], d["y"])
            return dict(ok=True, mensaje=None, recalcular=False)
        if e == "quitar_instrumento":
            IN.quitar(pl, d["id"])
            return dict(ok=True, mensaje=f"Quitado el instrumento {d['id']} con sus líneas de señal.", recalcular=False)
        if e == "conectar_senal":
            clave = IN.conectar(pl, d["origen"], d["tipo"], d["destino"], d.get("senal") or "electrica", d.get("parametro"))
            nm = isa51.SENALES[d.get("senal") or "electrica"][0].lower()
            return dict(ok=True, mensaje=f"Línea de {nm} de {d['origen']} a {IN.nombre_destino(pl, d['tipo'], d['destino'])}.", recalcular=False,
                        id=d["origen"], sel="ins")
        if e == "senal":
            IN.editar_senal(pl, d["clave"], {c: v for c, v in d.items() if c in ("senal", "parametro")})
            return dict(ok=True, mensaje=None, recalcular=False)
        if e == "quitar_senal":
            IN.quitar_senal(pl, d["clave"])
            return dict(ok=True, mensaje="Quitada la línea de señal.", recalcular=False)
        raise ValueError(f"Evento desconocido: {e}")
    except KeyError as k:
        return dict(ok=False, mensaje=f"No existe {k}", recalcular=False)
    except (ValueError, TypeError) as x:
        return dict(ok=False, mensaje=str(x), recalcular=False)


def secuencia_sugerida(pl: Planta, precedencia=None) -> int:
    """Como «Secuencia sugerida» del simulador del profesor: conecta cada entrada de proceso libre con la salida
    compatible libre del equipo anterior (en el orden en que se agregaron) y las entradas de vapor o calor libres con la
    caldera o el generador de calor. No toca las conexiones que ya existen.
    PAT 135: con tabla de precedencia, elige el equipo cuyo material acepta la entrada (primero los anteriores, después los
    que se agregaron más tarde) y prueba el siguiente si una conexión se rechaza."""
    eqs = list(pl.equipos.values()); n = 0
    regla = _regla_conectar(pl, precedencia)
    def libre(eq, p):
        return sum(c.reparto for c in pl.conexiones if c.origen == eq.id and c.puerto_origen == p.nombre) < 99.99
    for i, eq in enumerate(eqs):
        if eq.tipo.startswith("caldera"):
            continue
        for p in eq.entradas:
            if any(c.destino == eq.id and c.puerto_destino == p.nombre for c in pl.conexiones):
                continue
            if p.tipo in ("vapor", "calor"):
                fuente = next(((a, q) for a in eqs if a.tipo.startswith("caldera") for q in a.salidas if q.tipo == p.tipo), None)
            elif p.tipo in TIPOS_SERVICIO:
                continue
            elif regla is not None:                                # PAT 135
                cands = [(a, q) for a in list(reversed(eqs[:i])) + eqs[i + 1:] if not a.tipo.startswith("caldera") and a.id != eq.id
                         for q in a.salidas if compatibles(q.tipo, p.tipo) and q.tipo != "subproducto" and libre(a, q)
                         and PR.revisar(pl, regla, a.id, q.nombre, eq.id, p.nombre) is None]
                cands.sort(key=lambda aq: PR.estados_salida(pl, regla, aq[0].id) is None)    # primero los de estado conocido
                for a, q in cands:
                    r = aplicar_evento(pl, dict(evento="conectar", datos=dict(origen=a.id, puerto_origen=q.nombre, destino=eq.id,
                                                                            puerto_destino=p.nombre)), precedencia=precedencia)
                    if r["ok"]:
                        n += 1
                        break
                continue
            else:
                fuente = next(((a, q) for a in reversed(eqs[:i]) if not a.tipo.startswith("caldera") for q in a.salidas
                               if compatibles(q.tipo, p.tipo) and q.tipo != "subproducto" and libre(a, q)), None)
            if fuente is None:
                continue
            a, q = fuente
            r = aplicar_evento(pl, dict(evento="conectar", datos=dict(origen=a.id, puerto_origen=q.nombre, destino=eq.id, puerto_destino=p.nombre)),
                               precedencia=precedencia)
            n += 1 if r["ok"] else 0
    return n


def asignar_capacidades(pl: Planta, holgura: float = 0.10, solo_vacias: bool = True) -> int:
    """Capacidad nominal = carga actual × (1 + holgura), redondeada hacia arriba a 0,1 t/h (supuesto del diseñador)."""
    n = 0
    for eq in pl.equipos.values():
        if "capacidad" not in eq.params or eq.resultado is None:
            continue
        if solo_vacias and eq.params["capacidad"].valor:
            continue
        carga = eq.resultado.detalle.get("carga_t_h")
        if not carga:
            continue
        eq.set("capacidad", math.ceil(float(carga) * (1 + holgura) * 10) / 10, categoria="Supuesto",
               fuente=f"Asignada en el simulador: carga de diseño × {1 + holgura:.2f}".replace(".", ","),
               justificacion="Holgura de diseño elegida por el usuario; no es un dato de la planta")
        n += 1
    return n


# ---------------------------------------------------------------- PAT 133: copiar, pegar, deshacer y rehacer

def duplicar_equipos(pl: Planta, ids, dx: float = 100, dy: float = 100) -> dict:
    """Copia los equipos ids con todos sus parámetros (valor, categoría, fuente y justificación), con identificador nuevo
    según su letra ISO 10628 y desplazados (dx, dy) en la grilla. Copia las conexiones y especificaciones internas (entre
    equipos copiados) y no las externas ni los instrumentos. Devuelve {id original: id nuevo}."""
    from .planta import Conexion, EspecDiseno
    from .equipos import Parametro
    ids = [i for i in dict.fromkeys(ids or [])]
    if not ids:
        raise ValueError("Seleccione un equipo para duplicarlo")
    for i in ids:
        if i not in pl.equipos:
            raise ValueError(f"El equipo {i} ya no existe")
    mapa = {}
    for i in ids:
        eq = pl.equipos[i]; cls = type(eq)
        nid = siguiente_id(pl, cls.iso_letra)
        x = round((float(eq.x) + dx) / GRILLA) * GRILLA; y = round((float(eq.y) + dy) / GRILLA) * GRILLA
        nuevo = cls(nid, eq.nombre, max(0, x), max(0, y))
        nuevo.params = {k: Parametro(**p.a_dict()) for k, p in eq.params.items()}
        pl.agregar(nuevo)
        mapa[i] = nid
    for c in list(pl.conexiones):
        if c.origen in mapa and c.destino in mapa:
            tipo = next((p.tipo for p in pl.equipos[c.origen].salidas if p.nombre == c.puerto_origen), "producto")
            pl.conexiones.append(Conexion(mapa[c.origen], c.puerto_origen, mapa[c.destino], c.puerto_destino, c.reparto,
                                          _siguiente_numero(pl, tipo)))
    for es in list(pl.especs):
        if es.equipo_var in mapa and es.equipo_obj in mapa:
            pl.especs.append(EspecDiseno(mapa[es.equipo_var], es.param, mapa[es.equipo_obj], es.propiedad, es.valor, es.descripcion))
    return mapa


_META = ("nombre", "unidad", "categoria", "fuente", "justificacion", "minimo", "maximo")
_DEFECTO: dict = {}


def _meta_defecto(cls) -> dict:
    if cls.tipo not in _DEFECTO:
        _DEFECTO[cls.tipo] = {k: {m: getattr(p, m) for m in _META} for k, p in cls("_").params.items()}
    return _DEFECTO[cls.tipo]


def instantanea(pl: Planta) -> str:
    """Estado completo de la planta en JSON (datos/bd.planta_a_dict) más los metadatos de los parámetros que difieren del
    tipo (por ejemplo, la categoría Supuesto y la fuente que deja «Asignar capacidades»). Dos plantas iguales dan el mismo texto."""
    from ..datos.bd import planta_a_dict, a_json
    d = planta_a_dict(pl)
    meta = {}
    for k, eq in pl.equipos.items():
        base = _meta_defecto(type(eq))
        dif = {c: {m: getattr(p, m) for m in _META if getattr(p, m) != base.get(c, {}).get(m)} for c, p in eq.params.items()}
        dif = {c: v for c, v in dif.items() if v}
        if dif:
            meta[k] = dif
    d["_meta"] = meta
    return a_json(d)


def restaurar(pl: Planta, texto: str) -> Planta:
    """Devuelve la planta al estado de una instantánea, en el mismo objeto (las pestañas que la tienen siguen viéndola).
    Queda sin resolver: hay que resolverla de nuevo."""
    from ..catalogos.registro import planta_desde_dict
    d = json.loads(texto); meta = d.pop("_meta", {}) or {}
    nueva = planta_desde_dict(d)
    for k, dif in meta.items():
        eq = nueva.equipos.get(k)
        for c, v in (dif.items() if eq else []):
            if c in eq.params:
                for m, x in v.items():
                    setattr(eq.params[c], m, x)
    pl.nombre, pl.rubro, pl.globales = nueva.nombre, nueva.rubro, nueva.globales
    pl.equipos, pl.conexiones, pl.especs, pl.instrumentos = nueva.equipos, nueva.conexiones, nueva.especs, nueva.instrumentos
    pl._p = nueva._p
    pl.resuelta = False; pl.avisos = []
    if hasattr(pl, "salidas"):
        pl.salidas = {}
    return pl


class Historial:
    """Pilas de deshacer y rehacer con tope. Guarda estados (texto de instantanea) con una etiqueta del cambio.

    apilar(estado) guarda el estado anterior a un cambio y vacía rehacer. Los cambios seguidos de un mismo deslizador
    (mismo grupo, dentro de «ventana» segundos) quedan en un solo paso, para no gastar el tope en un arrastre."""

    def __init__(self, tope: int = 30, ventana: float = 2.0):
        self.tope = max(1, int(tope)); self.ventana = ventana
        self.atras: list[tuple[str, str]] = []; self.adelante: list[tuple[str, str]] = []
        self._grupo = None; self._t = -1e18

    @property
    def puede_deshacer(self) -> bool:
        return bool(self.atras)

    @property
    def puede_rehacer(self) -> bool:
        return bool(self.adelante)

    def apilar(self, estado: str, etiqueta: str = "", grupo=None, ahora: float | None = None) -> bool:
        ahora = time.monotonic() if ahora is None else ahora
        if grupo is not None and grupo == self._grupo and ahora - self._t <= self.ventana and self.atras and not self.adelante:
            self._t = ahora
            return False
        self.atras.append((estado, etiqueta))
        del self.atras[:-self.tope]
        self.adelante.clear()
        self._grupo, self._t = grupo, ahora
        return True

    def deshacer(self, actual: str):
        """Devuelve (estado, etiqueta) al que volver, o None. El estado actual pasa a rehacer."""
        if not self.atras:
            return None
        estado, et = self.atras.pop()
        self.adelante.append((actual, et)); del self.adelante[:-self.tope]
        self._grupo = None
        return estado, et

    def rehacer(self, actual: str):
        if not self.adelante:
            return None
        estado, et = self.adelante.pop()
        self.atras.append((actual, et)); del self.atras[:-self.tope]
        self._grupo = None
        return estado, et

    def resumen(self) -> dict:
        return dict(deshacer=len(self.atras), rehacer=len(self.adelante),
                    etiqueta_deshacer=self.atras[-1][1] if self.atras else "", etiqueta_rehacer=self.adelante[-1][1] if self.adelante else "")


_ETIQUETAS = {"agregar": "agregar {id}", "mover": "mover {id}", "conectar": "conectar {origen}.{puerto_origen} → {destino}.{puerto_destino}",
              "reparto": "cambiar la corriente {clave}", "quitar_conexion": "quitar la conexión {clave}", "quitar_equipo": "quitar {id}",
              "parametro": "cambiar {clave} de {id}", "renombrar": "renombrar {id}", "global": "cambiar {clave}",
              "espec": "cambiar la especificación", "alimentacion": "cambiar la alimentación de {id}", "secuencia": "secuencia sugerida",
              "capacidades": "asignar capacidades", "duplicar": "duplicar {ids}", "formulario": "aplicar el formulario de {id}",
              # PAT 134
              "agregar_instrumento": "agregar el instrumento {id}", "instrumento": "cambiar el instrumento {id}",
              "mover_instrumento": "mover {id}", "quitar_instrumento": "quitar el instrumento {id}",
              "conectar_senal": "conectar la señal {origen} → {destino}", "senal": "cambiar la señal {clave}", "quitar_senal": "quitar la señal {clave}"}


def etiqueta_evento(ev: dict, r: dict | None = None) -> str:
    d = dict(ev.get("datos") or {}); d.update({k: v for k, v in (r or {}).items() if k == "id" and "id" not in d})
    if isinstance(d.get("ids"), list):
        d["ids"] = ", ".join(map(str, d["ids"]))
    try:
        return _ETIQUETAS.get(ev.get("evento"), str(ev.get("evento"))).format_map(d)
    except (KeyError, IndexError, ValueError):
        return str(ev.get("evento"))


def _grupo(ev: dict):
    """Cambios que llegan seguidos desde un deslizador o un campo: se agrupan en un solo paso de deshacer."""
    e = ev.get("evento"); d = ev.get("datos") or {}
    if e in ("parametro",):
        return (e, d.get("id"), d.get("clave"))
    if e in ("reparto", "global", "espec", "alimentacion", "renombrar"):
        return (e, d.get("clave"), d.get("indice"), d.get("id"))
    return None


def aplicar_con_historial(pl: Planta, ev: dict, hist: Historial, tipos: dict | None = None, ahora: float | None = None,
                          precedencia=None) -> dict:
    """Aplica un evento del lienzo con deshacer y rehacer: «deshacer» y «rehacer» mueven la planta por el historial; cualquier
    otro evento que cambie la planta apila el estado anterior (y vacía rehacer). Devuelve lo mismo que aplicar_evento."""
    e = ev.get("evento")
    if e in ("deshacer", "rehacer"):
        paso = (hist.deshacer if e == "deshacer" else hist.rehacer)(instantanea(pl))
        if paso is None:
            return dict(ok=False, mensaje="No hay cambios que deshacer." if e == "deshacer" else "No hay cambios que rehacer.", recalcular=False)
        estado, et = paso
        restaurar(pl, estado)
        return dict(ok=True, mensaje=("Deshecho: " if e == "deshacer" else "Rehecho: ") + (et or "último cambio") + ".", recalcular=True,
                    restaurada=True)
    antes = instantanea(pl)
    r = aplicar_evento(pl, ev, tipos, precedencia)
    if r.get("ok") and instantanea(pl) != antes:
        hist.apilar(antes, etiqueta_evento(ev, r), _grupo(ev), ahora)
    return r


# ---------------------------------------------------------------- teoría de restricciones

def restricciones(pl: Planta, sol: Planta | None, f: float = 1.0) -> dict | None:
    """Flujo limitado por la capacidad efectiva, como el grafo del simulador del profesor: cada equipo procesa como
    máximo su capacidad efectiva y entrega aguas abajo la fracción que procesó. f escala la alimentación planificada.

    Devuelve por equipo la demanda, lo procesado, la sobrecarga (lo que se acumula antes del equipo) y la producción
    planificada y real (limitada por la restricción) de la planta."""
    if sol is None or not getattr(sol, "salidas", None):
        return None
    proc = [c for c in pl.conexiones if not pl.es_servicio(c) and c.origen in sol.equipos and c.destino in sol.equipos]
    try:
        orden = sol.orden()
    except ValueError:
        return None
    phi, eqs = {}, {}
    for k in orden:
        eq = sol.equipos[k]; r = eq.resultado
        if r is None or eq.tipo.startswith("caldera"):
            continue
        padres = [c for c in proc if c.destino == k]
        tot = ef = 0.0
        for c in padres:
            s = sol.salidas.get((c.origen, c.puerto_origen))
            if s is None:
                continue
            m = s.m * c.reparto / 100 / 1000
            tot += m; ef += m * phi.get(c.origen, f)
        razon = ef / tot if tot else f
        carga = _num(r.detalle.get("carga_t_h")); cap = eq.capacidad_efectiva()
        if not carga:
            phi[k] = razon; continue
        dem = carga * razon
        hecho = min(dem, cap) if cap else dem
        phi[k] = hecho / carga
        eqs[k] = dict(demanda=dem, procesado=hecho, efectiva=cap, sobrecarga=max(0.0, dem - cap) if cap else 0.0,
                      util_demanda=dem / cap if cap else None, util_real=hecho / cap if cap else None)
    plan = real = 0.0; hay = False
    for k, eq in sol.equipos.items():
        for p in eq.salidas:
            if p.tipo in ("producto", "biomasa") and not any(c.origen == k and c.puerto_origen == p.nombre for c in pl.conexiones):
                s = sol.salidas.get((k, p.nombre))
                if s is not None:
                    plan += s.m / 1000 * f; real += s.m / 1000 * phi.get(k, f); hay = True
    con = [k for k, v in eqs.items() if v["util_demanda"] is not None]
    restr = max(con, key=lambda k: eqs[k]["util_demanda"]) if con else None
    return dict(equipos=eqs, produccion_plan=plan if hay else None, produccion_real=real if hay else None, restrictivo=restr,
                limitantes=[k for k in con if eqs[k]["sobrecarga"] > 1e-6])


def curva_linea(pl: Planta, sol: Planta | None) -> list[list[float]] | None:
    """Producción real frente a la alimentación (0 a 160 % de la planificada): sube hasta el cuello de botella y se aplana."""
    out = []
    for i in range(0, 41):
        f = i * 0.04
        r = restricciones(pl, sol, f)
        if r is None or r["produccion_real"] is None:
            return None
        out.append([round(100 * f, 1), float(r["produccion_real"])])
    return out


def pistas(pl: Planta, sol, motivo, tr) -> list[str]:
    """Orientaciones según la situación actual, como «Solicitar pista» del simulador del profesor (no cambian el diseño)."""
    h = []
    if motivo:
        h.append(f"La planta no se resuelve: {motivo}. Conecte la entrada que falta arrastrando desde un puerto de salida, "
                 "o use «Secuencia sugerida».")
    if not any(eq.capacidad_efectiva() for eq in pl.equipos.values()):
        h.append("Ningún equipo tiene capacidad nominal. Use «Asignar capacidades» (carga + holgura) o escríbala en Propiedades: "
                 "así aparecen el recurso crítico y las barras de utilización.")
    if tr and tr["limitantes"]:
        k = tr["limitantes"][0]; v = tr["equipos"][k]
        h.append(f"{k} recibe {_f(v['demanda'])} t/h y solo procesa {_f(v['efectiva'])} t/h: se acumulan {_f(v['sobrecarga'])} t/h "
                 "antes del equipo. Amplíe solamente ese recurso y compare la producción real.")
    elif tr and tr["restrictivo"]:
        k = tr["restrictivo"]; v = tr["equipos"][k]
        h.append(f"El recurso más exigido es {k} ({pl.equipos[k].nombre}), al {100 * v['util_demanda']:.0f} % de su capacidad efectiva. "
                 "Antes de invertir en ampliarlo, baje su estado o suba la alimentación y vea si de verdad limita la línea.")
    sin_serv = [eq.id for eq in pl.equipos.values() for p in eq.entradas
                if p.tipo in ("vapor", "calor") and not any(c.destino == eq.id and c.puerto_destino == p.nombre for c in pl.conexiones)]
    if sin_serv:
        h.append(f"{', '.join(sin_serv)} no tiene(n) servicio térmico conectado: su demanda de vapor o calor no llega a la caldera.")
    if sol is not None:
        dem = sorted(((eq.resultado.servicios.get("vapor_kW", 0) + eq.resultado.servicios.get("calor_kW", 0), eq.id)
                      for eq in sol.equipos.values() if eq.resultado), reverse=True)
        if dem and dem[0][0] > 0:
            h.append(f"El mayor consumidor de vapor o calor es {dem[0][1]} ({pl.equipos[dem[0][1]].nombre}). Es el candidato natural "
                     "para recibir calor recuperado: revise la pestaña Recuperación de calor.")
    if not h:
        h.append("Compare las condiciones de operación y el resultado económico, no solo la capacidad nominal.")
    return h


# ---------------------------------------------------------------- resolución tolerante

def resolver_parcial(pl: Planta) -> tuple[Planta | None, str | None]:
    """Resuelve la planta. Si falla, resuelve la parte alimentada (para dibujar) y devuelve (subplanta, motivo).

    Si la planta se resuelve, devuelve (pl, None). Si ni la parte alimentada se puede resolver, (None, motivo).
    """
    try:
        pl.resolver()
        return pl, None
    except Exception as x:          # falta de alimentación, ciclo o parámetro fuera de rango
        motivo = str(x)
    pl.resuelta = False
    proc = [c for c in pl.conexiones if not pl.es_servicio(c)]
    ok = set(pl.equipos); cambio = True
    while cambio:
        cambio = False
        for k in list(ok):
            eq = pl.equipos[k]
            if eq.tipo.startswith("caldera"):
                continue
            for p in eq.entradas:
                if p.tipo in TIPOS_SERVICIO:
                    continue
                if not any(c.destino == k and c.puerto_destino == p.nombre and c.origen in ok for c in proc):
                    ok.discard(k); cambio = True
                    break
    sub = Planta(pl.nombre, pl.rubro); sub.globales = pl.globales
    sub.equipos = {k: e for k, e in pl.equipos.items() if k in ok}
    sub.conexiones = [c for c in pl.conexiones if c.origen in ok and c.destino in ok]
    sub.especs = [s for s in pl.especs if s.equipo_var in ok and s.equipo_obj in ok]
    for k, e in pl.equipos.items():
        if k not in ok:
            e.resultado = None
    try:
        sub.resolver() if sub.equipos else None
    except Exception:
        for e in pl.equipos.values():
            e.resultado = None
        return None, motivo
    pl.avisos = list(sub.avisos)
    return sub, motivo


# ---------------------------------------------------------------- datos para el lienzo

def _f(v, d=1):
    """Formato chileno: miles con punto y decimales con coma."""
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _rango(p, carga):
    """Rango del deslizador: el de la fuente si existe; si no, alrededor del valor (o de la carga, para la capacidad)."""
    v = _num(p.valor)
    lo = _num(p.minimo); hi = _num(p.maximo)
    if p.clave == "capacidad":
        base = max(v or 0.0, carga or 0.0, 1.0)
        return 0.0, float(10 ** math.ceil(math.log10(base * 2.0))) if hi is None else hi
    if lo is None:
        lo = 0.0 if (v is None or v >= 0) else 2 * v
    if hi is None:
        hi = max(abs(v or 1.0) * 2.0, lo + 1.0)
    return lo, hi


def _paso(lo, hi, entero):
    if entero:
        return 1
    r = (hi - lo) / 200 if hi > lo else 0.01
    e = 10 ** math.floor(math.log10(r)) if r > 0 else 0.01
    return round(e, 10)


def _puertos(eq):
    def lado(ps):
        return [dict(nombre=p.nombre, tipo=p.tipo, servicio=p.tipo in TIPOS_SERVICIO, descripcion=p.descripcion,
                     color=TIPOS_CORRIENTE.get(p.tipo, ("", "#555", 2))[1], tipo_txt=TIPOS_CORRIENTE.get(p.tipo, (p.tipo,))[0]) for p in ps]
    return lado(eq.entradas), lado(eq.salidas)


def _simbolo(simbolo: str) -> str:
    return iso10628.SIMBOLOS.get(simbolo, iso10628.SIMBOLOS["equipo_general"])[3]


def catalogo_lienzo(rubros: dict, catalogo) -> dict:
    # PAT 132: «Todos los equipos (ISO 10628)» va primero en la lista desplegable del catálogo
    out = {}
    rubros = {"todos": "Todos los equipos (ISO 10628)", **{k: v for k, v in rubros.items() if k != "todos"}}
    for r, nombre in rubros.items():
        out[r] = dict(nombre=nombre, equipos=[dict(
            tipo=c.tipo, nombre=c.nombre_tipo, letra=c.iso_letra, categoria=c.iso_categoria, simbolo=_simbolo(c.simbolo),
            categoria_nombre=iso10628.CATEGORIAS.get(c.iso_categoria, ""),
            simbolo_nombre=iso10628.SIMBOLOS.get(c.simbolo, ("",))[0], descripcion=getattr(c, "descripcion", "") or "",
            entradas=[dict(nombre=p.nombre, tipo=p.tipo) for p in c.entradas], salidas=[dict(nombre=p.nombre, tipo=p.tipo) for p in c.salidas])
            for c in catalogo(r)])
    # PAT 134: puntos de control de ISA-5.1 y elementos del diagrama de lazo de ISA-5.4, al final de la lista
    out["isa"] = dict(nombre="Instrumentación ISA-5.1 y ISA-5.4", equipos=[], instrumentos=IN.catalogo())
    return out


def _corriente(pl, sol, c):
    """Caudal (kg/h), temperatura, °Brix o humedad y calor de una conexión, si hay resultados."""
    f = dict(m=None, T=None, brix=None, hum=None, q=None)
    if sol is None or c.origen not in sol.equipos or c.destino not in sol.equipos:
        return f
    if pl.es_servicio(c):
        r = pl.equipos[c.destino].resultado
        if r is not None:
            f["q"] = _num(r.servicios.get(c.puerto_origen + "_kW"))
        return f
    s = getattr(sol, "salidas", {}).get((c.origen, c.puerto_origen))
    if s is None:
        return f
    s = s.fraccion(c.reparto / 100)
    f.update(m=_num(s.m), T=_num(s.T))
    if s.tipo == "biomasa" or (s.tipo == "subproducto" and s.fase == "solido"):
        f["hum"] = _num(100 * (1 - s.x)) if s.m else None
    elif s.s:
        f["brix"] = _num(s.brix)
    if s.fase == "vapor":
        f["fase"] = "vapor"
    return f


def diagnostico(pl: Planta, motivo: str | None, tr: dict | None = None, precedencia=None) -> list[dict]:
    """Reglas como las del simulador del profesor: sin alimentación, repartos, sobrecarga, falta de servicio térmico.
    PAT 135: también las conexiones existentes que no respetan la precedencia (error; aviso si las conexiones son libres)."""
    out = []
    if motivo:
        out.append(dict(nivel="error", texto=f"La planta no se puede resolver: {motivo}"))
    proc = [c for c in pl.conexiones if not pl.es_servicio(c)]
    for k, eq in pl.equipos.items():
        if eq.tipo.startswith("caldera"):
            if not any(c.origen == k for c in pl.conexiones):
                out.append(dict(nivel="aviso", equipo=k, texto=f"{k} ({eq.nombre}) no entrega su servicio a ningún equipo"))
            continue
        faltan = [p.nombre for p in eq.entradas if p.tipo not in TIPOS_SERVICIO and not any(c.destino == k and c.puerto_destino == p.nombre for c in proc)]
        if faltan:
            out.append(dict(nivel="error", equipo=k, texto=f"{k} ({eq.nombre}) no tiene alimentación en {', '.join(faltan)}"))
        for p in eq.entradas:
            if p.tipo in ("vapor", "calor") and not any(c.destino == k and c.puerto_destino == p.nombre for c in pl.conexiones):
                out.append(dict(nivel="aviso", equipo=k, texto=f"{k} ({eq.nombre}) no tiene servicio térmico conectado en {p.nombre} "
                                                               f"({TIPOS_CORRIENTE[p.tipo][0].lower()}): su demanda no llega a la caldera"))
        for p in eq.salidas:
            cs = [c for c in pl.conexiones if c.origen == k and c.puerto_origen == p.nombre]
            tot = sum(c.reparto for c in cs)
            if cs and abs(tot - 100) > 0.01 and p.tipo not in TIPOS_SERVICIO:
                out.append(dict(nivel="error" if tot > 100.01 else "aviso", equipo=k,
                                texto=f"El reparto de {k}.{p.nombre} suma {tot:.1f} % (debe sumar 100 %)"))
        v = (tr or {}).get("equipos", {}).get(k)
        if v and v["util_demanda"] is not None and 0.8 <= v["util_demanda"] <= 1 + 1e-9:
            out.append(dict(nivel="aviso", equipo=k, texto=f"Cuello de botella en rojo: {k} ({eq.nombre}) trabaja al {_f(100 * v['util_demanda'], 0)} % "
                                                           "de su capacidad efectiva (semáforo: rojo de 80 a 100 %)"))
        if v and v["sobrecarga"] > 1e-6:
            out.append(dict(nivel="error", equipo=k, texto=f"Sobrecarga o acumulación en {k} ({eq.nombre}): recibe {_f(v['demanda'])} t/h y su "
                                                           f"capacidad efectiva es {_f(v['efectiva'])} t/h; se acumulan {_f(v['sobrecarga'])} t/h"))
    t_ = PR.regla(pl, precedencia)                                  # PAT 135
    for _i, c, m in PR.violaciones(pl, t_):
        out.append(dict(nivel="aviso" if t_.libre else "error", equipo=c.destino,
                        texto=f"La conexión {c.origen}.{c.puerto_origen} → {c.destino}.{c.puerto_destino} no respeta el orden del proceso: {m}"))
    if pl.equipos and tr is not None and tr["produccion_plan"] is None:
        out.append(dict(nivel="aviso", texto="Falta una salida de producto final: ninguna salida de producto queda libre al final de la línea"))
    for a in pl.avisos:
        out.append(dict(nivel="aviso", texto=a))
    if not pl.equipos:
        out.append(dict(nivel="aviso", texto="La planta está vacía: arrastre equipos desde el catálogo"))
    if not out:
        out.append(dict(nivel="ok", texto="Sin observaciones: todos los equipos tienen alimentación, los repartos suman 100 % y no hay sobrecargas."))
    return out


def datos_lienzo(pl: Planta, sol: Planta | None, motivo: str | None, catalogo: dict, ultimo_seq: int = 0,
                 mensajes: list | None = None, kpis_extra: dict | None = None, historial: dict | None = None, precedencia=None) -> dict:
    fijados = {(s.equipo_var, s.param): s.descripcion or s.param for s in pl.especs}
    equipos = []
    for k, eq in pl.equipos.items():
        r = eq.resultado
        carga = _num(r.detalle.get("carga_t_h")) if r else None
        ent, sal = _puertos(eq)
        params = []
        for clave, p in eq.params.items():
            if isinstance(p.valor, str) and clave != "capacidad":
                continue                      # etiquetas de texto: se editan en el formulario
            tipo = "bool" if isinstance(p.valor, bool) else ("int" if isinstance(p.valor, int) else "float")
            lo, hi = (None, None) if tipo == "bool" else _rango(p, carga)
            params.append(dict(clave=clave, nombre=p.nombre, valor=p.valor if tipo == "bool" else _num(p.valor), unidad=p.unidad,
                               deslizador=clave != "costo", opcional=clave in OPCIONALES, justificacion=p.justificacion,
                               tipo=tipo, min=lo, max=hi, paso=None if tipo == "bool" else _paso(lo, hi, tipo == "int"),
                               categoria=p.categoria, fuente=p.fuente, fijado=fijados.get((k, clave)),
                               minimo=_num(p.minimo), maximo=_num(p.maximo)))   # PAT 134: límites duros del motor
        cap = _num(eq.params["capacidad"].valor) if "capacidad" in eq.params else None
        sale = None
        if r is not None and sol is not None and k in sol.equipos:
            ss_ = [getattr(sol, "salidas", {}).get((k, p.nombre)) for p in eq.salidas if p.tipo not in TIPOS_SERVICIO]
            sale = _num(sum(x.m for x in ss_ if x is not None) / 1000)
        u = eq.utilizacion() if r else None
        cierre = None
        if r is not None and sol is not None:
            ce = r.cierre_energia()
            cierre = dict(energia_kW=_num(ce), entra_kW=_num(sum(v for _, v in r.energia_in)))
        equipos.append(dict(
            id=k, tipo=eq.tipo, nombre=eq.nombre, nombre_tipo=eq.nombre_tipo, x=eq.x, y=eq.y, simbolo=_simbolo(eq.simbolo),
            simbolo_nombre=iso10628.SIMBOLOS.get(eq.simbolo, ("",))[0], categoria=eq.iso_categoria, letra=eq.iso_letra,
            entradas=ent, salidas=sal, params=params, tiene_capacidad="capacidad" in eq.params, capacidad=cap, carga=carga,
            utilizacion=_num(u), resuelto=r is not None, sale=sale,
            estado=_num(eq.params["estado"].valor) if "estado" in eq.params else None,
            servicios={kk: _num(v) for kk, v in (r.servicios.items() if r else []) if _num(v)}, cierre=cierre))
    conexiones = []
    for i, c in enumerate(pl.conexiones):
        tipo = pl.tipo_conexion(c)
        conexiones.append(dict(indice=i, clave=_clave_conexion(c), nombre=c.nombre, origen=c.origen, puerto_origen=c.puerto_origen,
                               destino=c.destino, puerto_destino=c.puerto_destino, reparto=c.reparto, tipo=tipo,
                               tipo_txt=TIPOS_CORRIENTE[tipo][0], color=TIPOS_CORRIENTE[tipo][1], grosor=TIPOS_CORRIENTE[tipo][2],
                               servicio=pl.es_servicio(c), **_corriente(pl, sol, c)))
    tr = restricciones(pl, sol)
    if tr:
        for e_ in equipos:
            v = tr["equipos"].get(e_["id"])
            if v:
                e_.update(demanda=_num(v["demanda"]), procesado=_num(v["procesado"]), efectiva=_num(v["efectiva"]),
                          sobrecarga=_num(v["sobrecarga"]), util_demanda=_num(v["util_demanda"]), util_real=_num(v["util_real"]))
        for c_ in conexiones:                     # caudal real (limitado) de cada corriente de proceso
            v = tr["equipos"].get(c_["origen"]); eo = pl.equipos[c_["origen"]]
            if v and c_["m"] is not None and eo.resultado and eo.resultado.detalle.get("carga_t_h"):
                c_["m_real"] = c_["m"] * v["procesado"] / float(eo.resultado.detalle["carga_t_h"])
    for e_ in equipos:
        e_["efectiva"] = e_.get("efectiva") if e_.get("efectiva") is not None else _num(pl.equipos[e_["id"]].capacidad_efectiva())
    restr = tr["restrictivo"] if tr else None
    inversion = sum(float(eq.params["costo"].valor) for eq in pl.equipos.values() if "costo" in eq.params and eq.params["costo"].valor)
    kpis = dict(produccion_t_h=_num(tr["produccion_plan"]) if tr else None, produccion_real_t_h=_num(tr["produccion_real"]) if tr else None,
                vapor_kW=_num(sol.servicio_total("vapor_kW") + sol.servicio_total("calor_kW")) if sol else None,
                electricidad_kW=_num(sol.servicio_total("electricidad_kW")) if sol else None,
                restrictivo=restr, limitantes=tr["limitantes"] if tr else [], conexiones=len(pl.conexiones),
                inversion_declarada=inversion or None)
    kpis.update(kpis_extra or {})
    especs = []
    for i, es in enumerate(pl.especs):
        if es.propiedad == "x":
            fac, uni, lo, hi = 100.0, ("°Brix" if pl.rubro == "tomate" else "% de sólidos"), 10.0, 45.0
        elif es.propiedad == "m":
            fac, uni = 0.001, "t/h"; lo, hi = 0.0, max(1.0, round(es.valor * fac * 2, 1))
        else:
            fac, uni, lo, hi = 1.0, "", 0.0, max(1.0, es.valor * 2)
        especs.append(dict(indice=i, descripcion=es.descripcion or f"{es.propiedad} de la entrada de {es.equipo_obj}", valor=es.valor * fac,
                           factor=fac, unidad=uni, min=lo, max=hi, equipo_var=es.equipo_var, param=es.param, equipo_obj=es.equipo_obj))
    fijos = {(s.equipo_var, s.param) for s in pl.especs}
    alim = []
    for k, eq in pl.equipos.items():
        if eq.entradas or eq.tipo.startswith("caldera") or eq.resultado is None:
            continue
        carga = _num(eq.resultado.detalle.get("carga_t_h"))
        editable = (("temporada_t" in eq.params and hasattr(eq, "horas") and (k, "temporada_t") not in fijos)
                    or ("carga_t_h" in eq.params and (k, "carga_t_h") not in fijos))
        if carga:
            alim.append(dict(id=k, nombre=eq.nombre, valor=carga, editable=editable, max=max(10.0, round(carga * 2, -1))))
    return dict(nombre=pl.nombre, rubro=pl.rubro, resuelta=pl.resuelta, motivo=motivo, equipos=equipos, conexiones=conexiones,
                kpis=kpis, diagnostico=diagnostico(pl, motivo, tr, precedencia), pistas=pistas(pl, sol, motivo, tr), catalogo=catalogo,
                curva=curva_linea(pl, sol), especs=especs, alimentaciones=alim,
                tipos={k: dict(nombre=v[0], color=v[1], grosor=v[2], servicio=k in TIPOS_SERVICIO) for k, v in TIPOS_CORRIENTE.items()},
                globales={k: _num(v) for k, v in pl.globales.items() if _num(v) is not None},
                ultimo_seq=ultimo_seq, mensajes=mensajes or [], tam=TAM,
                instrumentos=IN.datos(pl, TAM),                                       # PAT 134
                isa=dict(senales={k: v[0] for k, v in isa51.SENALES.items()}, lugares=isa51.LUGARES, ubicaciones=isa51.UBICACIONES,
                         funciones=isa51.FUNCIONES),
                historial=historial or dict(deshacer=0, rehacer=0, etiqueta_deshacer="", etiqueta_rehacer=""))   # PAT 133
