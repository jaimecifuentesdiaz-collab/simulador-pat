"""Modo curso (PAT 133, mejora 16): identificador del estudiante, variante reproducible del caso y registro de entregas.

Como el simulador del profesor (Scorm_pellet_profesor.html), cada estudiante recibe una variante propia del caso a partir
de su identificador, pero aquí la variante cambia también los datos de la planta y no solo los números aleatorios de la
operación. La derivación usa SHA-256 (hashlib), que da el mismo resultado en cualquier computador y en cualquier corrida;
no se usa hash() de Python porque cambia en cada ejecución. Cada parámetro varía dentro de un rango declarado en RANGOS,
con su fuente o como Supuesto. La clave del profesor se guarda solo como SHA-256 con sal aleatoria."""
from __future__ import annotations
import csv
import hashlib
import hmac
import io
import os
import unicodedata
from dataclasses import dataclass
from . import operacion as OP


@dataclass(frozen=True)
class Rango:
    clave: str
    etiqueta: str
    minimo: float
    maximo: float
    paso: float
    destino: str        # "planta" (argumento de crear) o "economia" (factor sobre el precio de la sesión)
    fuente: str


_SUP = "Supuesto didáctico (PAT 133): variación de ±10 % en torno al escenario base para que cada estudiante tenga cifras propias sin salir del rango de operación del escenario"
_GAS = ("Supuesto didáctico (PAT 133): ±15 % sobre el Henry Hub de la sesión, del orden de la variación mensual del indicador; "
        "el valor base se mantiene con su fuente (CNE, 2026c, p. 12)")
_BIO = "INFOR (Pardo, 2025), Boletín de precios forestales N.° 193, pp. 12-13: astilla con corteza entre 6.000 y 7.500 $/m³ estéreo (factor sobre 6.750)"
RANGOS = {
    "tomate": [
        Rango("season", "Tomate procesado por temporada (t)", 405000.0, 495000.0, 1000.0, "planta", _SUP),
        Rango("days", "Días de operación de la temporada", 68, 84, 1, "planta", _SUP),
        Rango("Thb", "Temperatura de salida del hot break (°C)", 85.0, 95.0, 0.5, "planta",
              "Supuesto didáctico (PAT 133): el escenario base usa 90 °C; se varía ±5 °C sin superar el máximo de 96 °C de la pestaña Escenario"),
        Rango("Tin", "Temperatura del tomate que llega (°C)", 20.0, 30.0, 0.5, "planta", "Supuesto didáctico (PAT 133): ±5 °C en torno a 25 °C, según la hora de cosecha"),
        Rango("f_precio_gas", "Factor sobre el precio del gas natural", 0.85, 1.15, 0.01, "economia", _GAS),
    ],
    "pellet": [
        Rango("produccion", "Pellet producido (t/h)", 4.5, 5.5, 0.1, "planta", _SUP),
        Rango("M0", "Humedad del aserrín verde (base húmeda)", 0.50, 0.60, 0.005, "planta", _SUP),
        Rango("dias", "Días de operación al año", 300, 350, 1, "planta", _SUP),
        Rango("f_precio_biomasa", "Factor sobre el precio de la biomasa", 0.89, 1.11, 0.01, "economia", _BIO),
    ],
    "chip": [
        Rango("produccion", "Chip seco producido (t/h)", 9.0, 11.0, 0.1, "planta", _SUP),
        Rango("M0", "Humedad de los rollizos verdes (base húmeda)", 0.532, 0.577, 0.001, "planta",
              "Visser et al. (2014): rollizos de pino radiata recién cortados, 53,2 % en verano y 57,7 % en invierno (la fuente de escenarios/chip.py)"),
        Rango("dias", "Días de operación al año", 280, 320, 1, "planta", _SUP),
        Rango("f_precio_biomasa", "Factor sobre el precio de la biomasa", 0.89, 1.11, 0.01, "economia", _BIO),
    ],
    "lena": [
        Rango("produccion", "Leña seca producida (t/h)", 1.8, 2.2, 0.1, "planta", _SUP),
        Rango("M0", "Humedad de la leña verde (base húmeda)", 0.50, 0.56, 0.005, "planta", _SUP),
        Rango("dias", "Días de operación al año", 280, 320, 1, "planta", _SUP),
        Rango("f_precio_biomasa", "Factor sobre el precio de la biomasa", 0.89, 1.11, 0.01, "economia", _BIO),
    ],
}


def normalizar(identificador: str) -> str:
    """Quita espacios, tildes y mayúsculas: «  Ana.Pérez » y «ana.perez» son el mismo estudiante."""
    t = unicodedata.normalize("NFKD", (identificador or "").strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c) and not c.isspace())


def fraccion(identificador: str, clave: str, curso: str = "") -> float:
    """Número uniforme y estable en [0, 1) para el identificador y el parámetro (SHA-256, 52 bits)."""
    texto = f"pat133|{normalizar(curso)}|{normalizar(identificador)}|{clave}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(texto).digest()[:7], "big") / float(1 << 56)


def _redondear(v: float, r: Rango):
    n = round((v - r.minimo) / r.paso)
    x = min(r.maximo, r.minimo + n * r.paso)
    return int(round(x)) if isinstance(r.minimo, int) and isinstance(r.paso, int) else round(x, 6)


