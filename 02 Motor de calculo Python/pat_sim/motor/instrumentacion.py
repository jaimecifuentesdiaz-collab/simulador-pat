"""Instrumentos ISA-5.1 y elementos de lazo ISA-5.4 en el lienzo de Diseño (PAT 134, pedido de Jaime del 04-11-2026).

Funciones sin interfaz, que se prueban solas y que usa pat_sim.motor.lienzo.aplicar_evento:
- agregar(pl, clave, x, y, equipo, corriente): agrega al soltar un símbolo del catálogo «Instrumentación ISA-5.1 y ISA-5.4».
- editar(pl, id, cambios): letras (validadas con la tabla de letras de ISA-5.1), número de lazo, ubicación, descripción, equipo,
  parámetro que mide o controla (debe existir en el equipo), elemento final y tipo de instrumento.
- conectar, editar_senal y quitar_senal: líneas de señal de ISA-5.1 (eléctrica, neumática, enlace de datos, capilar, hidráulica,
  electromagnética o conexión a proceso) del instrumento a un equipo, a una corriente o a otro instrumento.
- mover, quitar, limpiar (borra las líneas que quedaron sin destino), posiciones y datos (lo que dibuja el lienzo).
- lazos(pl): agrupa por número de lazo para la pantalla Lazos de control y su diagrama de lazo ISA-5.4.
PAT 142 (pedido de Jaime del 19-11-2026: lazos de control puestos directo en el lienzo y conectables entre sí):
- agregar_lazo(pl, variable, equipo, …): lazo típico de temperatura, presión, nivel, caudal o concentración con sus instrumentos y
  sus líneas de señal (medición, controlador, convertidor I/P y elemento final), con el número de lazo siguiente libre.
- Campos de ISA-5.4 en cada instrumento (acción en falla, alimentación, acción del controlador y consigna) y relación entre lazos
  en la línea de señal que une instrumentos de lazos distintos (cascada, razón, prealimentación o enclavamiento).
- relaciones(pl), revisar_lazos(pl) (base del validador de la tarea 6) y lazos_lienzo(pl) (rectángulo y rótulo de cada lazo).
El identificador de un instrumento es su etiqueta ISA-5.1 (letras-número, por ejemplo TIC-101), que no se puede repetir.
Fuentes: las mismas de pat_sim.simbolos.isa51 (Carballo y Romero, 2011, Tablas 3, 4, 15 y 17) y la estructura de ISA-5.4.
"""
from __future__ import annotations
import re
from .planta import Planta, Instrumento
from ..simbolos import isa51

GRILLA_INS = 10
TIPOS_DESTINO = ("equipo", "corriente", "instrumento")
# PAT 142: datos mínimos de ISA-5.4 (diapositivas ISA del curso: acción en falla p. 23, alimentación p. 26, consigna p. 27 y
# sentido de acción p. 28) y relación entre lazos (requisito 3 de la p. 32)
ACCIONES_FALLA = {"FC": "Cierra en falla (FC)", "FO": "Abre en falla (FO)", "FL": "Se bloquea en la última posición (FL)",
                  "FI": "Indeterminada en falla (FI)"}
ACCIONES = {"directa": "Directa: sube la medición, sube la salida", "inversa": "Inversa: sube la medición, baja la salida"}
ALIMENTACIONES = ("24 V c.c.", "aire AS 20 psig", "L1, L2, G")
RELACIONES = {"cascada": "Cascada: el controlador maestro fija la consigna del esclavo", "razon": "Razón: relación de caudales",
              "prealimentacion": "Prealimentación: la medición de otro lazo anticipa la perturbación",
              "enclavamiento": "Enclavamiento: acción todo o nada"}
RELACIONES_CORTO = {"cascada": "cascada", "razon": "razón", "prealimentacion": "prealimentación", "enclavamiento": "enclavamiento"}
LARGO_TEXTO_ISA54 = 40


def ident(ins: Instrumento) -> str:
    return isa51.tag(ins.letras, ins.numero)


def buscar(pl: Planta, id_: str) -> Instrumento:
    for i in pl.instrumentos:
        if ident(i) == id_:
            return i
    raise ValueError(f"El instrumento {id_} ya no existe")


def clave_corriente(c) -> str:
    """La misma clave que usa el lienzo para una corriente (pat_sim.motor.lienzo._clave_conexion)."""
    return f"{c.origen}.{c.puerto_origen}>{c.destino}.{c.puerto_destino}"


def clave_senal(origen: str, s: dict) -> str:
    return f"{origen}>{s.get('tipo')}:{s.get('destino')}"


def _redondear(v) -> float:
    return float(round(float(v) / GRILLA_INS) * GRILLA_INS)


def siguiente_numero(pl: Planta, simbolo: str = "", letras: str = "") -> str:
    """Número de lazo libre: el mayor número de lazo + 1 (101 si no hay); para un elemento de ISA-5.4, 1, 2, 3… por código."""
    usados = {ident(i) for i in pl.instrumentos}
    if not isa51.valida_isa51(simbolo):
        n = 1
        while isa51.tag(letras, str(n)) in usados:
            n += 1
        return str(n)
    nums = [int(i.numero) for i in pl.instrumentos if str(i.numero).isdigit() and isa51.valida_isa51(i.simbolo)]
    n = max(nums, default=100) + 1
    while isa51.tag(letras, str(n)) in usados:
        n += 1
    return str(n)


def agregar(pl: Planta, clave: str, x: float | None, y: float | None, equipo: str | None = None, corriente: str | None = None) -> Instrumento:
    """x o y None: el símbolo queda junto a su equipo (o arriba a la izquierda si no tiene) hasta que se mueva."""
    if clave not in isa51.ELEMENTOS:
        raise ValueError(f"Símbolo ISA desconocido: {clave}")
    e = isa51.ELEMENTOS[clave]
    if equipo and equipo not in pl.equipos:
        raise ValueError(f"No existe el equipo {equipo}")
    numero = siguiente_numero(pl, e["simbolo"], e["letras"])
    sin_pos = x is None or y is None             # soltado sobre su equipo: queda junto a él, como los lazos antiguos
    ins = Instrumento(e["letras"], numero, equipo or "", e["ubicacion"], "", None, None,
                      x=None if sin_pos else max(0.0, _redondear(x)), y=None if sin_pos else max(0.0, _redondear(y)), simbolo=e["simbolo"])
    pl.instrumentos.append(ins)
    if corriente and any(clave_corriente(c) == corriente for c in pl.conexiones):   # soltado sobre una corriente: en línea
        ins.conexiones.append(dict(senal="proceso", tipo="corriente", destino=corriente, parametro=None))
    return ins


