"""Instrumentos ISA-5.1 y elementos de lazo ISA-5.4 en el lienzo de Diseño (PAT 134, pedido de Jaime del 04-11-2026).

Funciones sin interfaz, que se prueban solas y que usa pat_sim.motor.lienzo.aplicar_evento:
- agregar(pl, clave, x, y, equipo, corriente): agrega al soltar un símbolo del catálogo «Instrumentación ISA-5.1 y ISA-5.4».
- editar(pl, id, cambios): letras (validadas con la tabla de letras de ISA-5.1), número de lazo, ubicación, descripción, equipo,
  parámetro que mide o controla (debe existir en el equipo), elemento final y tipo de instrumento.
- conectar, editar_senal y quitar_senal: líneas de señal de ISA-5.1 (eléctrica, neumática, enlace de datos, capilar, hidráulica,
  electromagnética o conexión a proceso) del instrumento a un equipo, a una corriente o a otro instrumento.
- mover, quitar, limpiar (borra las líneas que quedaron sin destino), posiciones y datos (lo que dibuja el lienzo).
- lazos(pl): agrupa por número de lazo para la pestaña Instrumentación y su diagrama de lazo ISA-5.4.
El identificador de un instrumento es su etiqueta ISA-5.1 (letras-número, por ejemplo TIC-101), que no se puede repetir.
Fuentes: las mismas de pat_sim.simbolos.isa51 (Carballo y Romero, 2011, Tablas 3, 4, 15 y 17) y la estructura de ISA-5.4.
"""
from __future__ import annotations
import re
from .planta import Planta, Instrumento
from ..simbolos import isa51

GRILLA_INS = 10
TIPOS_DESTINO = ("equipo", "corriente", "instrumento")


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
    ins.letras, ins.numero, ins.simbolo, ins.ubicacion, ins.equipo, ins.parametro = letras, numero, simbolo, ubic, equipo, parametro
    if "descripcion" in cambios:
        ins.descripcion = str(cambios["descripcion"] or "").strip()
    if "elemento_final" in cambios:
        ins.elemento_final = str(cambios["elemento_final"] or "").strip() or None
    if nid != id_:                              # las líneas que llegaban al instrumento siguen llegando con su nueva etiqueta
        for o in pl.instrumentos:
            for s in o.conexiones:
                if s.get("tipo") == "instrumento" and s.get("destino") == id_:
                    s["destino"] = nid
    return nid


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
    """Instrumentos para dibujar en el lienzo. dx, dy: posición relativa a su equipo (el lienzo la usa para que sigan al equipo)."""
    pos = posiciones(pl, tam); out = []
    for i in pl.instrumentos:
        k = ident(i); x, y, auto = pos[k]; e = pl.equipos.get(i.equipo)
        eqp = e.params if e is not None else {}
        out.append(dict(
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
                                               and s["parametro"] in pl.equipos[s["destino"]].params else ""))
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
