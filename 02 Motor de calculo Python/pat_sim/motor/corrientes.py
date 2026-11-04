"""Corrientes de materia y de energía."""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from .propiedades import CPW, sat

TIPOS = {
    # tipo: (descripción, color del diagrama, grosor relativo)
    "producto": ("Producto o materia prima", "#1b7a5a", 4),
    "subproducto": ("Subproducto o descarte", "#7a5a1b", 2),
    "vapor": ("Vapor de agua", "#c0392b", 2),
    "condensado": ("Condensado", "#2e6db4", 2),
    "agua": ("Agua", "#2e86c1", 2),
    "gas": ("Combustible gaseoso", "#8e44ad", 2),
    "aire": ("Aire", "#5dade2", 2),
    "humos": ("Gases de combustión", "#7f8c8d", 2),
    "electricidad": ("Energía eléctrica", "#d4ac0d", 1),
    "calor": ("Calor", "#e67e22", 1),
    "biomasa": ("Biomasa", "#6e8b3d", 4),
}


@dataclass
class Corriente:
    """Corriente de materia.

    m: caudal total (kg/h); s: sólidos (kg/h; en el tomate, sólidos solubles); T: temperatura (°C);
    fase: 'liquido', 'vapor' o 'solido'; cp: calor específico fijo (kJ/kg·K) si la corriente no se
    modela por sólidos; cps: calor específico de los sólidos (kJ/kg·K) para el modelo cp = cpw − (cpw − cps)·x.
    humedad: fracción de agua en base húmeda (biomasa).
    """
    nombre: str = ""
    tipo: str = "producto"
    m: float = 0.0
    s: float = 0.0
    T: float = 25.0
    fase: str = "liquido"
    cp: float | None = None
    cps: float = 1.5
    humedad: float | None = None
    extra: dict = field(default_factory=dict)

    @property
    def x(self) -> float:
        """Fracción de sólidos (para el tomate, °Brix/100)."""
        return self.s / self.m if self.m else 0.0

    @property
    def brix(self) -> float:
        return 100 * self.x

    @property
    def cp_mezcla(self) -> float:
        if self.cp is not None:
            return self.cp
        return CPW - (CPW - self.cps) * self.x

    def H(self) -> float:
        """Entalpía en kW con referencia 0 °C (líquido) y vapor con IAPWS-IF97."""
        if self.fase == "vapor":
            return self.m * sat(self.T)[1] / 3600
        if self.cp is not None:
            return self.m * self.cp * self.T / 3600
        return (CPW * self.m - (CPW - self.cps) * self.s) * self.T / 3600

    def CP(self) -> float:
        """Capacidad calorífica de flujo en kW/K."""
        return self.m * self.cp_mezcla / 3600

    def fraccion(self, f: float) -> "Corriente":
        return replace(self, m=self.m * f, s=self.s * f, extra=dict(self.extra))

    def a_dict(self) -> dict:
        return dict(nombre=self.nombre, tipo=self.tipo, m=self.m, s=self.s, T=self.T, fase=self.fase,
                    cp=self.cp, brix=self.brix, H_kW=self.H())


def mezclar(cs: list[Corriente], nombre: str = "") -> Corriente:
    """Mezcla adiabática de corrientes líquidas del mismo tipo (temperatura por balance de entalpía)."""
    cs = [c for c in cs if c is not None and c.m > 0]
    if not cs:
        return Corriente(nombre=nombre, m=0.0)
    if len(cs) == 1:
        c = replace(cs[0], extra=dict(cs[0].extra))
        if nombre:
            c.nombre = nombre
        return c
    m = sum(c.m for c in cs); s = sum(c.s for c in cs)
    H = sum(c.H() for c in cs)
    base = cs[0]
    out = replace(base, nombre=nombre or base.nombre, m=m, s=s, extra={})
    CP = out.CP()
    out.T = H / CP if CP else base.T
    return out


@dataclass
class Residual:
    """Corriente de calor residual que puede recuperarse (entra al mapa de corrientes calientes).

    T_in: temperatura de cesión (°C). T_out: temperatura final (None = la temperatura final común
    del mapa, o calor latente si CP es None). CP: kW/K (None = cambio de fase a T_in). Q: kW disponibles.
    """
    nombre: str
    equipo: str
    T_in: float
    CP: float | None
    Q: float
    T_out: float | None = None
    descripcion: str = ""
    en_mapa: bool = True