def _ubicaciones_validas(ins: Instrumento) -> dict:
    return isa51.UBICACIONES if not ins.simbolo else isa51.LUGARES


def editar(pl: Planta, id_: str, cambios: dict) -> str:
    """Aplica los cambios al instrumento id_ (todo o nada). Devuelve el identificador, que cambia si cambian letras o número."""
    ins = buscar(pl, id_)
    letras, numero, simbolo = ins.letras, ins.numero, ins.simbolo
    if "simbolo" in cambios:
        nuevo = str(cambios["simbolo"] or "")
        if nuevo not in isa51.FUNCIONES or (simbolo and simbolo not in isa51.FUNCIONES):
            raise ValueError("Solo se cambia el tipo de una burbuja: discreto, compartido (DCS), computador o PLC")
        simbolo = nuevo
    if "letras" in cambios:
        letras = isa51.validar_codigo(simbolo, cambios["letras"])
    if "numero" in cambios:
        numero = str(cambios["numero"] or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9]{1,8}", numero):
            raise ValueError("El número de lazo debe tener de 1 a 8 letras o cifras, sin espacios")
    nid = isa51.tag(letras, numero)
    if nid != id_ and any(ident(i) == nid for i in pl.instrumentos):
        raise ValueError(f"Ya existe el instrumento {nid}")
    ubic = ins.ubicacion
    if simbolo != ins.simbolo and ubic not in isa51.LUGARES:
        ubic = "panel"                          # una burbuja antigua «dcs» pasa a compartido en el panel principal
    if "ubicacion" in cambios:
        ubic = str(cambios["ubicacion"])
        validas = isa51.UBICACIONES if not simbolo else isa51.LUGARES
        if ubic not in validas:
            raise ValueError(f"Ubicación no válida: {ubic}")
    equipo = ins.equipo
    if "equipo" in cambios:
        equipo = str(cambios["equipo"] or "")
        if equipo and equipo not in pl.equipos:
            raise ValueError(f"No existe el equipo {equipo}")
    parametro = ins.parametro if equipo == ins.equipo else None
    if "parametro" in cambios:
        parametro = cambios["parametro"] or None
    if parametro and (not equipo or parametro not in pl.equipos[equipo].params):
        raise ValueError(f"El equipo {equipo or '(ninguno)'} no tiene el parámetro {parametro}")
    isa54 = {c: _texto_isa54(c, cambios[c]) for c in ("accion_falla", "accion", "alimentacion", "consigna") if c in cambios}   # PAT 142
    ins.letras, ins.numero, ins.simbolo, ins.ubicacion, ins.equipo, ins.parametro = letras, numero, simbolo, ubic, equipo, parametro
    if "descripcion" in cambios:
        ins.descripcion = str(cambios["descripcion"] or "").strip()
    if "elemento_final" in cambios:
        ins.elemento_final = str(cambios["elemento_final"] or "").strip() or None
    for c, v in isa54.items():                  # PAT 142: datos mínimos de ISA-5.4
        setattr(ins, c, v)
    if nid != id_:                              # las líneas que llegaban al instrumento siguen llegando con su nueva etiqueta
        for o in pl.instrumentos:
            for s in o.conexiones:
                if s.get("tipo") == "instrumento" and s.get("destino") == id_:
                    s["destino"] = nid
    return nid


def _texto_isa54(campo: str, valor) -> str:
    """PAT 142: valida un dato de ISA-5.4 (lanza ValueError antes de cambiar nada si no es válido)."""
    v = str(valor or "").strip()
    if campo == "accion_falla":
        v = v.upper()
        if v and v not in ACCIONES_FALLA:
            raise ValueError("La acción en falla debe ser FC (cierra), FO (abre), FL (se bloquea) o FI (indeterminada)")
    elif campo == "accion":
        v = v.lower()
        if v and v not in ACCIONES:
            raise ValueError("La acción del controlador debe ser directa o inversa")
    elif len(v) > LARGO_TEXTO_ISA54:
        raise ValueError(f"La {'alimentación' if campo == 'alimentacion' else 'consigna'} admite hasta {LARGO_TEXTO_ISA54} caracteres")
    return v


def _destino_existe(pl: Planta, tipo: str, destino: str) -> bool:
    if tipo == "equipo":
        return destino in pl.equipos
    if tipo == "corriente":
        return any(clave_corriente(c) == destino for c in pl.conexiones)
    if tipo == "instrumento":
        return any(ident(i) == destino for i in pl.instrumentos)
    return False


def conectar(pl: Planta, origen: str, tipo: str, destino: str, senal: str = "electrica", parametro: str | None = None) -> str:
    ins = buscar(pl, origen)
    if senal not in isa51.SENALES:
        raise ValueError(f"Tipo de señal desconocido: {senal}")
    if tipo not in TIPOS_DESTINO:
        raise ValueError(f"Destino desconocido: {tipo}")
    if tipo == "instrumento" and destino == origen:
        raise ValueError("Un instrumento no se puede conectar consigo mismo")
    if not _destino_existe(pl, tipo, destino):
        raise ValueError(f"No existe {'la corriente' if tipo == 'corriente' else 'el ' + tipo} {destino}")
    parametro = parametro or None
    if parametro and (tipo != "equipo" or parametro not in pl.equipos[destino].params):
        raise ValueError(f"El parámetro {parametro} no existe en {destino}" if tipo == "equipo" else "Solo un equipo tiene parámetros")
    s = dict(senal=senal, tipo=tipo, destino=destino, parametro=parametro)
    if any(clave_senal(origen, x) == clave_senal(origen, s) for x in ins.conexiones):
        raise ValueError(f"Ya existe la línea de señal de {origen} a {destino}")
    if tipo == "instrumento" and any(x.get("tipo") == "instrumento" and x.get("destino") == origen for x in buscar(pl, destino).conexiones):
        raise ValueError(f"Ya existe la línea de señal entre {destino} y {origen}")
    if tipo == "instrumento":                   # PAT 142: una línea entre lazos distintos es una relación entre lazos
        rel = relacion_defecto(ins, buscar(pl, destino))
        if rel:                                 # campo opcional: sin relación no se guarda (las señales quedan como antes)
            s["relacion"] = rel
    ins.conexiones.append(s)
    if tipo == "equipo" and not ins.equipo:     # el primer equipo al que se conecta pasa a ser su equipo
        ins.equipo = destino
        if parametro and not ins.parametro:
            ins.parametro = parametro
    return clave_senal(origen, s)


