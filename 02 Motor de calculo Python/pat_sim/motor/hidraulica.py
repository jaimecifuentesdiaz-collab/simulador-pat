"""Hidráulica de la planta (PAT 133, mejora 8): curva de bomba centrífuga, curva del sistema, punto de operación, válvula con
Cv y pérdida de carga de cada línea de líquido de la planta.

- Bomba centrífuga: H = H0 − k·Q² (Q en m³/h, H en m) y eficiencia parabólica η = η_máx·[2·Q/Q_mej − (Q/Q_mej)²], con
  máximo η_máx en el caudal de mejor eficiencia Q_mej (forma de uso común en el ajuste de curvas; Supuesto de forma).
- Sistema: H_s = Δz + h_f, con h_f de Darcy-Weisbach (Swamee y Jain, 1976) o ley de potencia para la pasta (Reynolds de
  Metzner-Reed, Steffe, 1996), las dos en calculadoras.tuberia.
- Válvula: Q = N1·Cv·√(ΔP/G) (ANSI/ISA-75.01.01, líquido sin cavitación ni corrección por viscosidad), con N1 = 1 para
  Q en gpm y ΔP en psi, y N1 = 0,865 para Q en m³/h y ΔP en bar. Aquí Cv va en gpm/psi^0,5, Q en m³/h y ΔP en kPa.
- Potencia de bombeo: P = ρ·g·Q·H/η.
"""
from __future__ import annotations
import math
from . import calculadoras as K
from . import propiedades as PR

G = 9.81
N1_M3H_BAR = 0.865          # ANSI/ISA-75.01.01, constante numérica para Q en m³/h y ΔP en bar
FUENTES = {
    "bomba": "Curva cuadrática H = H0 − k·Q² y eficiencia parabólica (Supuesto de forma, de uso común en el ajuste de curvas de bombas)",
    "sistema": "Swamee y Jain (1976); Steffe (1996), en calculadoras.tuberia",
    "valvula": "ANSI/ISA-75.01.01, ecuación de dimensionamiento de válvulas de control para líquidos",
}
# Supuestos de la red (cada uno con su justificación; se cambian en la interfaz)
V_DISENO_AGUA = 1.5          # m/s; Supuesto: velocidad media de diseño para agua y condensado en líneas de proceso (1 a 3 m/s es la banda habitual)
V_DISENO_PASTA = 1.0         # m/s; Supuesto: menor que en agua porque la pérdida de carga crece con la viscosidad aparente
L_LINEA = 30.0               # m; Supuesto: largo equivalente (tramo recto más accesorios) entre dos equipos vecinos
DZ_LINEA = 5.0               # m; Supuesto: altura a vencer entre equipos, del orden de la altura de un evaporador
RUGOSIDAD_INOX = 0.0015      # mm; Supuesto: tubo estirado de acero inoxidable sanitario (valor de tablas de rugosidad absoluta)
ETA_BOMBA = 0.65             # Supuesto: el mismo valor por defecto de la calculadora de bombas y tuberías
BRIX_TOMATE_ENTERO = 5.0     # Supuesto: el tomate triturado antes de la refinadora se trata como jugo de 5 °Brix (el jugo del escenario base)


# ---------------------------------------------------------------- bomba
def curva_bomba(Q_m3h: float, H0: float, k: float) -> float:
    """Altura de la bomba (m) a Q (m³/h)."""
    return H0 - k * Q_m3h * Q_m3h


def eficiencia_bomba(Q_m3h: float, eta_max: float, Q_mej: float) -> float:
    """Eficiencia parabólica con máximo eta_max en Q_mej; vale 0 en Q = 0 y en Q = 2·Q_mej."""
    if Q_mej <= 0:
        raise ValueError("El caudal de mejor eficiencia debe ser positivo")
    q = Q_m3h / Q_mej
    return max(0.0, eta_max * (2 * q - q * q))


def potencia_bombeo(Q_m3h: float, H_m: float, rho: float, eta: float) -> float:
    """Potencia en el eje (kW) = ρ·g·Q·H/η."""
    if eta <= 0:
        raise ValueError("La eficiencia de la bomba debe ser positiva")
    return rho * G * Q_m3h / 3600 * H_m / eta / 1000


def k_por_punto(H0: float, Q_m3h: float, H_m: float) -> float:
    """Coeficiente k de la curva que pasa por (Q, H)."""
    if Q_m3h <= 0 or H_m >= H0:
        raise ValueError("El punto debe tener caudal positivo y altura menor que la altura a caudal cero")
    return (H0 - H_m) / (Q_m3h * Q_m3h)


