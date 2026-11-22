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
PAT 142: vista «lazos» (pantalla Lazos de control): los equipos y las corrientes se dibujan como en la Planta ficticia sin editarse;
los instrumentos sí se agregan, mueven, editan, conectan y quitan, y se sueltan lazos típicos sobre un equipo (evento agregar_lazo,
pat_sim.motor.instrumentacion.agregar_lazo). Los eventos instrumento y senal aceptan los datos de ISA-5.4 y la relación entre lazos.
"""
from __future__ import annotations
import json, math, time
from .planta import Planta, TIPOS_SERVICIO, corrientes_compatibles
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
    """Una salida se puede conectar a una entrada del mismo tipo de corriente; un subproducto puede volver a proceso.
    PAT 143: la regla vive en motor/planta.corrientes_compatibles, que también usa el cálculo."""
    return corrientes_compatibles(tipo_salida, tipo_entrada)


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
    if isinstance(actual, str):                 # PAT 140: etiqueta de texto; vacía es válida
        return "" if valor is None else str(valor)
    if valor is None or valor == "":
        if p.clave in OPCIONALES:
            return None
        raise ValueError(f"{p.nombre}: falta el valor")
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


def aplicar_evento(pl: Planta, ev: dict, tipos: dict | None = None, precedencia=None, libre: bool | None = None) -> dict:
    """Aplica un evento del lienzo a la planta. Devuelve {ok, mensaje, recalcular}.

    Los errores de edición (puerto inexistente, tipos incompatibles, ciclo, precedencia) no lanzan excepción: vuelven con
    ok=False y la planta queda como estaba. precedencia: tabla de motor/precedencia.py (si no, pl.precedencia o ninguna).
    PAT 143 (tarea 6): libre=True (o el atributo pl.conexion_libre que fija la interfaz) es la conexión libre: se aceptan las
    conexiones entre corrientes de distinto tipo y las que no respetan la precedencia, y las marca el validador
    (motor/validador.py), que no deja avanzar mientras existan. Siguen rechazados el equipo consigo mismo, el puerto inexistente,
    la conexión repetida y el ciclo de corrientes de proceso (el cálculo secuencial no lo resuelve).
    """
    if tipos is None:
        from ..catalogos.registro import TIPOS as tipos
    e = ev.get("evento"); d = ev.get("datos") or {}
    if libre is None:
        libre = bool(getattr(pl, "conexion_libre", False))
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
            distinto = not compatibles(ps.tipo, pe.tipo)
            if distinto and not libre:
                raise ValueError(f"Tipos incompatibles: la salida {o}.{po} es {TIPOS_CORRIENTE[ps.tipo][0].lower()} "
                                 f"y la entrada {de}.{pd_} espera {TIPOS_CORRIENTE[pe.tipo][0].lower()}")
            if any((c.origen, c.puerto_origen, c.destino, c.puerto_destino) == (o, po, de, pd_) for c in pl.conexiones):
                raise ValueError(f"Ya existe la conexión {o}.{po} → {de}.{pd_}")
            regla = None if libre else _regla_conectar(pl, precedencia)   # PAT 135: precedencia (PAT 143: la revisa el validador)
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
            if distinto:                                            # PAT 143: conexión libre entre corrientes de distinto tipo
                msg += " Atención: une corrientes de distinto tipo; el diseño queda con un error hasta corregirla."
                return dict(ok=True, mensaje=msg, recalcular=True, tipo="aviso")
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
        if e == "agregar_lazo":                  # PAT 142: lazo típico soltado sobre un equipo
            r = IN.agregar_lazo(pl, d.get("variable"), d.get("equipo"), d.get("parametro") or None, d.get("x"), d.get("y"),
                                d.get("corriente") or None, d.get("numero") or None)
            return dict(ok=True, mensaje=r["mensaje"], recalcular=False, id=r["controlador"], sel="ins", numero=r["numero"])
        if e == "instrumento":
            cambios = {c: v for c, v in d.items() if c in ("letras", "numero", "ubicacion", "descripcion", "equipo", "parametro", "elemento_final", "simbolo",
                                                           "accion_falla", "alimentacion", "accion", "consigna")}   # PAT 142: ISA-5.4
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
            IN.editar_senal(pl, d["clave"], {c: v for c, v in d.items() if c in ("senal", "parametro", "relacion")})   # PAT 142: relación
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
                                                                            puerto_destino=p.nombre)), precedencia=precedencia, libre=False)
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
                               precedencia=precedencia, libre=False)
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
              "conectar_senal": "conectar la señal {origen} → {destino}", "senal": "cambiar la señal {clave}", "quitar_senal": "quitar la señal {clave}",
              "agregar_lazo": "agregar el lazo típico de {variable} en {equipo}"}   # PAT 142


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
                          precedencia=None, libre: bool | None = None) -> dict:
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
    r = aplicar_evento(pl, ev, tipos, precedencia, libre)
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


# ---------------------------------------------------------------- PAT 139b (14-11-2026): curva de eficiencia de la línea
# Pedido del profesor Torres (14-11-2026): curva característica de eficiencia, eje x la producción y eje y la eficiencia, con un
# máximo en el punto de diseño. Reemplaza en el lienzo a la recta «producción real contra alimentación».
ZONA_BUENA = (0.70, 1.20)
FUENTE_ZONA = ("Zona de buen rendimiento: el recurso crítico opera entre 70 % y 120 % de su punto de diseño, la región de operación "
               "preferida de las bombas rotodinámicas del Hydraulic Institute (ANSI/HI 9.6.3; https://www.pumps.org/product/ansi-hi-9-6-3/ y "
               "https://www.introtopumps.com/pump-terms/por-preferred-operating-range/, consultados el 14-11-2026: «in most cases extends "
               "from 70% to 120% of flow at the best efficiency point»). Supuesto: se extiende a todos los equipos de la línea")
FUENTE_CURVA = ("η(q) de cada etapa con la curva de motor/costo_total.py (eta_relativa, Supuesto «a_curva» y punto de diseño en la capacidad "
                "por unidad en operación, Supuesto «q_peak»). Eficiencia de la línea = energía ideal / energía real = Σ E_i / Σ (E_i / η_i), con "
                "E_i el consumo de servicios del balance de la etapa (kW, que no usa la curva); sin consumos, pesos iguales (Supuesto)")


def _carga_por_unidad(pl: Planta, k: str, cap: float) -> tuple[float, int, int]:
    """(capacidad de diseño de una unidad en t/h de carga, n, k): con selección comercial las k unidades necesarias se reparten la
    carga y la de reserva espera detenida (Supuesto «reparto» de costo_total.py); sin selección, una unidad del tamaño de la etapa."""
    from . import seleccion as SEL
    eq = pl.equipos.get(k)
    act = SEL.seleccion_actual(eq) if eq is not None and "unidades" in eq.params else None
    n, kk = (int(act["n"]), int(act["k"])) if act else (1, 1)
    n, kk = max(1, n), max(1, min(kk, max(1, n)))
    return cap / n, n, kk


def curva_eficiencia_linea(pl: Planta, sol: Planta | None, puntos: int = 41) -> dict | None:
    """Curva característica de eficiencia de la línea (PAT 139b): para la producción de 0 a la capacidad de la línea (donde se satura
    el recurso crítico), la eficiencia relativa η/η_max de cada etapa (motor/costo_total.eta_relativa con la carga por unidad en
    operación), la del recurso crítico y la de la línea (media armónica ponderada por la energía de cada etapa). Marca el punto de
    operación actual (alimentación planificada o, si hay sobrecarga, la capacidad de la línea), el punto de diseño de la línea (máximo de
    su curva) y la zona de buen rendimiento (recurso crítico entre 70 % y 120 % de su punto de diseño, ZONA_BUENA). None sin balance."""
    from . import costo_total as CT
    tr = restricciones(pl, sol, 1.0)
    if tr is None or not tr.get("produccion_plan"):
        return None
    P_plan = float(tr["produccion_plan"])
    etapas = []
    for k, v in tr["equipos"].items():
        cap, dem = _num(v.get("efectiva")), _num(v.get("demanda"))
        if not cap or cap <= 0 or dem is None or dem <= 0:
            continue
        q_unidad, n, kk = _carga_por_unidad(pl, k, cap)
        eq = (sol.equipos.get(k) if sol is not None else None) or pl.equipos[k]
        r = eq.resultado
        peso = sum(abs(_num(x) or 0.0) for x in (r.servicios.values() if r is not None else []))
        etapas.append(dict(id=k, nombre=pl.equipos[k].nombre, n=n, k=kk, q_diseno_t_h=q_unidad, carga_t_h=dem, util=dem / cap,
                           u_plan=(dem / kk) / q_unidad, peso_kW=peso))
    if not etapas:
        return None
    if not any(e["peso_kW"] > 0 for e in etapas):
        for e in etapas:
            e["peso_kW"] = 1.0
    f_sat = min(1.0 / e["util"] for e in etapas)                # alimentación (fracción de la planificada) que satura la línea
    crit = max(etapas, key=lambda e: e["util"])["id"]
    sw = sum(e["peso_kW"] for e in etapas)

    def etas(f):
        es = {e["id"]: CT.eta_relativa(f * e["u_plan"], 1.0) for e in etapas}
        lin = sw / sum(e["peso_kW"] / es[e["id"]] for e in etapas)
        return es, lin

    puntos = max(5, int(puntos))
    fs = [f_sat * i / (puntos - 1) for i in range(puntos)]
    x, lin, cr, por = [], [], [], {e["id"]: [] for e in etapas}
    for f in fs:
        es, l = etas(f)
        x.append(round(P_plan * f, 4)); lin.append(round(l, 5)); cr.append(round(es[crit], 5))
        for k, v in es.items():
            por[k].append(round(v, 5))
    finos = [f_sat * i / 400 for i in range(401)]
    f_dis = max(finos, key=lambda f: etas(f)[1])
    f_op = min(1.0, f_sat)
    es_op, l_op = etas(f_op)
    ec = next(e for e in etapas if e["id"] == crit)
    z0, z1 = ZONA_BUENA[0] / ec["u_plan"], min(ZONA_BUENA[1] / ec["u_plan"], f_sat)
    zona = [round(P_plan * z0, 4), round(P_plan * z1, 4)] if z0 < z1 else None
    return dict(x=x, eta_linea=lin, eta_critico=cr, critico=crit, capacidad_linea=round(P_plan * f_sat, 4), produccion_plan=P_plan,
                etapas=[dict(id=e["id"], nombre=e["nombre"], n=e["n"], k=e["k"], q_diseno_t_h=_num(e["q_diseno_t_h"]), peso_kW=_num(e["peso_kW"]),
                             carga_rel=_num(f_op * e["u_plan"]), eta_op=_num(es_op[e["id"]]), eta=por[e["id"]]) for e in etapas],
                operacion=dict(produccion=round(P_plan * f_op, 4), eta_linea=_num(l_op), eta_critico=_num(es_op[crit]),
                               carga_rel_critico=_num(f_op * ec["u_plan"]), sobrecarga=f_sat < 1.0),
                diseno=dict(produccion=round(P_plan * f_dis, 4), eta_linea=_num(etas(f_dis)[1])),
                zona=zona, fuente=FUENTE_CURVA, fuente_zona=FUENTE_ZONA)


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
    malas = {id(c) for c in pl.incompatibles()}       # PAT 143: la parte alimentada no usa las corrientes cruzadas
    proc = [c for c in pl.conexiones if not pl.es_servicio(c) and id(c) not in malas]
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
    sub.conexiones = [c for c in pl.conexiones if c.origen in ok and c.destino in ok and id(c) not in malas]
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


def catalogo_taxonomia(catalogo) -> dict:
    """PAT 136 (T22, punto 7): catálogo del lienzo con taxonomía. «Todos los equipos (ISO 10628)» primero (completo, como
    catalogo_lienzo), después una lista por función de proceso agrupada por familia de la ISO 10628 y una por tipo de planta (con
    la clave del rubro, para que el lienzo abra en la de la planta), y la instrumentación al final. Las listas de función y de planta
    llevan solo {tipo, grupo, buscar}: el lienzo toma el resto de «todos». «buscar» es el texto sin tildes del buscador."""
    from ..catalogos import taxonomia as TX
    base = catalogo_lienzo({}, catalogo)
    isa = base.pop("isa")
    fs = TX.fichas()
    texto = {f["tipo"]: TX.normalizar(" ".join([f["nombre"], f["tipo"], f["letra"], f["simbolo_nombre"], f["familia_nombre"]]
                                              + f["funcion_nombres"] + f["plantas_nombres"])) for f in fs}
    for e in base["todos"]["equipos"]:
        e["buscar"] = texto.get(e["tipo"], TX.normalizar(e["nombre"]))
    tipos = {e["tipo"] for e in base["todos"]["equipos"]}
    out = {"todos": base["todos"]}
    for r in TX.resumen_plantas(fs):
        from ..catalogos import plantas_genericas as PG
        rub = PG.PLANTAS[r["planta_id"]]["rubro"]
        eqs = [dict(tipo=f["tipo"], grupo=f["funcion_nombres"][0]) for f in r["equipos"] if f["tipo"] in tipos]
        out[rub] = dict(nombre=f"Planta: {r['planta']} ({len(eqs)})", equipos=eqs)
    for g in TX.arbol(fs):
        eqs = [dict(tipo=f["tipo"], grupo=f"{fam['familia']} · {fam['nombre']}") for fam in g["familias"] for f in fam["equipos"]
               if f["tipo"] in tipos]
        out["fun_" + g["funcion"]] = dict(nombre=f"Función: {g['nombre']} ({len(eqs)})", equipos=eqs)
    out["isa"] = isa
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
    PAT 135: también las conexiones existentes que no respetan la precedencia (error; aviso si las conexiones son libres).
    PAT 143: cada observación lleva su código de regla («regla», P00 a P15), que usa motor/validador.py para sus pistas."""
    out = []
    if motivo:
        out.append(dict(nivel="error", regla="P00", texto=f"La planta no se puede resolver: {motivo}"))
    proc = [c for c in pl.conexiones if not pl.es_servicio(c)]
    for k, eq in pl.equipos.items():
        if eq.tipo.startswith("caldera"):
            if not any(c.origen == k for c in pl.conexiones):
                out.append(dict(nivel="aviso", regla="P07", equipo=k, texto=f"{k} ({eq.nombre}) no entrega su servicio a ningún equipo"))
            continue
        faltan = [p.nombre for p in eq.entradas if p.tipo not in TIPOS_SERVICIO and not any(c.destino == k and c.puerto_destino == p.nombre for c in proc)]
        if faltan:
            out.append(dict(nivel="error", regla="P03", equipo=k, puertos=faltan, texto=f"{k} ({eq.nombre}) no tiene alimentación en {', '.join(faltan)}"))
        for p in eq.entradas:
            if p.tipo in ("vapor", "calor") and not any(c.destino == k and c.puerto_destino == p.nombre for c in pl.conexiones):
                out.append(dict(nivel="aviso", regla="P06", equipo=k, puerto=p.nombre, tipo=p.tipo,
                                texto=f"{k} ({eq.nombre}) no tiene servicio térmico conectado en {p.nombre} "
                                                               f"({TIPOS_CORRIENTE[p.tipo][0].lower()}): su demanda no llega a la caldera"))
        for p in eq.salidas:
            cs = [c for c in pl.conexiones if c.origen == k and c.puerto_origen == p.nombre]
            tot = sum(c.reparto for c in cs)
            if cs and abs(tot - 100) > 0.01 and p.tipo not in TIPOS_SERVICIO:
                out.append(dict(nivel="error" if tot > 100.01 else "aviso", regla="P05", equipo=k, puerto=p.nombre, total=tot,
                                texto=f"El reparto de {k}.{p.nombre} suma {tot:.1f} % (debe sumar 100 %)"))
        v = (tr or {}).get("equipos", {}).get(k)
        if v and v["util_demanda"] is not None and 0.8 <= v["util_demanda"] <= 1 + 1e-9:
            out.append(dict(nivel="aviso", regla="P11", equipo=k, texto=f"Cuello de botella en rojo: {k} ({eq.nombre}) trabaja al {_f(100 * v['util_demanda'], 0)} % "
                                                           "de su capacidad efectiva (semáforo: rojo de 80 a 100 %)"))
        if v and v["sobrecarga"] > 1e-6:
            out.append(dict(nivel="error", regla="P12", equipo=k, texto=f"Sobrecarga o acumulación en {k} ({eq.nombre}): recibe {_f(v['demanda'])} t/h y su "
                                                           f"capacidad efectiva es {_f(v['efectiva'])} t/h; se acumulan {_f(v['sobrecarga'])} t/h"))
    t_ = PR.regla(pl, precedencia)                                  # PAT 135
    for _i, c, m in PR.violaciones(pl, t_):
        out.append(dict(nivel="aviso" if t_.libre else "error", regla="P02", equipo=c.destino, conexion=_clave_conexion(c), motivo=m,
                        texto=f"La conexión {c.origen}.{c.puerto_origen} → {c.destino}.{c.puerto_destino} no respeta el orden del proceso: {m}"))
    if pl.equipos and tr is not None and tr["produccion_plan"] is None:
        out.append(dict(nivel="aviso", regla="P13", texto="Falta una salida de producto final: ninguna salida de producto queda libre al final de la línea"))
    for a in pl.avisos:
        out.append(dict(nivel="aviso", regla="P14", texto=a))
    if not pl.equipos:
        out.append(dict(nivel="aviso", regla="P15", texto="La planta está vacía: arrastre equipos desde el catálogo"))
    if not out:
        out.append(dict(nivel="ok", texto="Sin observaciones: todos los equipos tienen alimentación, los repartos suman 100 % y no hay sobrecargas."))
    return out