def nombre_destino(pl: Planta, tipo: str, destino: str) -> str:
    if tipo == "corriente":
        c = next((c for c in pl.conexiones if clave_corriente(c) == destino), None)
        return f"la corriente {c.nombre or 's/n'} ({c.origen} → {c.destino})" if c else destino
    return destino


def _buscar_senal(pl: Planta, clave: str):
    for ins in pl.instrumentos:
        for j, s in enumerate(ins.conexiones):
            if clave_senal(ident(ins), s) == clave:
                return ins, j, s
    raise ValueError("La línea de señal ya no existe")


def editar_senal(pl: Planta, clave: str, cambios: dict) -> str:
    ins, j, s = _buscar_senal(pl, clave)
    nueva = dict(s)
    if "senal" in cambios:
        if cambios["senal"] not in isa51.SENALES:
            raise ValueError(f"Tipo de señal desconocido: {cambios['senal']}")
        nueva["senal"] = cambios["senal"]
    if "parametro" in cambios:
        p = cambios["parametro"] or None
        if p and (s["tipo"] != "equipo" or p not in pl.equipos[s["destino"]].params):
            raise ValueError(f"El parámetro {p} no existe en {s['destino']}")
        nueva["parametro"] = p
    if "relacion" in cambios:                   # PAT 142: cascada, razón, prealimentación, enclavamiento o ninguna
        r = cambios["relacion"] or None
        if r and r not in RELACIONES:
            raise ValueError(f"Relación entre lazos desconocida: {r}. Use {', '.join(RELACIONES)} o ninguna")
        d = _instrumento(pl, s.get("destino")) if s.get("tipo") == "instrumento" else None
        if r and (d is None or not _lazos_distintos(ins, d)):
            raise ValueError("Solo una línea entre instrumentos de lazos distintos es una relación entre lazos")
        if r:
            nueva["relacion"] = r
        else:
            nueva.pop("relacion", None)
    ins.conexiones[j] = nueva
    return clave


def quitar_senal(pl: Planta, clave: str) -> dict:
    ins, j, s = _buscar_senal(pl, clave)
    return ins.conexiones.pop(j)


def mover(pl: Planta, id_: str, x: float, y: float):
    ins = buscar(pl, id_)
    ins.x, ins.y = max(0.0, _redondear(x)), max(0.0, _redondear(y))


def desplazar_de_equipo(pl: Planta, equipo: str, dx: float, dy: float):
    """Al mover un equipo, sus instrumentos con posición propia se mueven con él (los demás ya lo siguen)."""
    for i in pl.instrumentos:
        if i.equipo == equipo and i.x is not None and i.y is not None:
            i.x, i.y = max(0.0, i.x + dx), max(0.0, i.y + dy)


def quitar(pl: Planta, id_: str) -> Instrumento:
    ins = buscar(pl, id_)
    pl.instrumentos.remove(ins)
    limpiar(pl)
    return ins


def limpiar(pl: Planta) -> int:
    """Quita las líneas de señal cuyo destino ya no existe y los parámetros que ya no tiene el equipo. Devuelve cuántas quitó."""
    n = 0
    for ins in pl.instrumentos:
        antes = len(ins.conexiones)
        ins.conexiones[:] = [s for s in ins.conexiones if isinstance(s, dict) and _destino_existe(pl, s.get("tipo"), s.get("destino"))]
        n += antes - len(ins.conexiones)
        for s in ins.conexiones:
            if s.get("parametro") and (s["tipo"] != "equipo" or s["parametro"] not in pl.equipos[s["destino"]].params):
                s["parametro"] = None
        if ins.equipo and ins.equipo not in pl.equipos:
            ins.equipo, ins.parametro = "", None
    return n


def posiciones(pl: Planta, tam: float = 64) -> dict:
    """Centro de cada instrumento: el suyo, o junto a su equipo (sobre él, hacia la derecha, como el diagrama de flujo)."""
    out, cnt, sueltos = {}, {}, 0
    for i in pl.instrumentos:
        if i.x is not None and i.y is not None:
            out[ident(i)] = (float(i.x), float(i.y), False)
            continue
        e = pl.equipos.get(i.equipo)
        if e is not None:
            k = cnt.get(e.id, 0); cnt[e.id] = k + 1
            out[ident(i)] = (float(e.x) + tam + 22 + 38 * k, float(e.y) - 30, True)
        else:
            out[ident(i)] = (30.0 + 40 * sueltos, 20.0, True); sueltos += 1
    return out


def lectura(ins: Instrumento) -> str:
    if not isa51.valida_isa51(ins.simbolo):
        return isa51.NOMBRE_SIMBOLO.get(ins.simbolo, ins.simbolo) + " (código de ISA-5.4)"
    try:
        return isa51.interpretar(ins.letras)["descripcion"]
    except ValueError:
        return "Letras no válidas"


def catalogo() -> list[dict]:
    """Entradas de la categoría «Instrumentación ISA-5.1 y ISA-5.4» del catálogo del lienzo, con su símbolo SVG."""
    return [dict(clave=k, nombre=e["nombre"], grupo=e["grupo"], simbolo=e["simbolo"], ubicacion=e["ubicacion"], letras=e["letras"],
                 isa51=e["isa51"], fuente=e["fuente"], svg=isa51.simbolo_svg(e["simbolo"], e["letras"], "", 0, 0, e["ubicacion"]))
            for k, e in isa51.ELEMENTOS.items()]


