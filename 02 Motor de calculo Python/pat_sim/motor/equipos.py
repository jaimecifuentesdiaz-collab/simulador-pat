"""Clase base de los equipos: puertos, parámetros con fuente, símbolo ISO 10628 y balance."""
from __future__ import annotations
from dataclasses import dataclass, field
from .corrientes import Corriente, Residual

CATEGORIAS_PARAM = ("Agrozzi", "Fabricante", "Literatura", "Tabla", "Oficial", "Derivado", "Supuesto", "Usuario")


@dataclass
class Parametro:
    clave: str
    nombre: str
    valor: float | bool | int | str
    unidad: str = ""
    categoria: str = "Supuesto"
    fuente: str = ""
    justificacion: str = ""
    minimo: float | None = None
    maximo: float | None = None

    def a_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Puerto:
    nombre: str
    tipo: str          # tipo de corriente (ver corrientes.TIPOS)
    descripcion: str = ""


@dataclass
class Sumidero:
    """Corriente fría que puede recibir calor recuperado."""
    nombre: str
    equipo: str
    T_in: float
    T_out: float
    CP: float  # kW/K

    @property
    def Q(self) -> float:
        return self.CP * (self.T_out - self.T_in)


@dataclass
class Resultado:
    salidas: dict[str, Corriente] = field(default_factory=dict)
    servicios: dict[str, float] = field(default_factory=dict)   # vapor_kW, vapor_kgh, electricidad_kW
    residuales: list[Residual] = field(default_factory=list)
    sumideros: list[Sumidero] = field(default_factory=list)
    energia_in: list[tuple[str, float]] = field(default_factory=list)   # (concepto, kW)
    energia_out: list[tuple[str, float]] = field(default_factory=list)
    detalle: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    def cierre_energia(self) -> float:
        return sum(v for _, v in self.energia_in) - sum(v for _, v in self.energia_out)


class Equipo:
    """Clase base. Cada tipo de equipo define su símbolo, sus puertos, sus parámetros y su balance."""
    tipo = "equipo"
    nombre_tipo = "Equipo"
    rubro = "general"
    # ISO 10628 (UNE-EN ISO 10628:2001): categoría de la Tabla C.1, letra código del Anexo D y símbolo SVG
    iso_categoria = 20
    iso_letra = "A"
    simbolo = "equipo_general"
    entradas: list[Puerto] = []
    salidas: list[Puerto] = []
    params_base: list[Parametro] = []
    descripcion = ""

    def __init__(self, id: str, nombre: str | None = None, x: float = 0, y: float = 0, **valores):
        self.id = id
        self.nombre = nombre or self.nombre_tipo
        self.x, self.y = x, y
        self.params: dict[str, Parametro] = {p.clave: Parametro(**p.a_dict()) for p in self.params_base}
        if "capacidad" in self.params:          # teoría de restricciones, como en el simulador del profesor (PAT 128)
            for p in params_restricciones():
                self.params.setdefault(p.clave, p)
        for k, v in valores.items():
            self.set(k, v)
        self.resultado: Resultado | None = None

    # --- parámetros
    def set(self, clave, valor, **meta):
        if clave not in self.params:
            raise KeyError(f"{self.id}: parámetro desconocido {clave}")
        p = self.params[clave]
        p.valor = valor
        for k, v in meta.items():
            setattr(p, k, v)

    def v(self, clave):
        return self.params[clave].valor

    @property
    def etiqueta(self) -> str:
        """Etiqueta ISO 10628 (letra código + número), por ejemplo W4."""
        return self.id

    # --- balance (lo implementa cada tipo)
    def calcular(self, ent: dict[str, Corriente]) -> Resultado:
        raise NotImplementedError

    # --- capacidad (teoría de restricciones)
    def capacidad_efectiva(self) -> float | None:
        """Capacidad nominal × estado del equipo (t/h), como la capacidad efectiva del simulador del profesor."""
        if "capacidad" not in self.params or not self.params["capacidad"].valor:
            return None
        estado = self.params["estado"].valor if "estado" in self.params and self.params["estado"].valor is not None else 1.0
        return float(self.params["capacidad"].valor) * max(0.15, min(1.0, float(estado)))

    def utilizacion(self) -> float | None:
        cap = self.capacidad_efectiva()
        if cap is None or self.resultado is None:
            return None
        carga = self.resultado.detalle.get("carga_t_h")
        if carga is None:
            return None
        return carga / cap

    def a_dict(self) -> dict:
        return dict(id=self.id, tipo=self.tipo, nombre=self.nombre, x=self.x, y=self.y,
                    params={k: p.valor for k, p in self.params.items()})


def P(clave, nombre, valor, unidad="", categoria="Supuesto", fuente="", justificacion="", minimo=None, maximo=None):
    return Parametro(clave, nombre, valor, unidad, categoria, fuente, justificacion, minimo, maximo)


# Parámetros opcionales de capacidad (vacíos = no se usan), como en las propiedades del simulador del profesor
OPCIONALES = ("capacidad", "costo", "consumo_especifico")


def params_restricciones() -> list[Parametro]:
    return [P("estado", "Estado del equipo (disponibilidad)", 1.0, "—", "Supuesto",
              "1 = equipo en buen estado; como el estado (0 a 1) del simulador del profesor",
              "Capacidad efectiva = capacidad nominal × estado", 0.15, 1.0),
            P("costo", "Costo del equipo (inversión)", None, "$", "Usuario", "",
              "Lo declara el usuario; se suma en la inversión declarada del diseño"),
            P("consumo_especifico", "Consumo eléctrico específico adicional", None, "kWh/t", "Usuario", "",
              "Se suma a la electricidad del equipo: consumo × carga de entrada", 0, 500)]


def capacidad_param(valor=None, fuente="", categoria="Usuario"):
    return P("capacidad", "Capacidad nominal (carga de entrada)", valor, "t/h", categoria, fuente,
             "Solo para el indicador de utilización; no limita el balance")