# ---------------------------------------------------------------- PAT 138: tres pantallas de construcción con el mismo lienzo
VISTAS = ("ficticia", "real", "auxiliares", "lazos")   # PAT 142: «lazos», pantalla Lazos de control
# PAT 142: eventos que acepta la vista «lazos» (los equipos y las corrientes no se editan ahí)
EVENTOS_LAZOS = ("agregar_instrumento", "instrumento", "mover_instrumento", "quitar_instrumento", "conectar_senal", "senal",
                 "quitar_senal", "agregar_lazo", "deshacer", "rehacer")


def catalogo_lazos() -> dict:
    """PAT 142: catálogo del lienzo en la vista «lazos»: el grupo «Lazos típicos» más los grupos de instrumentación ISA-5.1 y ISA-5.4."""
    return {"lazos": dict(nombre="Lazos típicos e instrumentación ISA-5.1 y ISA-5.4", equipos=[], instrumentos=IN.catalogo(),
                          tipicos=IN.catalogo_tipicos())}


# PAT 139b (14-11-2026, pedido de Jaime): una etapa con n unidades en paralelo se dibuja con n símbolos iguales dentro de la etapa,
# con un colector de entrada y uno de salida. Tope de 6 dibujados (2 columnas de 3): más símbolos no caben legibles en el recuadro de
# 64 px del equipo; el resto se indica con «+r» y el total queda en la etiqueta «n × capacidad» y en la ficha.
TOPE_PARALELO = 6