# ---------------------------------------------------------------- sistema y punto de operación
def altura_sistema(Q_m3h: float, dz_m: float, D_mm: float, L_m: float, rho=1000.0, mu_Pas=0.001, rug_mm=RUGOSIDAD_INOX,
                   K_pl=None, n_pl=None) -> float:
    """Altura del sistema (m): estática más pérdidas por fricción (calculadoras.tuberia)."""
    if Q_m3h <= 1e-9:
        return dz_m
    return K.tuberia(Q_m3h, D_mm, L_m, rho, mu_Pas, rug_mm, K_pl, n_pl, 1.0, dz_m)["H_m"]


def punto_operacion(H0: float, k: float, sistema, Q_max: float | None = None, tol=1e-9) -> dict:
    """Intersección de la curva de la bomba con la del sistema (sistema: función Q → H). Bisección sobre Q."""
    Qm = Q_max if Q_max else math.sqrt(H0 / k)
    f = lambda q: curva_bomba(q, H0, k) - sistema(q)
    if f(0.0) <= 0:
        return dict(Q_m3h=0.0, H_m=sistema(0.0), existe=False)
    lo, hi = 0.0, Qm
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(mid) > 0: lo = mid
        else: hi = mid
        if hi - lo < tol: break
    Q = (lo + hi) / 2
    return dict(Q_m3h=Q, H_m=curva_bomba(Q, H0, k), existe=True)


def bomba_en_linea(Q_m3h, rho, H0, k, eta_max, Q_mej, dz_m, D_mm, L_m, mu_Pas=0.001, rug_mm=RUGOSIDAD_INOX, K_pl=None, n_pl=None) -> dict:
    """Punto natural de la bomba en la línea y operación al caudal que impone el proceso: si la bomba da más altura que la que pide
    la línea, el exceso lo toma una válvula de control (estrangulación); si da menos, la bomba no alcanza ese caudal."""
    sis = lambda q: altura_sistema(q, dz_m, D_mm, L_m, rho, mu_Pas, rug_mm, K_pl, n_pl)
    po = punto_operacion(H0, k, sis)
    Hs = sis(Q_m3h); Hb = curva_bomba(Q_m3h, H0, k); avisos = []
    if Hb >= Hs:
        H = Hb; exceso = Hb - Hs
    else:
        H = Hs; exceso = 0.0
        avisos.append(f"La bomba da {Hb:.1f} m al caudal del proceso y la línea pide {Hs:.1f} m: no alcanza ese caudal "
                      "(se calcula la potencia con la altura de la línea, como si se eligiera una bomba mayor)".replace(".", ","))
    eta = eficiencia_bomba(Q_m3h, eta_max, Q_mej)
    if eta < 0.2:
        avisos.append("La bomba trabaja lejos de su caudal de mejor eficiencia (eficiencia bajo 20 %); se usa 20 %")
        eta = max(eta, 0.2)
    W = potencia_bombeo(Q_m3h, H, rho, eta)
    return dict(Q_m3h=Q_m3h, H_bomba_m=Hb, H_sistema_m=Hs, H_m=H, eta=eta, potencia_kW=W, Q_natural_m3h=po["Q_m3h"],
                H_natural_m=po["H_m"], exceso_valvula_m=exceso, dp_valvula_kPa=rho * G * exceso / 1000, avisos=avisos)


# ---------------------------------------------------------------- válvula (ISA-75.01)
def caudal_valvula(Cv: float, dp_kPa: float, G_rel: float = 1.0) -> float:
    """Caudal (m³/h) por una válvula de coeficiente Cv (gpm/psi^0,5) con caída ΔP (kPa) y densidad relativa G."""
    return N1_M3H_BAR * Cv * math.sqrt(max(dp_kPa, 0.0) / 100.0 / G_rel)


def dp_valvula(Cv: float, Q_m3h: float, G_rel: float = 1.0) -> float:
    """Caída de presión (kPa) en una válvula de Cv dado al caudal Q (m³/h)."""
    if Cv <= 0:
        raise ValueError("El Cv debe ser positivo")
    return 100.0 * G_rel * (Q_m3h / (N1_M3H_BAR * Cv)) ** 2


def cv_requerido(Q_m3h: float, dp_kPa: float, G_rel: float = 1.0) -> float:
    """Cv (gpm/psi^0,5) que deja pasar Q (m³/h) con una caída ΔP (kPa)."""
    if dp_kPa <= 0:
        raise ValueError("La caída de presión debe ser positiva")
    return Q_m3h / (N1_M3H_BAR * math.sqrt(dp_kPa / 100.0 / G_rel))


