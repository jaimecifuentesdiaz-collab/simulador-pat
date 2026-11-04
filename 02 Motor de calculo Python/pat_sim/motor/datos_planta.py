"""Datos de placa y mediciones de la planta (PAT 133, mejora 19).

Sin visita a la planta, los parámetros de los equipos vienen de la DIA, del fabricante, de la literatura o son supuestos.
Este módulo entrega una plantilla CSV en formato chileno (separador punto y coma, coma decimal, fecha dd-mm-aaaa) con los
parámetros numéricos de cada equipo, y aplica las filas que el usuario llene: reemplaza el valor supuesto por el medido,
valida la unidad (con conversiones simples) y el rango del parámetro, lo marca con la categoría «Medido» con su fuente y su
fecha, y vuelve a resolver la planta. Si la planta no resuelve con los datos nuevos, deshace todos los cambios.

Las marcas «Medido» se guardan además en pl.globales["datos_medidos"], que viaja con la versión guardada (la versión solo
guarda los valores de los parámetros, no su categoría): restaurar_medidos(pl) las vuelve a poner al cargar la planta."""
from __future__ import annotations
import csv, io, math, re
from datetime import date, datetime
from .equipos import OPCIONALES

CATEGORIA_MEDIDO = "Medido"
CLAVE_GLOBAL = "datos_medidos"
COLUMNAS = ("equipo", "parametro", "valor", "unidad", "fuente", "fecha", "referencia")
OBLIGATORIAS = ("equipo", "parametro", "valor", "unidad", "fuente", "fecha")

# Conversiones de unidad aceptadas: (unidad del archivo, unidad del parámetro) -> factor que multiplica el valor del archivo
CONVERSIONES = {
    ("%", "kg/kg"): 0.01, ("%", "—"): 0.01, ("kg/h", "t/h"): 0.001, ("t/d", "t/h"): 1 / 24,
    ("kj/kg", "mj/kg"): 0.001, ("kwh/kg", "mj/kg"): 3.6, ("kg", "t"): 0.001, ("j/kg·k", "kj/kg·k"): 0.001,
}
SINONIMOS = {"ºc": "°c", "c": "°c", "grados c": "°c", "-": "—", "": "—", "adim": "—", "adimensional": "—", "tph": "t/h",
             "kj/kgk": "kj/kg·k", "kj/kg k": "kj/kg·k", "kj/(kg·k)": "kj/kg·k", "kj/kg.k": "kj/kg·k", "dias": "d", "días": "d", "kg/m3": "kg/m³"}


def norm_unidad(u: str | None) -> str:
    u = (u or "").strip().lower().replace("º", "°")
    return SINONIMOS.get(u, u)


def numero_cl(texto) -> float:
    """Lee una cifra en formato chileno (1.234,5 o 12.500) o con punto decimal (1234.5, 0.85). Un solo punto seguido de
    exactamente tres dígitos, con parte entera distinta de cero, se lee como separador de miles."""
    if isinstance(texto, (int, float)) and not isinstance(texto, bool):
        return float(texto)
    t = str(texto).strip().replace(" ", "").replace(" ", "")
    if not t:
        raise ValueError("valor vacío")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or (t.count(".") == 1 and re.fullmatch(r"[-+]?[1-9]\d{0,2}\.\d{3}", t)):
        t = t.replace(".", "")          # formato chileno: 12.500 es doce mil quinientos (0.125 y 1.5 siguen siendo decimales)
    try:
        v = float(t)
    except ValueError:
        raise ValueError(f"el valor «{texto}» no es un número") from None
    if not math.isfinite(v):
        raise ValueError("valor no finito")
    return v


def texto_cl(v) -> str:
    """Cifra en formato chileno para la plantilla (sin separador de miles, para que la planilla lo lea como número)."""
    if v is None:
        return ""
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    return f"{float(v):.6g}".replace(".", ",")


def fecha_cl(texto) -> date:
    t = str(texto or "").strip()
    for f in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            pass
    raise ValueError(f"fecha «{t}» no válida (use dd-mm-aaaa)")


def es_numerico(p) -> bool:
    return (isinstance(p.valor, (int, float)) and not isinstance(p.valor, bool)) or (p.valor is None and p.clave in OPCIONALES)


def ajustados_por_especificacion(pl) -> set:
    return {(e.equipo_var, e.param) for e in pl.especs}


