"""Plantillas mínimas por rubro y biblioteca de proyectos de ejemplo (PAT 133, mejora 14).

Una plantilla es la línea típica de proceso del rubro, ya conectada y resuelta, pero sin capacidades nominales, sin
instrumentación y sin la fuente de calor (caldera o generador): el estudiante declara las capacidades, agrega el servicio
térmico y busca la recuperación de calor. La biblioteca reúne los escenarios base con su nombre y descripción, más dos
variantes de diseño que ya existen como argumentos de los escenarios (sin cifras nuevas)."""
from __future__ import annotations
from dataclasses import dataclass, field
from . import agrozzi, pellet, chip, lena

MODULOS = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}
SERVICIO_CALOR = ("caldera", "generador")          # prefijos de tipo de los equipos de servicio térmico


@dataclass(frozen=True)
class Plantilla:
    clave: str
    rubro: str
    nombre: str
    descripcion: str
    pendientes: tuple = ()
    argumentos: dict = field(default_factory=dict)
    es_ejemplo: bool = False


PENDIENTES = ("Declarar la capacidad nominal de cada equipo (pestaña Diseño, Propiedades)",
              "Agregar la fuente de calor (caldera a gas o generador a biomasa) y conectarla a los consumidores de calor",
              "Revisar los balances de materia y energía",
              "Buscar la recuperación de calor (cascada y *pinch*) y evaluarla en Economía")

PLANTILLAS = {p.clave: p for p in [
    Plantilla("plantilla_tomate", "tomate", "Plantilla de pasta de tomate",
              "Recepción, lavado, trituradora, hot break, refinadora, dos evaporadores MVR, evaporador de múltiple efecto, "
              "esterilizador, enfriamiento flash y llenadora aséptica. Sin calderas, sin capacidades y sin lazos de control.", PENDIENTES),
    Plantilla("plantilla_pellet", "pellet", "Plantilla de pellet de madera",
              "Recepción de aserrín, secador rotatorio, molino, pelletizadora, enfriador, criba y ensacado. Sin generador de calor, "
              "sin capacidades y sin lazos de control.", PENDIENTES),
    Plantilla("plantilla_chip", "chip", "Plantilla de chip de madera",
              "Recepción de rollizos, astilladora, criba, secador de banda y acopio. Sin generador de calor, sin capacidades y sin "
              "lazos de control.", PENDIENTES),
    Plantilla("plantilla_lena", "lena", "Plantilla de leña seca",
              "Recepción de trozas, procesadora, secador de leña y acopio. Sin generador de calor, sin capacidades y sin lazos de control.",
              PENDIENTES),
]}

EJEMPLOS = {p.clave: p for p in [
    Plantilla("ejemplo_agrozzi", "tomate", "Planta basada en Agrozzi",
              "Línea de pasta de tomate del Capítulo 1 (Empresas Carozzi S.A., Teno) con los parámetros de Modelo_PAT_Agrozzi_v2.xlsx.",
              es_ejemplo=True),
    Plantilla("ejemplo_agrozzi_sin_tvr", "tomate", "Planta basada en Agrozzi sin termocompresor",
              "La misma línea con el evaporador Venus sin termocompresor (TVR): sirve para comparar el vapor vivo y la cascada.",
              argumentos=dict(tvr=False), es_ejemplo=True),
    Plantilla("ejemplo_pellet", "pellet", pellet.NOMBRE, (pellet.__doc__ or "").strip().split("\n")[0], es_ejemplo=True),
    Plantilla("ejemplo_chip", "chip", chip.NOMBRE, (chip.__doc__ or "").strip().split("\n")[0], es_ejemplo=True),
    # 57,7 % de humedad de los rollizos en invierno (Visser et al., 2014), la misma fuente que cita escenarios/chip.py
    Plantilla("ejemplo_chip_invierno", "chip", "Planta de chip de madera con rollizos de invierno",
              "El escenario base con la humedad de los rollizos de pino radiata en invierno, 57,7 % en base húmeda (Visser et al., 2014).",
              argumentos=dict(M0=0.577), es_ejemplo=True),
    Plantilla("ejemplo_lena", "lena", lena.NOMBRE, (lena.__doc__ or "").strip().split("\n")[0], es_ejemplo=True),
]}


def listar(rubro: str | None = None, ejemplos: bool | None = None) -> list[Plantilla]:
    """Plantillas y ejemplos, filtrados por rubro y por tipo (ejemplos=True solo la biblioteca, False solo las plantillas)."""
    todas = list(PLANTILLAS.values()) + list(EJEMPLOS.values())
    return [p for p in todas if (rubro is None or p.rubro == rubro) and (ejemplos is None or p.es_ejemplo == ejemplos)]


def obtener(clave: str) -> Plantilla:
    p = PLANTILLAS.get(clave) or EJEMPLOS.get(clave)
    if p is None:
        raise KeyError(f"No existe la plantilla o el ejemplo «{clave}»")
    return p


def _vaciar(pl):
    """Deja la línea de proceso: quita la fuente de calor, la instrumentación y las capacidades, y vuelve a resolver."""
    for k in [k for k, e in pl.equipos.items() if e.tipo.startswith(SERVICIO_CALOR)]:
        pl.quitar(k)
    pl.instrumentos = []
    for e in pl.equipos.values():
        if "capacidad" in e.params:
            e.params["capacidad"].valor = None
    pl.resolver()
    return pl


def cargar(clave: str):
    """Planta lista para la sesión: la plantilla vacía o el proyecto de ejemplo, siempre resuelta."""
    p = obtener(clave); mod = MODULOS[p.rubro]
    if p.es_ejemplo:
        pl = mod.crear(**p.argumentos)
        if p.argumentos:
            pl.nombre = p.nombre
        return pl
    pl = _vaciar(mod.crear(capacidades=False, **p.argumentos))
    pl.nombre = p.nombre
    return pl