def dibujo_paralelo(n, k=None) -> dict:
    """Cómo dibuja el lienzo n unidades en paralelo de las que se necesitan k: n_dibujados = min(n, TOPE_PARALELO), n_resto (las que no
    se dibujan), n_reserva = n − k (se dibujan con borde punteado, las últimas), columnas (1 hasta 3 unidades, 2 desde 4) y filas."""
    try:
        n = max(1, int(n))
    except (TypeError, ValueError):
        n = 1
    try:
        k = n if k is None else max(1, min(int(k), n))
    except (TypeError, ValueError):
        k = n
    m = min(n, TOPE_PARALELO)
    col = 1 if m <= 3 else 2
    return dict(n=n, k=k, n_dibujados=m, n_resto=n - m, n_reserva=n - k, n_reserva_dibujadas=max(0, m - min(k, m)),
                columnas=col, filas=math.ceil(m / col))


def capa_real(pl: Planta) -> dict:
    """Planta real (PAT 138): lo que la selección comercial (motor/seleccion.py, aplicar) dejó en cada equipo: modelo (con su
    fabricante cuando la ficha lo trae), unidades en paralelo n, necesarias k, capacidad instalada y por unidad (t/h de carga),
    MTBF y MTTR de una unidad, disponibilidad de la unidad A = MTBF/(MTBF + MTTR) y de la etapa k de n (binomial). Los equipos
    que admiten selección y no la tienen quedan con seleccion=False (el lienzo dibuja el equipo teórico). A_linea es el producto
    de las disponibilidades de las etapas con selección (línea en serie, mismo supuesto de seleccion.py)."""
    from . import seleccion as SEL
    eqs, As = {}, []
    for k, eq in pl.equipos.items():
        if "unidades" not in eq.params or "capacidad" not in eq.params or SEL._excluido(eq):
            continue
        act = SEL.seleccion_actual(eq)
        if not act:
            eqs[k] = dict(seleccion=False)
            continue
        n, kk = int(act["n"]), int(act["k"])
        mt, mr = act.get("mtbf_h"), act.get("mttr_h")
        A = SEL.disponibilidad(mt, mr) if mt and mr is not None and mt > 0 and mr >= 0 else None
        Ae = SEL.k_de_n(A, n, kk) if A is not None else None
        if Ae is not None:
            As.append(Ae)
        cap = _num(act.get("capacidad_t_h"))
        p = eq.params.get("modelo")
        eqs[k] = dict(seleccion=True, modelo=act["modelo"], n=n, k=kk, capacidad_instalada=cap,
                      capacidad_unidad=_num(cap / n) if cap and n else None, mtbf_h=_num(mt), mttr_h=_num(mr),
                      A_unidad=_num(A), A_etapa=_num(Ae), fuente=(p.fuente if p is not None else "") or "", categoria=(p.categoria if p is not None else ""),
                      dibujo=dibujo_paralelo(n, kk))
    con = sum(1 for v in eqs.values() if v["seleccion"])
    return dict(equipos=eqs, seleccionables=len(eqs), con_seleccion=con,
                A_linea=_num(math.prod(As)) if As else None,
                aviso=None if con else "Sin selección: aplique una combinación abajo. El lienzo muestra el equipo teórico de la Planta ficticia.")