# ------------------------------------------------------------------------------------------------ plantilla
def plantilla_csv(pl) -> str:
    """Plantilla con una fila por parámetro numérico de cada equipo. La columna valor va vacía: se llena solo lo medido;
    las filas sin valor se ignoran. La columna referencia (nombre, valor actual y categoría) es solo para orientarse."""
    buf = io.StringIO(); w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(COLUMNAS)
    fijos = ajustados_por_especificacion(pl)
    for e in pl.equipos.values():
        for p in e.params.values():
            if not es_numerico(p) or (e.id, p.clave) in fijos:
                continue
            ref = f"{e.nombre}: {p.nombre}; valor actual {texto_cl(p.valor) or 'sin valor'} ({p.categoria})"
            if p.minimo is not None or p.maximo is not None:
                ref += f"; rango {texto_cl(p.minimo) or '−∞'} a {texto_cl(p.maximo) or '∞'}"
            w.writerow([e.id, p.clave, "", p.unidad or "—", "", "", ref])
    return "﻿" + buf.getvalue()          # con BOM, para que Excel en Windows lea bien los acentos


def leer_csv(texto: str | bytes) -> list[dict]:
    """Filas del CSV como diccionarios (n = número de fila del archivo). Acepta punto y coma o coma como separador."""
    if isinstance(texto, bytes):
        try:
            texto = texto.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = texto.decode("latin-1")
    texto = texto.lstrip("﻿")
    primera = texto.splitlines()[0] if texto.strip() else ""
    sep = ";" if primera.count(";") >= primera.count(",") else ","
    rd = csv.DictReader(io.StringIO(texto), delimiter=sep)
    if rd.fieldnames is None:
        return []
    rd.fieldnames = [(c or "").strip().lower() for c in rd.fieldnames]
    faltan = [c for c in OBLIGATORIAS if c not in rd.fieldnames]
    if faltan:
        raise ValueError("Al archivo le faltan las columnas: " + ", ".join(faltan))
    return [dict({k: (v or "").strip() for k, v in f.items() if k}, n=i) for i, f in enumerate(rd, start=2)]


# ------------------------------------------------------------------------------------------------ aplicar
def _validar(pl, f: dict, hoy: date, fijos: set):
    """Devuelve (equipo, parámetro, valor convertido, fecha, nota) o lanza ValueError con el motivo del rechazo."""
    eq = pl.equipos.get(f.get("equipo", ""))
    if eq is None:
        raise ValueError("el equipo no existe en la planta")
    p = eq.params.get(f.get("parametro", ""))
    if p is None:
        raise ValueError("el equipo no tiene ese parámetro")
    if not es_numerico(p):
        raise ValueError("solo se aceptan parámetros numéricos")
    if (eq.id, p.clave) in fijos:
        raise ValueError("lo ajusta una especificación de diseño; cambie la especificación en vez del parámetro")
    v = numero_cl(f["valor"])
    ua, up = norm_unidad(f.get("unidad")), norm_unidad(p.unidad)
    nota = ""
    if ua != up:
        k = CONVERSIONES.get((ua, up))
        if k is None:
            raise ValueError(f"unidad «{f.get('unidad')}» distinta de la del parámetro ({p.unidad or '—'}) y sin conversión conocida")
        v = v * k; nota = f"convertido de {f.get('unidad')} a {p.unidad}"
    if p.minimo is not None and v < float(p.minimo) - 1e-12:
        raise ValueError(f"bajo el mínimo del parámetro ({texto_cl(p.minimo)} {p.unidad})")
    if p.maximo is not None and v > float(p.maximo) + 1e-12:
        raise ValueError(f"sobre el máximo del parámetro ({texto_cl(p.maximo)} {p.unidad})")
    if p.clave in OPCIONALES and v < 0:
        raise ValueError("no puede ser negativo")
    if isinstance(p.valor, int) and not isinstance(p.valor, bool):
        if abs(v - round(v)) > 1e-9:
            raise ValueError("debe ser un número entero")
        v = int(round(v))
    if not f.get("fuente"):
        raise ValueError("falta la fuente (placa, instrumento, informe o persona que midió)")
    fe = fecha_cl(f.get("fecha"))
    if fe > hoy:
        raise ValueError("la fecha es posterior a hoy")
    return eq, p, v, fe, nota


