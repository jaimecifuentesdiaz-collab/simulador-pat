"""Variables de calidad del laboratorio virtual y del control estadístico (pestaña Calidad SPC), por rubro.

Equivale a la constante QC y a qualityMean del simulador del profesor (Scorm_pellet_profesor.html), adaptadas al PAT:
la media de cada variable sale de la planta resuelta (el °Brix de la pasta, la temperatura del esterilizador, la
humedad que deja el secador), así que las acciones correctivas son los mismos parámetros del diseño y cambian también
el vapor y la recuperación de calor. Cada límite lleva su fuente; lo que no tiene fuente es Supuesto con su justificación.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

FUENTE_CODEX = "Codex Alimentarius (1981), CODEX STAN 57-1981, concentrados de tomate elaborados, sec. 3.2.4"
FUENTE_CEE = "Reglamento (CEE) n.º 1764/86 de la Comisión (1986), requisitos mínimos del concentrado de tomate: pH no mayor que 4,5"
FUENTE_DIA = "DIA_Agrozzi_rev0.pdf, p. 48"
FUENTE_PROF = "Simulador del profesor (Scorm_pellet_profesor.html, constante QC)"


@dataclass
class Variable:
    id: str
    nombre: str
    unidad: str
    lo: float | None            # límite inferior de especificación (None: sin límite)
    hi: float | None            # límite superior de especificación
    sd: float                   # desviación estándar de la variabilidad común, con el equipo en buen estado
    media: float                # media del proceso con la planta actual
    fuente_espec: str
    fuente_media: str
    categoria: str = "Supuesto"
    equipo_control: str | None = None   # su estado (desgaste) aumenta la variabilidad
    decimales: int = 2

    def a_dict(self) -> dict:
        return asdict(self)

    def especificacion(self) -> str:
        f = lambda v: f"{v:,.{self.decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if self.lo is not None and self.hi is not None:
            return f"{f(self.lo)} a {f(self.hi)} {self.unidad}".strip()
        if self.hi is not None:
            return f"máximo {f(self.hi)} {self.unidad}".strip()
        if self.lo is not None:
            return f"mínimo {f(self.lo)} {self.unidad}".strip()
        return "sin especificación"


def _equipo(pl, *tipos):
    return next((e for e in pl.equipos.values() if any(e.tipo.startswith(t) for t in tipos)), None)


def _v(eq, clave, defecto):
    try:
        v = eq.params[clave].valor if eq is not None and clave in eq.params else None
        return float(v) if v is not None else defecto
    except (TypeError, ValueError):
        return defecto


def producto_final(pl):
    """Corriente de producto que sale de la planta (puerto de producto o biomasa sin conexión aguas abajo)."""
    for k, eq in pl.equipos.items():
        for p in eq.salidas:
            if p.tipo in ("producto", "biomasa") and not any(c.origen == k and c.puerto_origen == p.nombre for c in pl.conexiones):
                s = pl.salidas.get((k, p.nombre)) if getattr(pl, "salidas", None) else None
                if s is not None:
                    return eq, s
    return None, None


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def variables_tomate(pl) -> list[Variable]:
    _eq, s = producto_final(pl)
    brix = float(s.brix) if s is not None and getattr(s, "brix", None) else 30.0
    evap = next((e.equipo_var for e in pl.especs if e.param == "brix_salida"), None) or (_equipo(pl, "evaporador_multiefecto").id if _equipo(pl, "evaporador_multiefecto") else None)
    est = _equipo(pl, "esterilizador"); hb = _equipo(pl, "hot_break"); sel = _equipo(pl, "recepcion_seleccion")
    Tst = _v(est, "T_salida", 103.0); Thb = _v(hb, "T_salida", 90.0); desc = _v(sel, "descarte", 0.10)
    return [
        Variable("brix", "Sólidos solubles de la pasta", "°Brix", 29.0, 31.0, 0.25, brix,
                 "Supuesto: ±1 °Brix en torno a la pasta de 30 °Brix del Capítulo 1; la pasta hot break se vende por rangos de 2 °Brix (por ejemplo 28/30 y 30/32)",
                 "Balance de la planta: °Brix de la corriente al llenado aséptico (lazo DIC-302 del último evaporador)",
                 equipo_control=evap, decimales=2),
        Variable("t_est", "Temperatura de esterilización", "°C", 103.0, 110.0, 0.6, Tst,
                 f"Mínimo: la DIA exige esterilizar sobre 103 °C ({FUENTE_DIA}); máximo 110 °C: Supuesto, sobre esa temperatura se oscurece la pasta y se daña el sabor",
                 "Consigna del lazo TIC-401 del esterilizador (parámetro de la planta)",
                 categoria="Agrozzi", equipo_control=est.id if est else None, decimales=1),
        Variable("ph", "pH de la pasta", "", None, 4.5, 0.04, 4.30, FUENTE_CEE,
                 "Supuesto: pH típico de la pasta de tomate entre 4,2 y 4,4; el tratamiento sobre 103 °C sirve solo para un alimento ácido",
                 categoria="Oficial", decimales=2),
        Variable("bostwick", "Consistencia Bostwick (dilución a 12 °Brix)", "cm en 30 s", 3.0, 7.0, 0.30,
                 _clamp(5.0 - 0.10 * (Thb - 90.0), 2.0, 9.0),
                 "Supuesto: rango de consistencia de una pasta hot break; menos centímetros es una pasta más espesa",
                 "Supuesto: 5,0 cm con el hot break a 90 °C y 0,1 cm menos por cada °C más, porque el hot break más caliente inactiva antes las enzimas que rompen la pectina",
                 equipo_control=hb.id if hb else None, decimales=2),
        Variable("howard", "Recuento de mohos Howard", "% de campos positivos", None, 50.0, 4.0,
                 _clamp(25.0 + 150.0 * (0.10 - desc), 5.0, 80.0),
                 f"{FUENTE_CODEX}: no más de 50 % de campos positivos (producto diluido a cerca de 8 % de sólidos solubles)",
                 "Supuesto: 25 % con el descarte de 10 % en la selección (Agrozzi) y 1,5 puntos más por cada punto menos de descarte, porque entra más fruta dañada",
                 categoria="Oficial", equipo_control=sel.id if sel else None, decimales=1),
    ]


def variables_biomasa(pl) -> list[Variable]:
    desp = _equipo(pl, "despacho"); seca = _equipo(pl, "secador")
    d = desp.resultado.detalle if desp is not None and desp.resultado is not None else {}
    base = str(desp.v("base_humedad")) if desp is not None and "base_humedad" in desp.params else "bh"
    M = 100 * float(d.get("humedad_bs" if base == "bs" else "humedad_bh", 0.10))
    Mbh = 100 * float(d.get("humedad_bh", 0.10))
    norma = str(desp.v("norma")) if desp is not None and "norma" in desp.params else ""
    fuente_norma = desp.params["humedad_max"].fuente if desp is not None and "humedad_max" in desp.params else ""
    hmax = 100 * _v(desp, "humedad_max", 0.10); pci_min = _v(desp, "PCI_min", 0.0)
    pci = float(d.get("PCI_MJ_kg", 17.0)); ctrl = seca.id if seca else None
    out = [Variable("humedad", f"Humedad del producto (base {'seca' if base == 'bs' else 'húmeda'})", "%", None, hmax, 0.22, M,
                    f"{norma}: {fuente_norma}", "Balance de la planta: humedad que deja el secador (consigna del lazo de humedad)",
                    categoria="Oficial", equipo_control=ctrl, decimales=2),
           Variable("pci", "Poder calorífico inferior (base húmeda)", "MJ/kg", pci_min if pci_min > 0 else None, None, 0.12, pci,
                    f"{norma}: {fuente_norma}" if pci_min > 0 else "La norma no fija un mínimo",
                    "Balance de la planta: poder calorífico del producto despachado (ISO 18125)", categoria="Oficial", equipo_control=ctrl, decimales=2)]
    if "ENplus" in norma:          # pellet: el resto de las propiedades de la ENplus A1, como el simulador del profesor
        dm = abs(Mbh - 9.5)
        out += [
            Variable("cenizas", "Cenizas", "%", None, 0.7, 0.026, 0.45, f"ENplus A1: {fuente_norma}",
                     "Supuesto: aserrín de pino radiata con poca corteza", categoria="Oficial", decimales=3),
            Variable("durabilidad", "Durabilidad mecánica", "%", 98.0, None, 0.19, _clamp(99.1 - 0.105 * (Mbh - 9.5) ** 2, 90.0, 99.7),
                     f"ENplus A1: {fuente_norma}", f"Fórmula de qualityMean del profesor con la humedad de la planta ({FUENTE_PROF})",
                     categoria="Oficial", equipo_control=ctrl, decimales=2),
            Variable("finos", "Finos", "%", None, 1.0, 0.12, _clamp(0.55 + 0.3 * dm, 0.1, 8.0), f"ENplus A1: {fuente_norma}",
                     f"Fórmula de qualityMean del profesor ({FUENTE_PROF})", categoria="Oficial", decimales=2),
            Variable("densidad", "Densidad a granel", "kg/m³", 600.0, 750.0, 9.0, _clamp(655.0 - 7.0 * dm, 500.0, 800.0), f"ENplus A1: {fuente_norma}",
                     f"Fórmula de qualityMean del profesor ({FUENTE_PROF})", categoria="Oficial", decimales=0),
        ]
    return out


def variables(pl) -> list[Variable]:
    """Variables de calidad de la planta actual (resuelta). Tomate o biomasa; otra planta, sin variables."""
    if pl.rubro == "tomate":
        return variables_tomate(pl)
    if _equipo(pl, "despacho") is not None:
        return variables_biomasa(pl)
    return []


def acciones(pl) -> list[dict]:
    """Acciones correctivas de la pestaña Calidad (como los deslizadores del profesor): son parámetros de la planta."""
    out = []
    if pl.rubro == "tomate":
        for i, e in enumerate(pl.especs):
            if e.param == "brix_salida":
                out.append(dict(etiqueta="°Brix objetivo de la pasta (consigna DIC-302)", tipo="espec", idx=i, valor=100 * e.valor,
                                minimo=24.0, maximo=36.0, paso=0.1, escala=100.0, variable="brix"))
        for tipo, clave, et, var, lo, hi, paso in (("esterilizador", "T_salida", "Temperatura de esterilización (consigna TIC-401, °C)", "t_est", 95.0, 120.0, 0.5),
                                                    ("hot_break", "T_salida", "Temperatura del hot break (consigna TIC-101, °C)", "bostwick", 75.0, 96.0, 0.5),
                                                    ("recepcion_seleccion", "descarte", "Descarte en lavado y selección (fracción)", "howard", 0.02, 0.25, 0.01)):
            eq = _equipo(pl, tipo)
            if eq is not None and clave in eq.params:
                out.append(dict(etiqueta=et, tipo="param", equipo=eq.id, param=clave, valor=float(eq.params[clave].valor), minimo=lo, maximo=hi,
                                paso=paso, escala=1.0, variable=var))
    else:
        eq = _equipo(pl, "secador")
        if eq is not None and "humedad_salida" in eq.params:
            out.append(dict(etiqueta="Humedad a la salida del secador (base húmeda, fracción)", tipo="param", equipo=eq.id, param="humedad_salida",
                            valor=float(eq.params["humedad_salida"].valor), minimo=0.04, maximo=0.40, paso=0.005, escala=1.0, variable="humedad"))
    return out


def aplicar_accion(pl, accion: dict, valor: float) -> bool:
    """Cambia el parámetro de la acción; devuelve True si cambió (la planta se debe volver a resolver)."""
    if accion["tipo"] == "espec":
        e = pl.especs[accion["idx"]]; nuevo = float(valor) / accion["escala"]
        if abs(e.valor - nuevo) < 1e-12:
            return False
        e.valor = nuevo; pl.resuelta = False
        return True
    eq = pl.equipos[accion["equipo"]]
    if abs(float(eq.params[accion["param"]].valor) - float(valor)) < 1e-12:
        return False
    eq.set(accion["param"], float(valor))
    return True