# ---------------------------------------------------------------- propiedades de una corriente y pérdida de una línea
def propiedades_corriente(c) -> dict | None:
    """Densidad y modelo reológico de una corriente líquida (None si no es líquida o no tiene caudal)."""
    if c is None or c.m <= 0 or c.fase != "liquido":
        return None
    T = max(0.0, min(float(c.T), 150.0))
    if c.tipo in ("agua", "condensado") or (c.tipo not in ("producto", "subproducto") and c.s == 0):
        return dict(modelo="newtoniano", rho=PR.densidad_agua(T), mu=PR.viscosidad_agua(T), K=None, n=None, brix=0.0, T=T)
    brix = c.brix if c.s > 0 else BRIX_TOMATE_ENTERO
    Kp, n = PR.reologia_pasta(brix, T)
    return dict(modelo="ley de potencia", rho=PR.densidad_pasta(brix, T), mu=None, K=Kp, n=n, brix=brix, T=T,
                supuesto_brix=c.s <= 0)


def diametro_por_velocidad(Q_m3h: float, v_ms: float) -> float:
    """Diámetro interno (mm) que da la velocidad de diseño v (m/s) al caudal Q (m³/h)."""
    return 1000 * math.sqrt(4 * Q_m3h / 3600 / (math.pi * v_ms))


def perdida_linea(m_kgh: float, props: dict, D_mm: float | None = None, L_m: float = L_LINEA, dz_m: float = DZ_LINEA,
                  v_diseno: float | None = None, rug_mm: float = RUGOSIDAD_INOX, eta: float = ETA_BOMBA) -> dict:
    """Caudal volumétrico, diámetro (dado o por velocidad de diseño), pérdida de carga y potencia de bombeo de una línea."""
    rho = props["rho"]; Q = m_kgh / rho
    pasta = props["modelo"] == "ley de potencia"
    v = v_diseno or (V_DISENO_PASTA if pasta else V_DISENO_AGUA)
    D = D_mm or diametro_por_velocidad(Q, v)
    t = K.tuberia(Q, D, L_m, rho, props["mu"] or 0.001, rug_mm, props["K"], props["n"], eta, dz_m)
    return dict(Q_m3h=Q, D_mm=D, v=t["v"], Re=t["Re"], f=t["f"], regimen=t["regimen"], dp_kPa=t["dp_kPa"], H_m=t["H_m"],
                potencia_kW=t["potencia_kW"], rho=rho, modelo=props["modelo"])


# ---------------------------------------------------------------- red de la planta
def _horas(pl) -> float | None:
    for e in pl.equipos.values():
        if hasattr(e, "horas"):
            return float(e.horas())
    h = pl.globales.get("horas_temporada")
    return float(h) if h else None


def red_hidraulica(pl, v_agua: float = V_DISENO_AGUA, v_pasta: float = V_DISENO_PASTA, L_m: float = L_LINEA,
                   dz_m: float = DZ_LINEA, rug_mm: float = RUGOSIDAD_INOX, eta: float = ETA_BOMBA) -> dict:
    """Recorre las conexiones de proceso de la planta resuelta y estima, para cada línea de líquido con caudal másico, el
    diámetro por velocidad de diseño (Supuesto), la pérdida de carga y la potencia de bombeo. Las corrientes de sólidos
    (biomasa), de gases y de servicios no se cuentan."""
    if not pl.resuelta:
        raise ValueError("Resuelva la planta antes de calcular la red hidráulica")
    filas, omitidas, avisos = [], 0, []
    for c in pl.conexiones:
        if pl.es_servicio(c):
            continue
        cor = pl.salidas.get((c.origen, c.puerto_origen))
        cor = cor.fraccion(c.reparto / 100) if cor is not None else None
        props = propiedades_corriente(cor)
        if props is None:
            omitidas += 1; continue
        r = perdida_linea(cor.m, props, None, L_m, dz_m, v_pasta if props["modelo"] == "ley de potencia" else v_agua, rug_mm, eta)
        bomba = next((k for k in (c.origen, c.destino) if getattr(pl.equipos[k], "es_bomba", False)), None)
        filas.append(dict(linea=c.nombre or f"{c.origen} → {c.destino}", origen=c.origen, destino=c.destino, tipo=cor.tipo,
                          m_kgh=cor.m, T=props["T"], brix=props["brix"], K=props["K"], n=props["n"], bomba_diagrama=bomba,
                          supuesto_brix=bool(props.get("supuesto_brix")), **r))
    if any(f["supuesto_brix"] for f in filas):
        avisos.append(f"Las líneas de tomate sin °Brix se calculan como jugo de {BRIX_TOMATE_ENTERO:.0f} °Brix (Supuesto)")
    tot = sum(f["potencia_kW"] for f in filas); h = _horas(pl)
    return dict(lineas=filas, potencia_total_kW=tot, horas=h, energia_MWh=tot * h / 1000 if h else None, omitidas=omitidas,
                supuestos=dict(v_agua=v_agua, v_pasta=v_pasta, L_m=L_m, dz_m=dz_m, rug_mm=rug_mm, eta=eta), avisos=avisos)