def _con_entre(pl: Planta, a: str, b: str, nombre: str | None = None):
    """Conexión de proceso de a hacia b (si hay varias, la que tiene ese nombre de línea)."""
    cs = [c for c in pl.conexiones if c.origen == a and c.destino == b and not pl.es_servicio(c)]
    if nombre:
        for c in cs:
            if (c.nombre or f"{c.origen} → {c.destino}") == nombre:
                return c
    return cs[0] if cs else None


def capa_auxiliares(pl: Planta, aux: dict | None) -> dict:
    """Equipos auxiliares (PAT 138) puestos sobre el lienzo: cada bomba y cada válvula sobre su línea de líquido (clave de la
    conexión), cada estanque pulmón sobre la línea entre sus dos equipos, el diámetro nominal de cada cañería y el resumen de
    servicios. aux: resultado de motor/auxiliares.auxiliares (la pantalla lo calcula con sus parámetros); sin él, capa vacía."""
    out = dict(bombas=[], valvulas=[], estanques=[], canerias=[], servicios=[], n_bloqueo=0, n_retencion=0, totales={}, avisos=[])
    if not aux:
        out["avisos"].append("Resuelva la planta para ver sus equipos auxiliares.")
        return out
    b = aux.get("bombas") or {}
    for x in b.get("filas") or []:
        c = _con_entre(pl, x["origen"], x["destino"], x.get("linea"))
        out["bombas"].append(dict(id=x["id"], linea=x["linea"], origen=x["origen"], destino=x["destino"], con=_clave_conexion(c) if c else None,
                                  Q_m3h=_num(x["Q_m3h"]), H_m=_num(x["H_m"]), D_mm=_num(x["D_mm"]), potencia_kW=_num(x["potencia_kW"]),
                                  en_diagrama=bool(x["en_diagrama"]), costo_usd=_num(x.get("costo_usd")), fuente=x.get("fuente_costo", "")))
    v = aux.get("valvulas") or {}
    out["n_bloqueo"], out["n_retencion"] = int(v.get("n_bloqueo") or 0), int(v.get("n_retencion") or 0)
    lazo = {(i.elemento_final or "").strip(): i.equipo for i in getattr(pl, "instrumentos", []) or []}
    for x in v.get("control") or []:
        en_diag = x["id"] in pl.equipos
        eq = x["id"] if en_diag else lazo.get(x["id"])
        c = None
        if not en_diag and eq:
            proc = [cc for cc in pl.conexiones if not pl.es_servicio(cc)]
            liq = {(f["origen"], f["destino"]) for f in b.get("filas") or []}
            c = (next((cc for cc in proc if cc.destino == eq and (cc.origen, cc.destino) in liq), None)
                 or next((cc for cc in proc if cc.destino == eq), None) or next((cc for cc in proc if cc.origen == eq), None))
        out["valvulas"].append(dict(id=x["id"], nombre=x["nombre"], Cv=_num(x.get("Cv")), equipo=eq, en_diagrama=en_diag,
                                    con=_clave_conexion(c) if c else None, costo_usd=_num(x.get("costo_usd")), nota=x.get("nota", "")))
    e = aux.get("estanques") or {}
    for x in e.get("filas") or []:
        c = _con_entre(pl, x["antes"], x["despues"])
        out["estanques"].append(dict(id="TK " + x["id"], antes=x["antes"], despues=x["despues"], con=_clave_conexion(c) if c else None,
                                     masa_t=_num(x["masa_t"]), v_util_m3=_num(x["v_util_m3"]), v_geo_m3=_num(x["v_geo_m3"]), D_m=_num(x["D_m"]),
                                     H_m=_num(x["H_m"]), costo_usd=_num(x.get("costo_usd")), metodo=e.get("metodo")))
    for x in (aux.get("canerias") or {}).get("lineas") or []:
        c = _con_entre(pl, x["origen"], x["destino"], x.get("linea"))
        if c is not None:
            out["canerias"].append(dict(con=_clave_conexion(c), DN=x["DN"], pulgadas=x["pulgadas"], largo_m=_num(x["largo_m"])))
    for x in (aux.get("servicios") or {}).get("filas") or []:
        out["servicios"].append(dict(servicio=x["servicio"], demanda=_num(x["demanda"]), unidad=x["unidad"], genera=x["genera"]))
    out["totales"] = dict(total_clp=_num(aux.get("total_clp")), total_instalado_clp=_num(aux.get("total_instalado_clp")),
                          bombeo_kW=_num(b.get("total_kw")), pulmones_m3=_num(sum(x["v_geo_m3"] for x in e.get("filas") or [])),
                          canerias_m=_num((aux.get("canerias") or {}).get("total_m")))
    out["avisos"] = list(aux.get("avisos") or [])
    # PAT 140 g: posición de cada auxiliar que el estudiante dejó fuera de su línea (motor/eleccion_auxiliares.CLAVE_POS); el lienzo lo
    # dibuja ahí, unido a su línea por un trazo
    pos = ((getattr(pl, "_p", None) or {}).get("posiciones_auxiliares") or {}) if isinstance(getattr(pl, "_p", None), dict) else {}
    for grupo in ("bombas", "valvulas", "estanques"):
        for x in out[grupo]:
            q = pos.get(x["id"])
            if isinstance(q, dict) and _num(q.get("x")) is not None and _num(q.get("y")) is not None:
                x["pos"] = dict(x=_num(q["x"]), y=_num(q["y"]))
    return out


