"""Equipos genéricos de la ISO 10628 (PAT 132) para la opción «Todos los equipos» del catálogo del lienzo.

Cada símbolo de la serie básica de la Tabla C.1 que no tiene todavía un equipo con modelo propio (pasta de tomate, biomasa o
servicios) se ofrece como un equipo genérico: deja pasar la corriente sin cambiarla y, si se le declara, consume
electricidad por tonelada que entra, que se disipa al ambiente. Sirve para dibujar la planta completa con la simbología de la
norma (bombas, válvulas, transportadores, recipientes, básculas) y para que la vista de restricciones tome su capacidad.
Fuente de símbolos, categorías y letras: UNE-EN ISO 10628:2001, Tabla C.1 y Anexo D (simbolos/iso10628.py)."""
from __future__ import annotations
from ..motor.equipos import Equipo, Puerto, Resultado, P, capacidad_param
from ..simbolos import iso10628
from ..motor import hidraulica as HID      # PAT 133 (mejora 8): bombas y válvulas con modelo hidráulico

RUBRO = "iso"
# medio que circula por el equipo cuando no es el producto
MEDIO = {"ventilador": "aire", "compresor": "vapor", "eyector": "vapor", "bomba_vacio": "vapor", "chimenea": "humos"}


class EquipoISO(Equipo):
    rubro = RUBRO
    params_base = [P("energia_especifica", "Electricidad por tonelada que entra", 0.0, "kWh/t", "Usuario", "",
                     "Equipo genérico: declare el consumo del fabricante si lo conoce", 0, 500),
                   capacidad_param()]

    def calcular(self, ent):
        e = ent["entrada"]; W = float(self.v("energia_especifica") or 0) * e.m / 1000
        p = e.fraccion(1.0); p.nombre = f"Salida de {self.nombre}"
        r = Resultado(salidas={"salida": p}); r.servicios = dict(electricidad_kW=W) if W else {}
        r.energia_in = [("Entrada", e.H())] + ([("Electricidad", W)] if W else [])
        r.energia_out = [("Salida", p.H())] + ([("Electricidad disipada al ambiente", W)] if W else [])
        r.detalle = dict(carga_t_h=e.m / 1000)
        return r


# ---------------------------------------------------------------- PAT 133 (mejora 8): bombas y válvulas con parámetros propios
BOMBAS_CURVA = ("bomba", "bomba_centrifuga")                 # curva H = H0 − k·Q² (centrífuga)
BOMBAS_DESPLAZAMIENTO = ("bomba_desplazamiento", "bomba_tornillo")   # el caudal lo fija la velocidad: altura = la del sistema
VALVULAS = ("valvula", "valvula_retencion", "valvula_control", "valvula_seguridad", "valvula_mariposa", "valvula_bola", "valvula_tres_vias")
MARGEN_ALTURA = 1.10        # Supuesto: la bomba se elige con 10 % más de altura que la que pide la línea (la válvula toma el exceso)
CIERRE_SOBRE_DISENO = 1.25  # Supuesto: altura a caudal cero de 25 % sobre la del punto de diseño, orden habitual de una centrífuga


def _params_linea():
    return [P("L_linea", "Largo equivalente de la línea que mueve", HID.L_LINEA, "m", "Supuesto", "",
              "Tramo recto más accesorios entre dos equipos vecinos", 0, 2000),
            P("dz_linea", "Altura a vencer", HID.DZ_LINEA, "m", "Supuesto", "", "Del orden de la altura de un evaporador", -50, 200),
            P("D_linea", "Diámetro interno de la línea (vacío = por velocidad de diseño)", None, "mm", "Usuario", "",
              "Sin dato, se toma el diámetro que da 1,5 m/s en agua y 1,0 m/s en pasta (Supuesto de motor/hidraulica.py)", 5, 1000)]


