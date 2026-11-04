"""Escenario: planta de chip (astilla) de madera a partir de rollizos verdes de pino radiata (rubro chip).

Línea: recepción de rollizos, astilladora de disco, criba de sobretamaño y finos, secador de banda a baja temperatura y
acopio con la ISO 17225-4. Un generador de calor que quema corteza y rechazo calienta el aire del secador."""
from __future__ import annotations
from ..motor.planta import Instrumento
from ..catalogos import biomasa as B
from .biomasa_comun import nueva_planta, fijar_produccion
from . import capacidades as _cap

NOMBRE = "Planta de chip de madera (escenario base)"
BASE = dict(produccion=10.0, M0=0.53, Mseco=0.25, Tae=90.0, Tas=45.0, dias=300, hpd=16, rechazo=0.05, Tfin=30.0, dT=5.0)
PARAMS = [
    ("produccion", "Chip seco producido (t/h)", 1.0, 60.0, 0.5, "%.1f"),
    ("M0", "Humedad de los rollizos verdes (base húmeda)", 0.20, 0.65, 0.01, "%.2f"),
    ("Mseco", "Humedad del chip seco (base húmeda)", 0.10, 0.45, 0.01, "%.2f"),
    ("Tae", "Temperatura del aire de secado (°C)", 50.0, 150.0, 5.0, "%.0f"),
    ("Tas", "Temperatura del escape del secador (°C)", 30.0, 80.0, 1.0, "%.0f"),
    ("dias", "Días de operación al año", 100, 366, 1, "%d"),
    ("hpd", "Horas de operación por día", 8, 24, 1, "%d"),
    ("rechazo", "Rechazo de la criba (fracción)", 0.0, 0.20, 0.01, "%.2f"),
    ("dT", "Aproximación mínima de temperatura (°C)", 2.0, 15.0, 0.5, "%.1f"),
    ("Tfin", "Temperatura final de los residuales (°C)", 20.0, 40.0, 1.0, "%.1f"),
]


def crear(capacidades=True, **kw):
    p = dict(BASE); p.update(kw)
    pl = nueva_planta(NOMBRE, "chip", p); E = pl.agregar
    # humedad de rollizos de pino radiata recién cortados: 53,2 % en verano y 57,7 % en invierno (Visser et al., 2014)
    E(B.AlimentacionBiomasa("B1", "Recepción de rollizos", 40, 120, materia="Rollizos verdes de pino radiata", humedad=p["M0"],
                            dias=p["dias"], horas_dia=p["hpd"]))
    E(B.Astilladora("Z1", "Astilladora de disco", 200, 120))
    # finos de astilladoras de fuste: nunca sobre 10 % (Kuptz y Hartmann, 2022, p. 116); la clase P31s admite hasta 10 % de finos
    E(B.CribaBiomasa("F1", "Criba de astillas", 360, 120, rechazo=p["rechazo"]))
    E(B.SecadorBanda("T1", "Secador de banda", 520, 120, humedad_salida=p["Mseco"], T_aire_entrada=p["Tae"], T_aire_salida=p["Tas"],
                     T_condensacion=p["Tfin"]))
    E(B.DespachoBiomasa("A1", "Acopio de chip (ISO 17225-4)", 680, 120, norma="ISO 17225-4 (astilla, clase M25)", humedad_max=0.25, PCI_min=0.0,
                        base_humedad="bh"))      # clases M10, M25 y M35 (Natural Resources Canada, s. f., Tabla 1)
    pl.equipos["A1"].set("humedad_max", 0.25, fuente="Alakangas et al. (2015): ISO 17225-4, astilla de madera, clase M25 (humedad hasta 25 % en base húmeda)")   # PAT 131
    pl.equipos["A1"].set("norma", "ISO 17225-4 (astilla, clase M25)", fuente="Alakangas et al. (2015): ISO 17225-4")
    E(B.GeneradorCalorBiomasa("D1", "Generador de calor a corteza", 520, 290))
    C = pl.conectar
    C("B1", "producto", "Z1", "entrada", nombre="1"); C("Z1", "producto", "F1", "entrada", nombre="2")
    C("F1", "producto", "T1", "entrada", nombre="3"); C("T1", "producto", "A1", "entrada", nombre="4")
    C("D1", "calor", "T1", "calor", nombre="Q1")
    fijar_produccion(pl, "B1", "A1", p["produccion"], "Chip seco producido")
    pl.instrumentos += [
        Instrumento("TIC", "101", "T1", "plc", "Temperatura del aire de secado a la entrada", "T_aire_entrada", "TV-101"),
        Instrumento("MIC", "102", "T1", "plc", "Humedad del chip a la salida del secador", "humedad_salida", "Velocidad de la banda"),
        Instrumento("WI", "201", "B1", "plc", "Peso de los rollizos recibidos", None, None),
    ]
    pl._p = p
    pl.resolver()
    if capacidades:                       # capacidad nominal de partida (PAT 132), como el simulador del profesor
        _cap.aplicar(pl)
    return pl