def datos_lienzo(pl: Planta, sol: Planta | None, motivo: str | None, catalogo: dict, ultimo_seq: int = 0,
                 mensajes: list | None = None, kpis_extra: dict | None = None, historial: dict | None = None, precedencia=None,
                 vista: str = "ficticia", aux: dict | None = None, libre: bool = False, validacion: dict | None = None) -> dict:
    """Lo que el lienzo dibuja. PAT 138: vista «ficticia» (Diseño, editable, como antes), «real» (más la selección comercial de
    cada equipo, solo lectura) o «auxiliares» (más la selección y los equipos auxiliares de aux, solo lectura). PAT 142: «lazos»
    (equipos y corrientes de solo lectura, instrumentos editables con editar_instrumentos y la lista «lazos» de lazos_lienzo).
    PAT 143 (tarea 6): libre=True habilita la conexión libre en el navegador (puertos de distinto tipo en la Planta ficticia y
    candidatos que no calzan en la Planta real y en Equipos auxiliares); validacion (resultado de motor/validador.revisar) reemplaza
    la lista del botón «Diagnóstico»: los errores quedan en la advertencia sobre el lienzo y la caja muestra los avisos."""
    if vista not in VISTAS:
        raise ValueError(f"Vista desconocida: {vista}. Use {', '.join(VISTAS)}")
    d = _datos_lienzo(pl, sol, motivo, catalogo, ultimo_seq, mensajes, kpis_extra, historial, precedencia)
    d["vista"] = vista
    d["libre"] = bool(libre)                                              # PAT 143
    if validacion is not None:
        from . import validador as VAL
        d["diagnostico"] = VAL.para_lienzo(validacion)
        d["validacion"] = dict(errores=len(validacion.get("errores") or []), avisos=len(validacion.get("avisos") or []))
    d["solo_lectura"] = vista != "ficticia"
    d["editar_instrumentos"] = vista in ("ficticia", "lazos")              # PAT 142
    if vista == "lazos":
        d["lazos"] = IN.lazos_lienzo(pl, TAM)
    if vista in ("real", "auxiliares"):
        d["real"] = capa_real(pl)
        d["kpis"].update(A_linea=d["real"]["A_linea"], con_seleccion=d["real"]["con_seleccion"], seleccionables=d["real"]["seleccionables"])
    if vista == "auxiliares":
        d["auxiliares"] = capa_auxiliares(pl, aux)
        d["kpis"].update({"aux_" + k: v for k, v in d["auxiliares"]["totales"].items()})
    return d