def datos(pl: Planta, tam: float = 64) -> list[dict]:
    """Instrumentos para dibujar en el lienzo. dx, dy: posición relativa a su equipo (el lienzo la usa para que sigan al equipo).
    PAT 142: más el lazo, los datos de ISA-5.4, si es controlador o elemento final y, en cada línea de señal, la relación entre lazos."""
    pos = posiciones(pl, tam); out = []
    por_id = {ident(i): i for i in pl.instrumentos}
    for i in pl.instrumentos:
        k = ident(i); x, y, auto = pos[k]; e = pl.equipos.get(i.equipo)
        eqp = e.params if e is not None else {}
        out.append(dict(
            lazo=lazo_de(i) or "", accion_falla=i.accion_falla or "", alimentacion=i.alimentacion or "", accion=i.accion or "",
            consigna=i.consigna or "", es_controlador=es_controlador(i), es_final=es_final(i),
            
            id=k, letras=i.letras, numero=i.numero, simbolo=i.simbolo, simbolo_nombre=isa51.NOMBRE_SIMBOLO.get(i.simbolo, i.simbolo),
            isa51=isa51.valida_isa51(i.simbolo), lectura=lectura(i), ubicacion=i.ubicacion,
            ubicacion_nombre=isa51.UBICACIONES.get(i.ubicacion, i.ubicacion), descripcion=i.descripcion or "", equipo=i.equipo or "",
            parametro=i.parametro or "", parametro_nombre=eqp[i.parametro].nombre if i.parametro in eqp else "",
            elemento_final=i.elemento_final or "", x=x, y=y, auto=auto,
            dx=(x - float(e.x)) if e is not None else None, dy=(y - float(e.y)) if e is not None else None,
            svg=isa51.simbolo_svg(i.simbolo, i.letras, i.numero, 0, 0, i.ubicacion),
            ubicaciones=list(_ubicaciones_validas(i)),
            conexiones=[dict(clave=clave_senal(k, s), senal=s.get("senal"), senal_nombre=isa51.SENALES.get(s.get("senal"), ("",))[0],
                             tipo=s.get("tipo"), destino=s.get("destino"), parametro=s.get("parametro") or "",
                             parametro_nombre=(pl.equipos[s["destino"]].params[s["parametro"]].nombre
                                               if s.get("tipo") == "equipo" and s.get("parametro") and s["destino"] in pl.equipos
                                               and s["parametro"] in pl.equipos[s["destino"]].params else ""),
                             relacion=s.get("relacion") or "", relacion_nombre=RELACIONES_CORTO.get(s.get("relacion") or "", ""),
                             entre_lazos=s.get("tipo") == "instrumento" and s.get("destino") in por_id
                             and _lazos_distintos(i, por_id[s.get("destino")]))
                        for s in i.conexiones if isinstance(s, dict)]))
    return out


def lazos(pl: Planta) -> list[dict]:
    """Lazos por número: los instrumentos ISA-5.1 que comparten número. El representante (el que se dibuja en la sala de
    control del diagrama de lazo ISA-5.4) es el que tiene función de controlador (C) o, si no hay, el primero. caja: etiqueta de
    una caja de conexiones unida por una línea de señal a algún instrumento del lazo, si la hay."""
    grupos: dict = {}
    for i in pl.instrumentos:
        if isa51.valida_isa51(i.simbolo):
            try:
                isa51.interpretar(i.letras)
            except ValueError:
                continue
            grupos.setdefault(str(i.numero), []).append(i)
    out = []
    for num, ms in grupos.items():
        rep = next((m for m in ms if "C" in m.letras[1:] and m.simbolo in ("", "discreto", "compartido", "computador", "plc")), None) or \
            next((m for m in ms if "C" in m.letras[1:]), ms[0])
        ids = {ident(m) for m in ms}
        cajas = [ident(c) for c in pl.instrumentos if c.simbolo == "caja_conexiones" and
                 (any(s.get("tipo") == "instrumento" and s.get("destino") in ids for s in c.conexiones) or
                  any(s.get("tipo") == "instrumento" and s.get("destino") == ident(c) for m in ms for s in m.conexiones))]
        senales = [dict(origen=ident(m), **s) for m in ms for s in m.conexiones if isinstance(s, dict)]
        out.append(dict(numero=num, representante=rep, miembros=ms, caja=cajas[0] if cajas else None, senales=senales))
    return out


# ================================================================== PAT 142: lazos de control en el lienzo
# Clasificación por las letras sucesivas de ISA-5.1 (diapositivas ISA del curso, p. 14): C controlador, E elemento primario,
# T transmisor, V válvula y Z elemento final sin clasificar; el convertidor I/P es el símbolo «convertidor» (p. 18).
VARIABLE_NOMBRE = {"T": "temperatura", "P": "presión", "L": "nivel", "F": "caudal", "A": "concentración"}
COLORES_LAZO = ("#1b7a5a", "#2563eb", "#b45309", "#7c3aed", "#be123c", "#0e7490", "#4d7c0f", "#9d174d")
SIMBOLOS_FINALES = ("valvula_diafragma", "valvula_piston", "valvula_motor", "valvula_solenoide", "valvula_manual", "valvula_alivio")


def _funciones(letras: str) -> str:
    """Letras sucesivas sin el modificador de la primera letra (D, F, Q o J; p. 15, nota 3)."""
    t = str(letras or "").upper()[1:]
    return t[1:] if len(t) > 1 and t[0] in isa51.MODIFICADORES else t


def lazo_de(ins: Instrumento) -> str | None:
    """Número de lazo de un instrumento ISA-5.1 con letras válidas (los elementos de ISA-5.4, como cajas y tarjetas, no forman lazo)."""
    if not isa51.valida_isa51(ins.simbolo):
        return None
    try:
        isa51.interpretar(ins.letras)
    except ValueError:
        return None
    return str(ins.numero) if str(ins.numero or "").strip() else None


def es_controlador(ins: Instrumento) -> bool:
    return lazo_de(ins) is not None and "C" in _funciones(ins.letras)


def es_convertidor(ins: Instrumento) -> bool:
    return ins.simbolo == "convertidor"


def es_final(ins: Instrumento) -> bool:
    f = _funciones(ins.letras)
    return lazo_de(ins) is not None and not es_controlador(ins) and (ins.simbolo in SIMBOLOS_FINALES or "V" in f or "Z" in f)


def es_medicion(ins: Instrumento) -> bool:
    f = _funciones(ins.letras)
    return lazo_de(ins) is not None and not es_controlador(ins) and not es_final(ins) and ("T" in f or "E" in f)


def _instrumento(pl: Planta, id_: str):
    return next((i for i in pl.instrumentos if ident(i) == id_), None)


def _lazos_distintos(a: Instrumento, b: Instrumento) -> bool:
    la, lb = lazo_de(a), lazo_de(b)
    return bool(la and lb and la != lb)