def variante(identificador: str, rubro: str = "tomate", curso: str = "") -> dict:
    """Variante del caso para el estudiante: argumentos de la planta, factores de precio y semilla de la operación."""
    ident = normalizar(identificador)
    if not ident:
        raise ValueError("Ingrese el identificador del estudiante")
    if rubro not in RANGOS:
        raise ValueError(f"El modo curso no tiene variantes para el rubro «{rubro}»")
    planta, economia = {}, {}
    for r in RANGOS[rubro]:
        v = _redondear(r.minimo + fraccion(ident, r.clave, curso) * (r.maximo - r.minimo), r)
        (planta if r.destino == "planta" else economia)[r.clave] = v
    return dict(identificador=ident, rubro=rubro, curso=curso, planta=planta, economia=economia,
                semilla=OP.semilla_texto(ident))


def crear_planta(var: dict):
    """Planta resuelta de la variante, con el escenario del rubro y sus capacidades de partida."""
    from ..escenarios import agrozzi, pellet, chip, lena
    mod = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}[var["rubro"]]
    pl = mod.crear(**var["planta"])
    pl.nombre = f"{pl.nombre} · variante {var['identificador']}"
    return pl


def aplicar_economia(var: dict, economia: dict, precio_gas_base: float, precio_biomasa_base: float) -> dict:
    """Ajusta los precios de la sesión con los factores de la variante (los demás datos de Economía no cambian)."""
    e = var.get("economia", {})
    if "f_precio_gas" in e:
        economia["precio_gas"] = round(precio_gas_base * e["f_precio_gas"], 4)
    if "f_precio_biomasa" in e:
        economia["precio_biomasa"] = round(precio_biomasa_base * e["f_precio_biomasa"], 2)
    return economia


def operacion_de(var: dict):
    """Operación por turnos con la semilla del identificador, la misma que fija el nombre en la pestaña Evaluación."""
    return OP.Operacion(rubro=var["rubro"], semilla=var["semilla"], estudiante=var["identificador"])


# ----------------------------------------------------------------------------------------------- clave del profesor
def hash_clave(clave: str, sal: str | None = None) -> str:
    """«sha256$sal$hash»: SHA-256 de la sal más la clave. La clave nunca se guarda en claro."""
    if not clave:
        raise ValueError("La clave del profesor no puede quedar vacía")
    sal = sal or os.urandom(16).hex()
    return f"sha256${sal}${hashlib.sha256((sal + clave).encode('utf-8')).hexdigest()}"


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        tipo, sal, _h = (guardado or "").split("$")
    except ValueError:
        return False
    return tipo == "sha256" and hmac.compare_digest(hash_clave(clave or " ", sal), guardado)


# ----------------------------------------------------------------------------------------------- curso en la base
def configurar(bd, nombre: str, rubro: str = "tomate", clave: str | None = None) -> dict:
    """Crea el curso si no existe; la clave se fija la primera vez (o se cambia si se entrega otra)."""
    c = bd.obtener_o_crear_curso(nombre, rubro)
    if c["rubro"] != rubro:
        bd.actualizar_curso(c["id"], rubro=rubro)
    if clave:
        bd.actualizar_curso(c["id"], clave_hash=hash_clave(clave))
    return bd.obtener_curso(c["id"])


def ingresar(bd, curso: dict, identificador: str, nombre: str = "") -> dict:
    """El estudiante ingresa: queda inscrito y recibe su variante."""
    var = variante(identificador, curso["rubro"], curso["nombre"])
    var["estudiante_id"] = bd.registrar_estudiante(curso["id"], var["identificador"], nombre.strip())
    return var


def entregar(bd, curso: dict, identificador: str, op) -> int:
    """Registra el puntaje de la Evaluación finalizada (motor/operacion.finalizar) con su fecha."""
    if not getattr(op, "finalizada", False) or not op.puntaje:
        raise ValueError("Finalice la evaluación en la pestaña Evaluación antes de entregar.")
    eid = bd.registrar_estudiante(curso["id"], normalizar(identificador))
    detalle = dict(op.puntaje, turnos=len(op.turnos), laboratorio=len(op.lab))
    return bd.guardar_entrega(eid, int(op.puntaje["total"]), detalle, op.rubro, op.semilla)


def tabla_profesor(bd, curso: dict, clave: str) -> list[dict]:
    """Una fila por estudiante: entregas, último y mejor puntaje y fecha. Exige la clave del profesor."""
    if not verificar_clave(clave, curso.get("clave_hash", "")):
        raise PermissionError("Clave del profesor incorrecta")
    filas = {}
    for s in bd.listar_estudiantes(curso["id"]):
        filas[s["identificador"]] = dict(identificador=s["identificador"], nombre=s["nombre"], entregas=0, ultimo=None, mejor=None, fecha="")
    for e in bd.listar_entregas(curso["id"]):
        f = filas.setdefault(e["identificador"], dict(identificador=e["identificador"], nombre=e["nombre"], entregas=0, ultimo=None, mejor=None, fecha=""))
        f["entregas"] += 1; f["ultimo"] = e["puntaje"]; f["fecha"] = e["fecha"]
        f["mejor"] = e["puntaje"] if f["mejor"] is None else max(f["mejor"], e["puntaje"])
    return [filas[k] for k in sorted(filas)]


COLUMNAS_CSV = [("identificador", "Identificador"), ("nombre", "Nombre"), ("entregas", "Entregas"), ("ultimo", "Último puntaje"),
                ("mejor", "Mejor puntaje"), ("fecha", "Fecha de la última entrega")]


def exportar_csv(filas: list[dict]) -> str:
    """CSV separado por punto y coma (Excel en español de Chile), con BOM para que abra con tildes."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow([t for _k, t in COLUMNAS_CSV])
    for f in filas:
        w.writerow(["" if f.get(k) is None else f.get(k) for k, _t in COLUMNAS_CSV])
    return "﻿" + buf.getvalue()