def _datos_lienzo(pl: Planta, sol: Planta | None, motivo: str | None, catalogo: dict, ultimo_seq: int = 0,
                  mensajes: list | None = None, kpis_extra: dict | None = None, historial: dict | None = None, precedencia=None) -> dict:
    fijados = {(s.equipo_var, s.param): s.descripcion or s.param for s in pl.especs}
    equipos = []
    for k, eq in pl.equipos.items():
        r = eq.resultado
        carga = _num(r.detalle.get("carga_t_h")) if r else None
        ent, sal = _puertos(eq)
        params = []
        for clave, p in eq.params.items():
            # PAT 140: las etiquetas de texto (modelo, materia, etiquetas de corrientes…) también llegan al cuadro «Propiedades»
            # (tipo «texto»); antes solo se editaban en el formulario «Todos los parámetros de un equipo», que se eliminó.
            tipo = "bool" if isinstance(p.valor, bool) else ("texto" if isinstance(p.valor, str) else ("int" if isinstance(p.valor, int) else "float"))
            lo, hi = (None, None) if tipo in ("bool", "texto") else _rango(p, carga)
            params.append(dict(clave=clave, nombre=p.nombre, valor=p.valor if tipo in ("bool", "texto") else _num(p.valor), unidad=p.unidad,
                               deslizador=clave != "costo" and tipo != "texto", opcional=clave in OPCIONALES, justificacion=p.justificacion,
                               tipo=tipo, min=lo, max=hi, paso=None if tipo in ("bool", "texto") else _paso(lo, hi, tipo == "int"),
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
                curva_eficiencia=curva_eficiencia_linea(pl, sol), especs=especs, alimentaciones=alim,      # PAT 139b
                tipos={k: dict(nombre=v[0], color=v[1], grosor=v[2], servicio=k in TIPOS_SERVICIO) for k, v in TIPOS_CORRIENTE.items()},
                globales={k: _num(v) for k, v in pl.globales.items() if _num(v) is not None},
                ultimo_seq=ultimo_seq, mensajes=mensajes or [], tam=TAM,
                instrumentos=IN.datos(pl, TAM),                                       # PAT 134
                isa=dict(senales={k: v[0] for k, v in isa51.SENALES.items()}, lugares=isa51.LUGARES, ubicaciones=isa51.UBICACIONES,
                         funciones=isa51.FUNCIONES, relaciones=IN.RELACIONES, acciones_falla=IN.ACCIONES_FALLA, acciones=IN.ACCIONES,
                         alimentaciones=list(IN.ALIMENTACIONES)),                       # PAT 142
                historial=historial or dict(deshacer=0, rehacer=0, etiqueta_deshacer="", etiqueta_rehacer=""))   # PAT 133