def relacion_defecto(origen: Instrumento, destino: Instrumento):
    """Relación por defecto de una línea de señal entre dos instrumentos. False: mismo lazo (no es relación entre lazos).
    Controlador a controlador = cascada (el maestro fija la consigna del esclavo); medición de otro lazo a un controlador =
    prealimentación; el resto queda sin relación (None) y se elige en Propiedades."""
    if not _lazos_distintos(origen, destino):
        return False
    if es_controlador(origen) and es_controlador(destino):
        return "cascada"
    if es_medicion(origen) and es_controlador(destino):
        return "prealimentacion"
    return None


# Lazos típicos: (letras, elemento del catálogo ISA, papel). El controlador va en el DCS (control compartido en el panel
# principal; ISA p. 10 y 11), el transmisor, el convertidor I/P y la válvula en campo (ejemplos de las pp. 18 y 34).
TIPICOS = {
    "temperatura": dict(letra="T", nombre="temperatura", miembros=(("TE", "termopozo", "primario"), ("TT", "transmisor", "transmisor"),
                        ("TIC", "controlador", "controlador"), ("TY", "convertidor_ip", "convertidor"), ("TV", "valvula_diafragma", "final")),
                        parametros=("T_salida", "T_aire_entrada", "T_final", "TN", "T1", "Ts", "T_ebullicion", "T")),
    "presion": dict(letra="P", nombre="presión", miembros=(("PT", "transmisor", "transmisor"), ("PIC", "controlador", "controlador"),
                    ("PY", "convertidor_ip", "convertidor"), ("PV", "valvula_diafragma", "final")),
                    parametros=("P", "presion", "P_vapor", "p_vapor", "P_trabajo")),
    "nivel": dict(letra="L", nombre="nivel", miembros=(("LT", "transmisor", "transmisor"), ("LIC", "controlador", "controlador"),
                  ("LY", "convertidor_ip", "convertidor"), ("LV", "valvula_diafragma", "final")),
                  parametros=("nivel", "nivel_pct", "nivel_m")),
    "caudal": dict(letra="F", nombre="caudal", miembros=(("FE", "placa_orificio", "primario"), ("FT", "transmisor", "transmisor"),
                   ("FIC", "controlador", "controlador"), ("FY", "convertidor_ip", "convertidor"), ("FV", "valvula_diafragma", "final")),
                   parametros=("caudal", "carga_t_h", "Q", "caudal_m3h")),
    # Análisis (primera letra A de ISA-5.1, p. 14): °Brix en el tomate, humedad o sólidos en la biomasa
    "concentracion": dict(letra="A", nombre="concentración", miembros=(("AT", "transmisor", "transmisor"), ("AIC", "controlador", "controlador"),
                          ("AY", "convertidor_ip", "convertidor"), ("AV", "valvula_diafragma", "final")),
                          parametros=("brix_salida", "humedad_salida", "x_salida", "brix_jugo", "solidos_salida")),
}
NOMBRE_TIPICO = {k: v["nombre"] for k, v in TIPICOS.items()}
# Alimentación por papel (ISA p. 26): transmisor de dos hilos con 24 V c.c. de la fuente del lazo, controlador del DCS con
# alimentación eléctrica L1, L2, G y convertidor I/P con aire de instrumentos AS 20 psig; el elemento primario y la válvula no
# llevan alimentación propia (la válvula recibe 3 a 15 psig del I/P). Supuesto de un lazo electrónico con actuador neumático.
ALIMENTACION_PAPEL = {"transmisor": "24 V c.c.", "controlador": "L1, L2, G", "convertidor": "aire AS 20 psig"}


def catalogo_tipicos() -> list[dict]:
    """Entradas del grupo «Lazos típicos» del catálogo del lienzo en la vista «lazos», con el símbolo del controlador."""
    out = []
    for k, t in TIPICOS.items():
        letras = [m[0] for m in t["miembros"]]
        ctl = next(m[0] for m in t["miembros"] if m[2] == "controlador")
        out.append(dict(variable=k, nombre=f"Lazo de control de {t['nombre']}", grupo="Lazos típicos", letras=" · ".join(letras),
                        controlador=ctl, svg=isa51.simbolo_svg("compartido", ctl, "", 0, 0, "panel")))
    return out


def parametro_de(pl: Planta, variable: str, equipo: str) -> str | None:
    """Parámetro del equipo que gobierna un lazo típico (temperatura de salida, presión, nivel, caudal o °Brix); None si no tiene."""
    e = pl.equipos.get(equipo)
    if e is None or variable not in TIPICOS:
        return None
    for p in TIPICOS[variable]["parametros"]:
        if p in e.params and not isinstance(e.params[p].valor, (str, bool)):
            return p
    if variable == "temperatura":
        return next((p for p, v in e.params.items() if p.startswith("T_") and not isinstance(v.valor, (str, bool))), None)
    return None


def _consigna(pl: Planta, equipo: str, parametro: str | None) -> str:
    """Punto de consigna inicial = valor actual del parámetro con su unidad (fracción kg/kg en °Brix o en % de sólidos)."""
    if not parametro:
        return ""
    p = pl.equipos[equipo].params[parametro]
    try:
        v = float(p.valor)
    except (TypeError, ValueError):
        return ""
    if p.unidad == "kg/kg":
        v, u = 100 * v, ("°Brix" if pl.rubro == "tomate" else "% de sólidos")
    else:
        u = "" if p.unidad in ("—", "-", None) else p.unidad
    t = f"{v:.1f}".replace(".", ",")
    return f"{t} {u}".strip()[:LARGO_TEXTO_ISA54]


def _corriente_final(pl: Planta, equipo: str):
    """Corriente sobre la que actúa el elemento final: la de servicio del equipo (vapor, calor o agua); si no tiene, su entrada
    de proceso; si tampoco, su salida. Devuelve (clave, es_enfriamiento) o (None, False)."""
    def tipo(c):
        try:
            return pl.tipo_conexion(c)
        except Exception:
            return ""
    ent = [c for c in pl.conexiones if c.destino == equipo]
    serv = [c for c in ent if pl.es_servicio(c) and tipo(c) != "electricidad"]
    for pref in ("vapor", "calor", "agua"):
        c = next((c for c in serv if tipo(c) == pref), None)
        if c is not None:
            return clave_corriente(c), pref == "agua"
    c = next(iter(serv), None) or next((c for c in ent if not pl.es_servicio(c)), None) \
        or next((c for c in pl.conexiones if c.origen == equipo and not pl.es_servicio(c)), None)
    return (clave_corriente(c), "agua" in (tipo(c) or "")) if c is not None else (None, False)