def aplicar_datos(pl, filas: list[dict], hoy: date | None = None, resolver: bool = True) -> dict:
    """Aplica las filas medidas a la planta. Devuelve el informe: cambios (antes y después), rechazos (con el motivo),
    filas sin valor ignoradas, si la planta quedó resuelta y el error si no resolvió (en ese caso se deshace todo)."""
    hoy = hoy or date.today(); fijos = ajustados_por_especificacion(pl)
    cambios, rechazos, vistos = [], [], {}; ignoradas = 0; respaldo = []
    for f in filas:
        if not str(f.get("valor", "")).strip():
            ignoradas += 1; continue
        clave = (f.get("equipo", ""), f.get("parametro", ""))
        base = dict(fila=f.get("n"), equipo=clave[0], parametro=clave[1], valor=f.get("valor"), unidad=f.get("unidad"))
        if clave in vistos:
            rechazos.append(dict(base, motivo=f"repetido: ya se aplicó la fila {vistos[clave]}")); continue
        try:
            eq, p, v, fe, nota = _validar(pl, f, hoy, fijos)
        except (ValueError, TypeError) as e:
            rechazos.append(dict(base, motivo=str(e))); continue
        vistos[clave] = f.get("n")
        respaldo.append((p, p.valor, p.categoria, p.fuente, p.justificacion))
        fecha = fe.strftime("%d-%m-%Y")
        cambios.append(dict(fila=f.get("n"), equipo=eq.id, nombre_equipo=eq.nombre, parametro=p.clave, nombre=p.nombre, unidad=p.unidad,
                            antes=p.valor, categoria_antes=p.categoria, fuente_antes=p.fuente, despues=v,
                            fuente=f["fuente"], fecha=fecha, nota=nota))
        anterior = f"{texto_cl(p.valor) or 'sin valor'} {p.unidad}".strip()
        eq.set(p.clave, v, categoria=CATEGORIA_MEDIDO, fuente=f"{f['fuente']}, {fecha}",
               justificacion=f"Medido: reemplaza el valor {anterior} ({p.categoria}{', ' + p.fuente if p.fuente else ''})")
    out = dict(cambios=cambios, rechazos=rechazos, ignoradas=ignoradas, resuelta=pl.resuelta, error=None)
    if cambios and resolver:
        try:
            pl.resolver(); out["resuelta"] = True
        except Exception as e:          # la planta no resuelve con los datos nuevos: se deshace todo
            for p, v, c, fu, j in respaldo:
                p.valor, p.categoria, p.fuente, p.justificacion = v, c, fu, j
            try:
                pl.resolver()
            except Exception:
                pl.resuelta = False
            out.update(cambios=[], error=f"La planta no resuelve con los datos medidos ({e}); no se aplicó ningún cambio",
                       resuelta=pl.resuelta, deshechos=cambios)
            return out
    if out["cambios"]:
        reg = {(d["equipo"], d["parametro"]): d for d in pl.globales.get(CLAVE_GLOBAL, [])}
        for c in out["cambios"]:
            reg[(c["equipo"], c["parametro"])] = dict(equipo=c["equipo"], parametro=c["parametro"], valor=c["despues"],
                                                     fuente=c["fuente"], fecha=c["fecha"],
                                                     justificacion=pl.equipos[c["equipo"]].params[c["parametro"]].justificacion)
        pl.globales[CLAVE_GLOBAL] = list(reg.values())
    return out


def aplicar_csv(pl, texto, hoy: date | None = None, resolver: bool = True) -> dict:
    return aplicar_datos(pl, leer_csv(texto), hoy=hoy, resolver=resolver)


def restaurar_medidos(pl) -> int:
    """Vuelve a marcar como «Medido» los parámetros guardados en pl.globales (al cargar una versión guardada), solo si el
    valor sigue siendo el medido. Devuelve cuántos marcó."""
    n = 0
    for d in pl.globales.get(CLAVE_GLOBAL, []) or []:
        eq = pl.equipos.get(d.get("equipo")); p = eq.params.get(d.get("parametro")) if eq else None
        if p is None or p.categoria == CATEGORIA_MEDIDO:
            continue
        try:
            igual = p.valor is not None and math.isclose(float(p.valor), float(d["valor"]), rel_tol=1e-9, abs_tol=1e-12)
        except (TypeError, ValueError):
            igual = False
        if igual:
            p.categoria = CATEGORIA_MEDIDO; p.fuente = f"{d['fuente']}, {d['fecha']}"; p.justificacion = d.get("justificacion", "")
            n += 1
    return n


def medidos(pl) -> list[dict]:
    """Parámetros marcados como medidos en la planta."""
    return [dict(equipo=e.id, nombre_equipo=e.nombre, parametro=p.clave, nombre=p.nombre, valor=p.valor, unidad=p.unidad, fuente=p.fuente)
            for e in pl.equipos.values() for p in e.params.values() if p.categoria == CATEGORIA_MEDIDO]