class BombaISO(EquipoISO):
    """Bomba genérica: la electricidad sale del punto de operación contra la curva del sistema (motor/hidraulica.py).
    Si se declara la electricidad por tonelada del fabricante, se usa esa en lugar del cálculo."""
    es_bomba = True; curva = True
    params_base = [P("energia_especifica", "Electricidad por tonelada que entra (vacío o 0 = por el punto de operación)", 0.0, "kWh/t",
                     "Usuario", "", "Si se declara el consumo del fabricante, reemplaza el cálculo hidráulico", 0, 500),
                   P("H0", "Altura a caudal cero (vacío = se elige para la línea)", None, "m", "Supuesto", "",
                     "Sin dato: 1,25 × la altura de diseño, que es 1,10 × la altura que pide la línea", 1, 300),
                   P("k", "Coeficiente de la curva H = H0 − k·Q² (vacío = se elige para la línea)", None, "m/(m³/h)²", "Supuesto", "",
                     "Sin dato: la curva pasa por la altura de diseño al caudal del proceso", 0, 100),
                   P("eta_max", "Eficiencia máxima de la bomba", 0.70, "—", "Supuesto", "",
                     "Orden habitual de una centrífuga de proceso de tamaño medio", 0.2, 0.92),
                   P("Q_mej", "Caudal de mejor eficiencia (vacío = el del proceso)", None, "m³/h", "Supuesto", "",
                     "Sin dato, la bomba se elige para trabajar en su mejor eficiencia", 0.1, 5000),
                   ] + _params_linea() + [capacidad_param()]

    def _num(self, k):
        v = self.v(k)
        return None if v in (None, "") else float(v)

    def calcular(self, ent):
        e = ent["entrada"]
        if float(self.v("energia_especifica") or 0) > 0:
            r = EquipoISO.calcular(self, ent); r.detalle["origen_electricidad"] = "consumo declarado del fabricante"
            return r
        p = e.fraccion(1.0); p.nombre = f"Salida de {self.nombre}"
        r = Resultado(salidas={"salida": p}); r.detalle = dict(carga_t_h=e.m / 1000)
        props = HID.propiedades_corriente(e)
        if props is None:
            r.avisos.append(f"{self.id}: la corriente que entra no es un líquido con caudal; la bomba no consume electricidad")
            r.energia_in = [("Entrada", e.H())]; r.energia_out = [("Salida", p.H())]
            return r
        L, dz = float(self.v("L_linea")), float(self.v("dz_linea"))
        lin = HID.perdida_linea(e.m, props, self._num("D_linea"), L, dz)
        Q, rho = lin["Q_m3h"], props["rho"]
        eta_max = float(self.v("eta_max"))
        if self.curva:
            H_dis = MARGEN_ALTURA * lin["H_m"]
            H0 = self._num("H0") or CIERRE_SOBRE_DISENO * H_dis
            k = self._num("k") if self._num("k") is not None else HID.k_por_punto(H0, Q, H_dis) if H0 > H_dis else 0.0
            Qm = self._num("Q_mej") or Q
            b = HID.bomba_en_linea(Q, rho, H0, k, eta_max, Qm, dz, lin["D_mm"], L, props["mu"] or 0.001, HID.RUGOSIDAD_INOX,
                                   props["K"], props["n"])
            r.avisos += [f"{self.id}: {a}" for a in b["avisos"]]
            W = b["potencia_kW"]
            r.detalle.update(Q_m3h=Q, H0_m=H0, k=k, H_m=b["H_m"], H_sistema_m=b["H_sistema_m"], eta=b["eta"],
                             Q_natural_m3h=b["Q_natural_m3h"], dp_valvula_kPa=b["dp_valvula_kPa"])
        else:
            H = MARGEN_ALTURA * lin["H_m"]; W = HID.potencia_bombeo(Q, H, rho, eta_max)
            r.detalle.update(Q_m3h=Q, H_m=H, H_sistema_m=lin["H_m"], eta=eta_max)
        r.detalle.update(D_mm=lin["D_mm"], v=lin["v"], dp_linea_kPa=lin["dp_kPa"], regimen=lin["regimen"], W_kW=W,
                         origen_electricidad="punto de operación")
        r.servicios = dict(electricidad_kW=W)
        r.energia_in = [("Entrada", e.H()), ("Electricidad", W)]
        r.energia_out = [("Salida", p.H()), ("Electricidad disipada al ambiente", W)]
        return r


class BombaDesplazamientoISO(BombaISO):
    """Bomba de desplazamiento positivo o de tornillo: el caudal lo fija la velocidad, la altura es la de la línea."""
    curva = False
    params_base = [p for p in BombaISO.params_base if p.clave not in ("H0", "k", "Q_mej")]


class ValvulaISO(EquipoISO):
    """Válvula genérica con coeficiente Cv (ISA-75.01): deja pasar la corriente e informa su caída de presión."""
    params_base = [P("Cv", "Coeficiente de la válvula Cv (vacío = se dimensiona)", None, "gpm/psi^0,5", "Usuario", "",
                     "Con Q en m³/h y ΔP en bar, Q = 0,865·Cv·√(ΔP/G) (ANSI/ISA-75.01.01)", 0.01, 10000),
                   P("dp_diseno", "Caída de presión de diseño (para dimensionar el Cv)", 50.0, "kPa", "Supuesto", "",
                     "Orden habitual de la caída que se asigna a una válvula de control en una línea de proceso", 1, 1000),
                   P("energia_especifica", "Electricidad por tonelada que entra (actuador)", 0.0, "kWh/t", "Usuario", "",
                     "Equipo genérico: declare el consumo del actuador si lo conoce", 0, 500),
                   capacidad_param()]

    def calcular(self, ent):
        r = EquipoISO.calcular(self, ent); e = ent["entrada"]
        props = HID.propiedades_corriente(e)
        if props is None:
            return r
        Q = e.m / props["rho"]; Gr = props["rho"] / 1000.0
        Cv = self.v("Cv")
        Cv = float(Cv) if Cv not in (None, "") else HID.cv_requerido(Q, float(self.v("dp_diseno")), Gr)
        r.detalle.update(Q_m3h=Q, G=Gr, Cv=Cv, dp_kPa=HID.dp_valvula(Cv, Q, Gr))
        if props["modelo"] != "newtoniano":
            r.avisos.append(f"{self.id}: la ecuación del Cv es para líquidos newtonianos; en la pasta la caída es una estimación")
        return r


def _base(sid):
    if sid in BOMBAS_CURVA: return BombaISO
    if sid in BOMBAS_DESPLAZAMIENTO: return BombaDesplazamientoISO
    if sid in VALVULAS: return ValvulaISO
    return EquipoISO


def _clase(sid, nombre, cat, letra):
    medio = MEDIO.get(sid, "producto")
    return type(f"ISO_{sid}", (_base(sid),), dict(
        tipo=f"iso_{sid}", nombre_tipo=nombre, iso_categoria=cat, iso_letra=letra, simbolo=sid,
        descripcion=f"Equipo genérico de la ISO 10628, categoría {cat} ({iso10628.CATEGORIAS.get(cat, '')}).",
        entradas=[Puerto("entrada", medio)], salidas=[Puerto("salida", medio)]))


def catalogo(usados: set[str]) -> list[type]:
    """Una clase por cada símbolo de la Tabla C.1 que no tenga ya un equipo con modelo propio."""
    return [_clase(sid, nom, cat, letra) for sid, (nom, cat, letra, _d) in iso10628.SIMBOLOS.items() if sid not in usados]