def _numero_lazo(pl: Planta, letras: list, numero=None) -> str:
    usados = {ident(i) for i in pl.instrumentos}
    if numero is not None:
        n = str(numero).strip()
        if not re.fullmatch(r"[A-Za-z0-9]{1,8}", n):
            raise ValueError("El número de lazo debe tener de 1 a 8 letras o cifras, sin espacios")
        rep = [isa51.tag(l, n) for l in letras if isa51.tag(l, n) in usados]
        if rep:
            raise ValueError(f"Ya existe {', '.join(rep)}: elija otro número de lazo")
        return n
    lazos_usados = {lazo_de(i) for i in pl.instrumentos} - {None}
    nums = [int(x) for x in lazos_usados if x.isdigit()]
    n = max(nums, default=100) + 1
    while str(n) in lazos_usados or any(isa51.tag(l, str(n)) in usados for l in letras):
        n += 1
    return str(n)


def _fila_libre(pl: Planta, x0: float, y0: float, n: int, paso: float = 50, tam: float = 64, eq=None) -> list:
    """n posiciones en fila (grilla de 10) que no se encimen con los instrumentos que ya están (otros lazos): si la fila choca,
    se corre 60 px hacia arriba; si se sale por arriba, sigue bajo el equipo."""
    ocup = [(x, y) for x, y, _a in posiciones(pl, tam).values()]
    y = y0
    for k in range(40):
        fila = [(_redondear(x0 + paso * j), _redondear(y)) for j in range(n)]
        if all(abs(a - b) >= 44 or abs(c - d) >= 44 for a, c in fila for b, d in ocup):
            return [(max(0.0, a), max(0.0, c)) for a, c in fila]
        y -= 60
        if y < 20:
            y = (float(eq.y) + tam + 90 + 60 * k) if eq is not None else y0 + 60 * (k + 1)
    return [(max(0.0, _redondear(x0 + paso * j)), max(0.0, _redondear(y0))) for j in range(n)]


def _lista_y(ids: list) -> str:
    return ids[0] if len(ids) == 1 else ", ".join(ids[:-1]) + " y " + ids[-1]


def agregar_lazo(pl: Planta, variable: str, equipo: str, parametro: str | None = None, x: float | None = None, y: float | None = None,
                 corriente: str | None = None, numero=None) -> dict:
    """Lazo típico soltado sobre un equipo: crea sus instrumentos ISA-5.1 con el número de lazo siguiente libre (o numero) y sus
    líneas de señal: medición a proceso del equipo, transmisor a controlador eléctrica, controlador a convertidor I/P eléctrica, I/P a
    válvula neumática y válvula a proceso de la corriente (la de servicio del equipo si no se da corriente). x, y: inicio de la fila
    (si no, sobre el equipo). Devuelve {numero, variable, equipo, parametro, instrumentos, senales, mensaje}. Todo o nada."""
    variable = str(variable or "").strip().lower()
    if variable not in TIPICOS:
        raise ValueError(f"Lazo típico desconocido: {variable}. Use {', '.join(TIPICOS)}")
    if not equipo or equipo not in pl.equipos:
        raise ValueError("Suelte el lazo típico sobre un equipo de la planta" if not equipo else f"No existe el equipo {equipo}")
    t = TIPICOS[variable]; eq = pl.equipos[equipo]
    if parametro:
        if parametro not in eq.params:
            raise ValueError(f"El equipo {equipo} no tiene el parámetro {parametro}")
    else:
        parametro = parametro_de(pl, variable, equipo)
    if corriente and not any(clave_corriente(c) == corriente for c in pl.conexiones):
        raise ValueError(f"No existe la corriente {corriente}")
    enfria = False
    if not corriente:
        corriente, enfria = _corriente_final(pl, equipo)
    letras = [m[0] for m in t["miembros"]]
    num = _numero_lazo(pl, letras, numero)
    sin_pos = x is None or y is None
    x0 = float(eq.x) - 10 if sin_pos else float(x)
    y0 = float(eq.y) - 70 if sin_pos else float(y)
    pos = _fila_libre(pl, x0, y0, len(letras), eq=eq)
    antes = list(pl.instrumentos)
    try:
        ids, papel = [], {}
        for (le, clave, rol), (px, py) in zip(t["miembros"], pos):
            e = isa51.ELEMENTOS[clave]
            ins = Instrumento(le, num, equipo, e["ubicacion"], "", None, None, x=px, y=py, simbolo=e["simbolo"])
            ins.alimentacion = ALIMENTACION_PAPEL.get(rol, "")
            if rol == "primario":
                ins.descripcion = f"Elemento primario de {t['nombre']} en {equipo}"
            elif rol == "transmisor":
                ins.descripcion, ins.parametro = f"Transmisor de {t['nombre']} de {equipo}", parametro
            elif rol == "controlador":
                ins.descripcion, ins.parametro = f"Control de {t['nombre']} de {equipo} {eq.nombre}"[:120], parametro
                # Acción inversa: con la válvula FC (aire abre) sobre el servicio, si la medición sube la salida baja para cerrar;
                # con la válvula FO (aire cierra) sobre agua de enfriamiento, si la medición sube la salida baja para abrir (ISA p. 28).
                ins.accion = "inversa"
                ins.consigna = _consigna(pl, equipo, parametro)
            elif rol == "convertidor":
                ins.descripcion = "Convertidor I/P: señal eléctrica de 4 a 20 mA a neumática de 3 a 15 psig"
            else:
                ins.descripcion = f"Válvula de control de {t['nombre']} de {equipo}"
                # Falla segura (ISA p. 23): sin aire o sin señal la válvula de vapor, calor o alimentación cierra (FC) y no
                # sobrecalienta ni rebalsa; la de agua de enfriamiento abre (FO) y sigue enfriando. Supuesto de diseño.
                ins.accion_falla = "FO" if enfria else "FC"
            pl.instrumentos.append(ins)
            ids.append(ident(ins)); papel[rol] = ident(ins)
        ctl = papel["controlador"]; fin = papel["final"]
        _instrumento(pl, ctl).elemento_final = fin
        senales = []
        med = papel.get("primario") or papel["transmisor"]
        senales.append(conectar(pl, med, "equipo", equipo, "proceso", parametro))
        if "primario" in papel:     # elemento primario al transmisor: capilar en temperatura (ISA p. 18), tomas de proceso en caudal (p. 34)
            senales.append(conectar(pl, papel["primario"], "instrumento", papel["transmisor"], "capilar" if variable == "temperatura" else "proceso"))
        senales.append(conectar(pl, papel["transmisor"], "instrumento", ctl, "electrica"))
        senales.append(conectar(pl, ctl, "instrumento", papel["convertidor"], "electrica"))
        senales.append(conectar(pl, papel["convertidor"], "instrumento", fin, "neumatica"))
        if corriente:
            senales.append(conectar(pl, fin, "corriente", corriente, "proceso"))
        else:
            senales.append(conectar(pl, fin, "equipo", equipo, "proceso"))
    except Exception:
        pl.instrumentos[:] = antes
        for i in pl.instrumentos:            # quita las líneas que alcanzaron a llegar a los instrumentos nuevos
            i.conexiones[:] = [s for s in i.conexiones if not (s.get("tipo") == "instrumento" and s.get("destino") not in {ident(a) for a in antes})]
        raise
    msg = (f"Agregado el lazo {num} de control de {t['nombre']} en {equipo} {eq.nombre}: {_lista_y(ids)}."
           + ("" if parametro else " Elija en Propiedades el parámetro que gobierna el controlador."))
    return dict(numero=num, variable=variable, equipo=equipo, parametro=parametro, instrumentos=ids, senales=senales, mensaje=msg,
                controlador=ctl)


def titulo_lazo(L: dict) -> str:
    """Descripción en palabras de la función del lazo, para su título (ISA p. 32, requisito 2): «Lazo 101 · control de temperatura»."""
    rep = L["representante"]; le = rep.letras[:1].upper()
    var = VARIABLE_NOMBRE.get(le) or isa51.PRIMERA_LETRA.get(le, "variable").split(",")[0].lower()
    f = _funciones(rep.letras)
    func = "control" if "C" in f else ("indicación" if "I" in f else ("transmisión" if "T" in f else "medición"))
    return f"Lazo {L['numero']} · {func} de {var}"


def relaciones(pl: Planta) -> list[dict]:
    """Relaciones entre lazos (ISA p. 32, requisito 3): cada línea de señal de un instrumento de un lazo a uno de otro lazo.
    {lazo_origen, lazo_destino, tipo (cascada, razon, prealimentacion, enclavamiento o None), nombre, senal (clave), origen, destino}."""
    out = []
    por_id = {ident(i): i for i in pl.instrumentos}
    for i in pl.instrumentos:
        for s in i.conexiones:
            if not isinstance(s, dict) or s.get("tipo") != "instrumento" or s.get("destino") not in por_id:
                continue
            d = por_id[s["destino"]]
            if not _lazos_distintos(i, d):
                continue
            tp = s.get("relacion") or None
            out.append(dict(lazo_origen=lazo_de(i), lazo_destino=lazo_de(d), tipo=tp, nombre=RELACIONES_CORTO.get(tp, "sin relación"),
                            senal=clave_senal(ident(i), s), origen=ident(i), destino=ident(d)))
    return out


def lazos_lienzo(pl: Planta, tam: float = 64) -> list[dict]:
    """Lazos para el lienzo en la vista «lazos»: número, color, letras del controlador, miembros, caja que los encierra (x, y,
    ancho, alto, con margen para el rótulo), título y relaciones con otros lazos."""
    pos = posiciones(pl, tam); rels = relaciones(pl); out = []
    for k, L in enumerate(sorted(lazos(pl), key=lambda L: (not str(L["numero"]).isdigit(), int(L["numero"]) if str(L["numero"]).isdigit() else 0, str(L["numero"])))):
        ids = [ident(m) for m in L["miembros"]]
        xs = [pos[i][0] for i in ids if i in pos]; ys = [pos[i][1] for i in ids if i in pos]
        caja = dict(x=min(xs) - 28, y=min(ys) - 34, ancho=max(xs) - min(xs) + 56, alto=max(ys) - min(ys) + 62) if xs else None
        rel = [dict(lazo=r["lazo_destino"] if r["lazo_origen"] == L["numero"] else r["lazo_origen"], tipo=r["tipo"], nombre=r["nombre"],
                    senal=r["senal"], sentido="sale" if r["lazo_origen"] == L["numero"] else "llega")
               for r in rels if L["numero"] in (r["lazo_origen"], r["lazo_destino"])]
        rep = L["representante"]
        out.append(dict(numero=L["numero"], color=COLORES_LAZO[k % len(COLORES_LAZO)], controlador=rep.letras if es_controlador(rep) else "",
                        representante=ident(rep), miembros=ids, caja=caja, titulo=titulo_lazo(L), relaciones=rel))
    return out


def _r(nivel, lazo, objeto, mensaje, pista, fuente, regla=None):
    """PAT 143: regla = número de la regla ISA (1 a 15) de la tabla del curso, para las pistas progresivas del validador."""
    return dict(nivel=nivel, lazo=lazo, objeto=objeto, mensaje=mensaje, pista=pista, fuente=fuente, regla=regla)


def revisar_lazos(pl: Planta) -> list[dict]:
    """Revisión de los lazos (base del validador de la tarea 6). Lista de {nivel («error» o «aviso»), lazo, objeto, mensaje, pista,
    fuente}; fuente «ISA p. …» si la regla sale de las diapositivas ISA del curso, «buena práctica» si no (tabla de 15 reglas del
    resumen de la tarea 2, sección 2.6). Un lazo declarado con un solo instrumento y sin líneas de señal (los lazos resumidos de los
    ejemplos) solo recibe avisos: se completa en el lienzo. Planta sin instrumentos: un aviso."""
    if not pl.instrumentos:
        return [_r("aviso", None, None, "La planta no tiene lazos de control todavía.",
                   "Arrastre un lazo típico del catálogo del lienzo sobre el equipo cuya variable quiere controlar.", "buena práctica", 5)]
    out = []
    por_id = {ident(i): i for i in pl.instrumentos}
    llegan: dict = {}
    for i in pl.instrumentos:
        for s in i.conexiones:
            if isinstance(s, dict) and s.get("tipo") == "instrumento":
                llegan.setdefault(s.get("destino"), []).append((i, s))
    for L in lazos(pl):
        num, ms = L["numero"], L["miembros"]; ids = {ident(m) for m in ms}
        resumido = len(ms) == 1 and not ms[0].conexiones
        # 1 y 5: misma primera letra en todo el lazo, salvo auxiliares como el I/P (ISA p. 19; número repetido, p. 8 y 12)
        prim = sorted({m.letras[:1].upper() for m in ms if not es_convertidor(m)})
        if len(prim) > 1:
            out.append(_r("aviso", num, ident(ms[0]), f"El número de lazo {num} se repite con distintas primeras letras ({', '.join(prim)}).",
                          "En un lazo todos los instrumentos llevan la primera letra de la variable medida (una válvula que mueve un "
                          "controlador de nivel es LV): cambie las letras o dé otro número al otro lazo.", "ISA p. 19", 2))
        ctl = [m for m in ms if es_controlador(m)]
        med = [m for m in ms if es_medicion(m)]
        fin = [m for m in ms if es_final(m)]
        if ctl and not resumido:
            c = ctl[0]
            if not med:
                out.append(_r("error", num, ident(c), f"El lazo {num} tiene el controlador {ident(c)} pero no tiene medición.",
                              f"Agregue un transmisor {c.letras[0]}T-{num} unido a proceso del equipo y con señal eléctrica a {ident(c)}.",
                              "ISA pp. 18 y 34", 5))
            if not fin:
                out.append(_r("error", num, ident(c), f"El lazo {num} tiene el controlador {ident(c)} pero no tiene elemento final.",
                              f"Agregue una válvula {c.letras[0]}V-{num} sobre la corriente que se manipula y únala al controlador, con "
                              "un convertidor I/P si el actuador es neumático.", "ISA pp. 18 y 34", 5))
            # orden medición, controlador, elemento final, siguiendo las líneas de señal entre instrumentos del lazo
            sig = {i_: [s.get("destino") for s in por_id[i_].conexiones if isinstance(s, dict) and s.get("tipo") == "instrumento"
                        and s.get("destino") in ids] for i_ in ids}

            def alcanza(a, b):
                vistos, pila = set(), [a]
                while pila:
                    x = pila.pop()
                    if x == b:
                        return True
                    if x in vistos:
                        continue
                    vistos.add(x); pila.extend(sig.get(x, []))
                return False
            if med and not any(alcanza(ident(m), ident(c)) for m in med):
                out.append(_r("error", num, ident(c), f"En el lazo {num} ninguna medición llega con una señal a {ident(c)}.",
                              f"Una con una línea de señal eléctrica el transmisor ({', '.join(ident(m) for m in med)}) hacia {ident(c)}.",
                              "ISA pp. 18 y 34", 5))
            for f in fin:
                if not alcanza(ident(c), ident(f)):
                    out.append(_r("error", num, ident(f), f"En el lazo {num} el controlador {ident(c)} no llega con una señal al elemento final {ident(f)}.",
                                  f"Una {ident(c)} con {ident(f)}: señal eléctrica al convertidor I/P y neumática del I/P a la válvula.",
                                  "ISA p. 18", 5))
        if not resumido:
            for f in fin:          # el elemento final actúa sobre una corriente o un equipo
                if not any(isinstance(s, dict) and s.get("tipo") in ("corriente", "equipo") for s in f.conexiones):
                    out.append(_r("error", num, ident(f), f"El elemento final {ident(f)} no actúa sobre ninguna corriente ni equipo.",
                                  f"Arrastre desde el punto azul de {ident(f)} hasta la corriente que manipula (por ejemplo el vapor del equipo).",
                                  "ISA p. 18; regla 5, buena práctica", 5))
            if med and not any(isinstance(s, dict) and s.get("tipo") in ("corriente", "equipo") for m in med for s in m.conexiones):
                out.append(_r("error", num, ident(med[0]), f"La medición del lazo {num} no está unida a proceso.",
                              f"Una {ident(med[0])} con una línea de conexión a proceso hasta el equipo o la corriente que mide.",
                              "regla 8, buena práctica (ejemplos ISA pp. 18 y 34)", 8))
            for m in ms:           # el convertidor I/P recibe eléctrica y entrega neumática
                if not es_convertidor(m):
                    continue
                ent = [s for _o, s in llegan.get(ident(m), [])]
                sal = [s for s in m.conexiones if isinstance(s, dict) and s.get("tipo") == "instrumento"]
                if any(s.get("senal") != "electrica" for s in ent) or any(s.get("senal") != "neumatica" for s in sal):
                    out.append(_r("error", num, ident(m), f"El convertidor I/P {ident(m)} debe recibir señal eléctrica y entregar señal neumática.",
                                  "Cambie en Propiedades el tipo de cada línea: eléctrica la que llega del controlador y neumática la que va a la válvula.",
                                  "ISA p. 17 y 18; regla 7", 7))
        # 10: acción en falla del elemento final y fuente de alimentación del lazo (ISA p. 32, requisitos 6 y 7)
        for f in fin:
            if not f.accion_falla:
                out.append(_r("aviso", num, ident(f), f"El elemento final {ident(f)} no declara su acción en falla.",
                              "Elija en Propiedades FC (cierra), FO (abre), FL (se bloquea) o FI (indeterminada) según el estado seguro.",
                              "ISA p. 32, requisito 7", 10))
            n_mando = len([1 for _o, s in llegan.get(ident(f), [])])
            if n_mando > 1:
                out.append(_r("aviso", num, ident(f), f"El elemento final {ident(f)} recibe {n_mando} señales de mando.",
                              "Un elemento final recibe una sola señal de mando: deje una y use una relación (cascada o razón) entre los controladores.",
                              "buena práctica (regla 15)", 15))
        if not any(m.alimentacion for m in ms):
            out.append(_r("aviso", num, ident(L["representante"]), f"El lazo {num} no declara su fuente de alimentación.",
                          "Escriba en Propiedades la alimentación: 24 V c.c. del transmisor, L1, L2, G del controlador o aire AS 20 psig del I/P.",
                          "ISA p. 32, requisito 6 (p. 26)", 10))
        for c in ctl:              # 14: acción y consigna visibles en el controlador
            if not c.accion or not c.consigna:
                falta = " y ".join(x for x, v in (("la acción", c.accion), ("la consigna", c.consigna)) if not v)
                out.append(_r("aviso", num, ident(c), f"El controlador {ident(c)} no declara {falta}.",
                              "Escriba en Propiedades la acción (directa o inversa) y la consigna con su unidad.", "ISA pp. 27 y 28; obligatoriedad, buena práctica", 14))
    return out
