"""Catálogo de equipos de la línea de agar agar a partir de alga roja Gracilaria (PAT 143 b, tarea 9 del plan PAT 141, 20-11-2026).

Proceso de referencia (McHugh, 2003, FAO 441, sección 3.1.1; Armisen y Galatas, 1987, FAO 288, cap. 1): recepción del alga seca,
lavado e hidratación, tratamiento alcalino con NaOH en caliente, lavado y neutralización, extracción con agua caliente, filtración
en caliente con filtro prensa, enfriamiento y gelificación del extracto, prensado del gel (sinéresis), secado con aire caliente,
molienda y envasado. Una caldera a gas entrega el vapor del baño alcalino, de la extracción y de la batería del aire de secado.

Modelo de las corrientes: m es el caudal total (kg/h) y s la materia seca (kg/h: materia seca del alga, el agar disuelto y la soda
cuando la hay). El calor específico es la mezcla de agua y sólidos de motor/corrientes.py, con el de los sólidos tomado como el de
los carbohidratos de Choi y Okos (1986) a 50 °C (Supuesto: el alga y el agar son sobre todo polisacáridos). En extra van dos
razones que no cambian al repartir una corriente: «fr_naoh» (soda / materia seca) y «fr_agar» (agar disuelto / materia seca).

El agua de proceso y la soda entran como servicio (agua_kgh y reactivo_kgh): no se dibujan como corrientes, pero suman en el
balance de materia de cada equipo (motor/planta.cierres) y en Equipos auxiliares, como el aire de secado de la biomasa.

Corrientes para la recuperación de calor:
- Frías (sumideros): el baño alcalino, el agua de extracción y el aire de secado, desde su temperatura de entrada hasta la de
  proceso.
- Calientes (residuales): la lejía alcalina gastada, el extracto filtrado mientras se enfría hasta antes de gelificar y el escape
  húmedo del secador (sensible y latente).
Cada cifra lleva su fuente; lo que no tiene fuente va como Supuesto con su justificación."""
from __future__ import annotations
from ..motor.equipos import Equipo, Puerto, Resultado, Sumidero, P, capacidad_param
from ..motor.corrientes import Corriente, Residual
from ..motor.propiedades import CPW, _CP_CO, _poli
from .biomasa import SecadorBiomasa, _variante

RUBRO = "agar"
CONSULTA = "consulta 20-11-2026"
MCHUGH = "McHugh (2003), FAO Fisheries Technical Paper 441, sección 3.1.1"
ARMISEN = "Armisen y Galatas (1987), FAO Fisheries Technical Paper 288, cap. 1"
BELAT = "Belattmania et al. (2021), Marine Drugs 19(12), 672, sección 3"
CORREA = "Correa Rivas (2020), Universidad de Chile, ficha del repositorio"
ESCALANTE = "Escalante y Noriega (2019), Universidad de Lima"
JECFA = "JECFA (1997), especificación del agar (INS 406), 49.ª reunión"
T_SOLIDOS = 50.0                                     # °C a la que se evalúa el cp de los sólidos (punto medio del proceso)
CPS_AGAR = round(_poli(_CP_CO["carbohidrato"], T_SOLIDOS), 4)   # 1,6324 kJ/kg·K
FUENTE_CPS = (f"Choi y Okos (1986): cp de los carbohidratos a {T_SOLIDOS:.0f} °C; Supuesto: la materia seca del alga, el agar y la "
              "soda se tratan con ese cp (el alga es sobre todo polisacárido)")
J_SUP = "sin dato de una planta de agar ni fuente abierta; declare el valor del fabricante o el medido"


def humedad_bh(c: Corriente) -> float:
    return 1 - c.s / c.m if c.m else 0.0


def _corriente(nombre, m, s, T, tipo="producto", fase="liquido", **extra):
    return Corriente(nombre, tipo, m=m, s=s, T=T, fase=fase, cps=CPS_AGAR, extra=dict(extra))


def _f(v, d=1):
    """Número con punto de miles y coma decimal."""
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _CPmezcla(m, s):
    """Capacidad calorífica de flujo (kW/K) de m kg/h con s kg/h de sólidos."""
    return (CPW * m - (CPW - CPS_AGAR) * s) / 3600


def _h_agua(m, T):
    return m * CPW * T / 3600


def _agitador(valor=5.0):
    return P("energia_especifica", "Electricidad del agitador y la recirculación", valor, "kWh/t", "Supuesto", "",
             f"Por tonelada de alga recibida que pasa por el equipo; {J_SUP}. Se disipa al ambiente", 0, 100)


def _perdidas():
    return P("perdidas", "Pérdidas de calor por las paredes (fracción del calor útil)", 0.05, "—", "Supuesto", "",
             "Igual a la del secador del catálogo de biomasa; estanques con aislación", 0, 0.3)


def _T_agua():
    return P("T_agua", "Temperatura del agua de proceso que llega", 15.0, "°C", "Supuesto", "",
             "Agua de red o de pozo a la temperatura media anual de la zona sur de Chile", 2, 30)


class EquipoAgar(Equipo):
    rubro = RUBRO

    def _W(self, carga_kgh):
        return float(self.v("energia_especifica")) * carga_kgh / 1000 if "energia_especifica" in self.params else 0.0


# ----------------------------------------------------------------------------------------------- recepción
class RecepcionAlga(EquipoAgar):
    tipo = "alimentacion_alga"; nombre_tipo = "Recepción y pesaje del alga seca (bodega y tolva)"
    iso_categoria = 1; iso_letra = "B"; simbolo = "tolva"
    entradas = []
    salidas = [Puerto("producto", "producto", "Alga seca")]
    params_base = [
        P("materia", "Materia prima", "Alga roja seca en fardos (pelillo, Gracilaria chilensis)", "", "Usuario", "", "Solo descriptivo"),
        P("carga_t_h", "Alga seca que entra a la planta", 0.4, "t/h", "Usuario", "", "Se ajusta con la especificación de producción", 0.01, 20),
        P("humedad", "Humedad del alga recibida (base húmeda)", 0.20, "kg/kg", "Literatura",
          f"{ARMISEN}, «Post-harvest treatment»: el alga se seca hasta cerca de 20 % de humedad para guardarla ({CONSULTA})",
          "", 0.05, 0.5),
        P("T", "Temperatura del alga (ambiente)", 15.0, "°C", "Supuesto", "", "Temperatura media anual de la zona sur de Chile", -5, 35),
        P("dias", "Días de operación al año", 330, "d", "Supuesto", "",
          "El alga seca se guarda en fardos (Armisen y Galatas, 1987), así que la planta puede trabajar todo el año; se dejan 35 días de mantención", 1, 366),
        P("horas_dia", "Horas de operación por día", 24, "h/d", "Supuesto", "", "Tres turnos", 1, 24),
    ]

    def horas(self):
        return float(self.v("dias")) * float(self.v("horas_dia"))

    def calcular(self, ent):
        m = float(self.v("carga_t_h")) * 1000; M = float(self.v("humedad"))
        c = _corriente("Alga seca", m, m * (1 - M), float(self.v("T")), fase="solido", fr_naoh=0.0)
        r = Resultado(salidas={"producto": c})
        r.energia_in = [("Alga seca", c.H())]; r.energia_out = [("Alga seca", c.H())]
        r.detalle = dict(horas=self.horas(), carga_t_h=m / 1000, humedad_bh=M, materia_seca_t_h=c.s / 1000)
        return r


# ----------------------------------------------------------------------------------------------- lavados
class _Lavado(EquipoAgar):
    """Mezcla adiabática del alga con agua a T_agua; el alga sale escurrida con la humedad pedida y el resto del agua como efluente.
    quitar_soda: la soda que trae el alga se va con el agua de lavado (lavado completo)."""
    entradas = [Puerto("entrada", "producto", "Alga")]
    salidas = [Puerto("producto", "producto", "Alga lavada"), Puerto("efluente", "subproducto", "Agua de lavado")]
    quitar_soda = False
    nombre_salida = "Alga lavada"; nombre_efluente = "Agua de lavado"

    def calcular(self, ent):
        e = ent["entrada"]; Wa = float(self.v("razon_agua")) * e.s; Tw = float(self.v("T_agua")); Mh = float(self.v("humedad_salida"))
        r = Resultado()
        fr = float(e.extra.get("fr_naoh", 0.0) or 0.0)
        N = e.s * fr / (1 + fr) if fr > 0 else 0.0          # fr_naoh = soda / materia seca del alga
        Sa = e.s - N
        m_tot = e.m + Wa
        H_in = e.H() + _h_agua(Wa, Tw)
        T = H_in / _CPmezcla(m_tot, e.s) if m_tot else Tw
        s_alga = Sa if self.quitar_soda else e.s
        m_alga = s_alga / (1 - Mh) if Mh < 1 else e.m
        if m_alga > m_tot - (e.s - s_alga):
            r.avisos.append(f"{self.id}: el agua no alcanza para dejar el alga con {_f(100 * Mh, 0)} % de humedad; sale con toda el agua")
            m_alga = m_tot - (e.s - s_alga)
        a = _corriente(self.nombre_salida, m_alga, s_alga, T, fase="solido", fr_naoh=0.0 if self.quitar_soda or not Sa else N / Sa)
        ef = _corriente(self.nombre_efluente, m_tot - m_alga, e.s - s_alga, T, tipo="subproducto")
        W = self._W(e.m)
        r.salidas = {"producto": a, "efluente": ef}
        r.servicios = dict(agua_kgh=Wa, electricidad_kW=W)
        r.energia_in = [("Alga", e.H()), ("Agua de proceso", _h_agua(Wa, Tw)), ("Electricidad", W)]
        r.energia_out = [(self.nombre_salida, a.H()), (self.nombre_efluente, ef.H()), ("Electricidad disipada al ambiente", W)]
        r.detalle = dict(carga_t_h=e.m / 1000, agua_kgh=Wa, T_salida=T, humedad_salida=humedad_bh(a), soda_al_efluente_kgh=e.s - s_alga,
                         W_kW=W, volumen_util_m3=m_tot * float(self.v("tiempo_h")) / 1000)
        return r


class LavadoAlga(_Lavado):
    tipo = "lavado_alga"; nombre_tipo = "Estanque de lavado e hidratación del alga"
    iso_categoria = 11; iso_letra = "R"; simbolo = "recipiente_agitado"
    params_base = [
        P("razon_agua", "Agua de lavado por kg de materia seca del alga", 2.5, "kg/kg", "Derivado",
          f"{ESCALANTE}, Fig. 5.3, p. 45: 800 L de agua para 400 kg de alga seca",
          "800 / (400 × 0,80 de materia seca) = 2,5. Cifra de una lectura previa de la tesis, por verificar en el PDF; que esos 800 L "
          "sean los del lavado es Supuesto (la lectura no los asigna a una etapa)", 0.5, 50),
        P("humedad_salida", "Humedad del alga hidratada y escurrida (base húmeda)", 0.70, "kg/kg", "Supuesto", "",
          f"El alga seca absorbe agua al hidratarse; {J_SUP}. Con 2,5 kg de agua por kg de materia seca el alga llega hasta cerca de 73 %", 0.2, 0.95),
        P("tiempo_h", "Tiempo de residencia", 20 / 60, "h", "Literatura", f"{ESCALANTE}, sección 5.2.2.1, pp. 42-43: reposo de 20 min",
          "Solo para el volumen útil del estanque", 0.05, 24),
        _T_agua(), _agitador(), capacidad_param(),
    ]


class LavadoNeutralizacion(_Lavado):
    tipo = "lavado_neutralizacion_agar"; nombre_tipo = "Estanque de lavado y neutralización del alga tratada"
    iso_categoria = 11; iso_letra = "R"; simbolo = "recipiente_agitado"
    quitar_soda = True; nombre_salida = "Alga neutralizada"; nombre_efluente = "Agua de lavado con soda"
    params_base = [
        P("razon_agua", "Agua de lavado por kg de materia seca del alga", 25.0, "kg/kg", "Literatura",
          f"{BELAT}: el alga tratada se enjuaga y se remoja en 500 mL de agua por 20 g de alga seca ({CONSULTA})",
          "Razón de laboratorio (1:25); la planta puede usar menos agua con lavado en contracorriente", 1, 60),
        P("humedad_salida", "Humedad del alga neutralizada y escurrida (base húmeda)", 0.80, "kg/kg", "Supuesto", "",
          f"Algo mayor que la del alga hidratada: el álcali hincha el tejido; {J_SUP}", 0.2, 0.95),
        P("tiempo_h", "Tiempo de residencia", 0.5, "h", "Derivado", f"{ESCALANTE}, pp. 42-43: lavado de 30 min",
          "Solo para el volumen útil del estanque. McHugh (2003) agrega a veces un ácido muy débil; aquí la soda se va con el agua de "
          "lavado y el ácido no se modela (Supuesto)", 0.05, 24),
        _T_agua(), _agitador(), capacidad_param(),
    ]


# ----------------------------------------------------------------------------------------------- tratamiento alcalino
class TratamientoAlcalino(EquipoAgar):
    """Baño de NaOH en caliente con camisa o serpentín de vapor. El contenido (alga hidratada y solución fresca) se calienta de su
    temperatura de mezcla a la del baño; el alga sale escurrida con el líquido retenido y el resto es la lejía gastada, caliente."""
    tipo = "tratamiento_alcalino_agar"; nombre_tipo = "Reactor de tratamiento alcalino (NaOH en caliente)"
    iso_categoria = 2; iso_letra = "C"; simbolo = "reactor"
    entradas = [Puerto("entrada", "producto", "Alga hidratada"), Puerto("vapor", "vapor", "Vapor de caldera")]
    salidas = [Puerto("producto", "producto", "Alga tratada"), Puerto("lejia", "subproducto", "Lejía alcalina gastada"),
               Puerto("condensado", "condensado")]
    params_base = [
        P("razon_solucion", "Solución de NaOH por kg de materia seca del alga", 25.0, "kg/kg", "Literatura",
          f"{BELAT}: 20 g de alga seca en 500 mL de NaOH al 6 % ({CONSULTA})",
          "Razón de laboratorio (1:25); Armisen y Galatas (1987) usan 30 mL/g en la evaluación de laboratorio. Una planta reutiliza la "
          "lejía: la de Escalante y Noriega (2019, Fig. 5.3) gasta 40 kg de NaOH por 70 kg de agar, mucho menos que esta razón", 2, 60),
        P("conc_naoh", "Concentración de NaOH de la solución fresca", 0.035, "kg/kg", "Literatura",
          f"{MCHUGH}: NaOH al 2 a 5 % para Gracilaria ({CONSULTA})", "Punto medio del rango", 0.005, 0.1),
        P("T_bano", "Temperatura del baño alcalino", 85.0, "°C", "Literatura", f"{MCHUGH}: 85 a 90 °C; {ARMISEN}: 80 a 90 °C",
          "Límite inferior del rango de McHugh, el de menor consumo de vapor", 60, 98),
        P("tiempo_h", "Tiempo de tratamiento", 1.0, "h", "Literatura", f"{MCHUGH}: cerca de 1 h; {ARMISEN}: 3 a 5 h en la industria",
          "Solo para el volumen útil del reactor", 0.25, 6),
        P("humedad_salida", "Líquido retenido por el alga tratada y escurrida (fracción de su masa)", 0.80, "kg/kg", "Supuesto", "",
          f"Igual a la del alga neutralizada; {J_SUP}", 0.2, 0.95),
        P("T_solucion", "Temperatura de la solución fresca que llega", 15.0, "°C", "Supuesto", "",
          "Se prepara con agua de proceso a temperatura ambiente; la recuperación de calor la precalienta", 2, 90),
        _perdidas(), _agitador(),
        P("etiqueta", "Nombre de la corriente residual de la lejía", "Lejía", "", "Usuario"),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; R = float(self.v("razon_solucion")); c = float(self.v("conc_naoh")); Tb = float(self.v("T_bano"))
        Ts = float(self.v("T_solucion")); perd = float(self.v("perdidas")); Mh = float(self.v("humedad_salida"))
        r = Resultado()
        fr0 = float(e.extra.get("fr_naoh", 0.0) or 0.0)
        N0 = e.s * fr0 / (1 + fr0) if fr0 > 0 else 0.0
        Sa = e.s - N0
        Wsol = R * Sa; N = c * Wsol + N0; Wagua = Wsol * (1 - c)
        L = (e.m - e.s) + Wsol + N0                        # líquido del baño: agua del alga y solución (con la soda que traía el alga)
        H_sol = ((Wsol - c * Wsol) * CPW + c * Wsol * CPS_AGAR) * Ts / 3600
        m_tot = e.m + Wsol; s_tot = e.s + c * Wsol
        CP = _CPmezcla(m_tot, s_tot)
        T_mez = (e.H() + H_sol) / CP if CP else Tb
        if Tb <= T_mez:
            r.avisos.append(f"{self.id}: el baño ya está sobre {_f(Tb, 0)} °C al mezclar; no pide vapor")
        Q_util = max(CP * (Tb - T_mez), 0.0)
        Q_perd = Q_util * perd / (1 - perd) if perd < 1 else 0.0
        Q = Q_util + Q_perd
        T_out = max(Tb, T_mez)
        m_alga = Sa / (1 - Mh) if Mh < 1 else e.m
        Rliq = min(max(m_alga - Sa, 0.0), L)
        Nret = Rliq * N / L if L else 0.0
        alga = _corriente("Alga tratada", Sa + Rliq, Sa + Nret, T_out, fase="solido", fr_naoh=Nret / Sa if Sa else 0.0)
        lej = _corriente("Lejía alcalina gastada", L - Rliq, N - Nret, T_out, tipo="subproducto")
        W = self._W(e.m)
        r.salidas = {"producto": alga, "lejia": lej}
        r.servicios = dict(vapor_kW=Q, agua_kgh=Wagua, reactivo_kgh=c * Wsol, electricidad_kW=W)
        r.sumideros = [Sumidero("Baño alcalino", self.id, T_mez, T_out, CP)] if Q_util > 0 else []
        r.residuales = [Residual(str(self.v("etiqueta")) + "_" + self.id, self.id, T_out, lej.CP(), 0.0, None,
                                 "Lejía alcalina gastada que se descarta caliente (Supuesto: se puede enfriar en un intercambiador de "
                                 "placas apto para soda antes de neutralizarla)")]
        r.energia_in = [("Alga hidratada", e.H()), ("Solución de NaOH fresca", H_sol), ("Vapor (calor entregado)", Q), ("Electricidad", W)]
        r.energia_out = [("Alga tratada", alga.H()), ("Lejía gastada", lej.H()), ("Pérdidas por las paredes", Q_perd),
                         ("Electricidad disipada al ambiente", W)]
        r.detalle = dict(carga_t_h=e.m / 1000, solucion_kgh=Wsol, naoh_kgh=c * Wsol, T_mezcla=T_mez, Q_kW=Q, Q_util_kW=Q_util,
                         lejia_kgh=lej.m, W_kW=W, volumen_util_m3=m_tot * float(self.v("tiempo_h")) / 1000)
        return r


# ----------------------------------------------------------------------------------------------- extracción
class ExtractorAgar(EquipoAgar):
    """Extracción con agua caliente en estanque con camisa de vapor. El agua que se agrega deja el agar disuelto con la
    concentración pedida en la fase líquida; el residuo insoluble queda en suspensión hasta el filtro."""
    tipo = "extractor_agar"; nombre_tipo = "Extractor de agar con camisa de vapor"
    iso_categoria = 3; iso_letra = "W"; simbolo = "camisa"
    entradas = [Puerto("entrada", "producto", "Alga neutralizada"), Puerto("vapor", "vapor", "Vapor de caldera")]
    salidas = [Puerto("producto", "producto", "Extracto caliente con el residuo"), Puerto("condensado", "condensado")]
    params_base = [
        P("rendimiento", "Agar extraído por kg de materia seca del alga", 0.2326, "kg/kg", "Literatura",
          f"{CORREA}: 23,26 % sin extracción previa de proteínas (22,03 % con ella), Agarophyton chilense ({CONSULTA})",
          "Escala de laboratorio; la base seca es Supuesto. Belattmania et al. (2021) miden 20,5 % en G. gracilis con NaOH", 0.05, 0.40),
        P("conc_extracto", "Agar en la fase líquida del extracto", 0.01, "kg/kg", "Literatura",
          f"{ARMISEN}, sección 4: los extractos van de 0,8 a 1,5 %; {MCHUGH}: el gel tiene cerca de 1 % de agar",
          "Fija el agua de extracción: agua = agar × (1 − c) / c", 0.004, 0.03),
        P("T_extraccion", "Temperatura de extracción", 95.0, "°C", "Literatura", f"{MCHUGH}: Gracilaria con agua a 95 a 100 °C por 2 a 4 h",
          "Límite inferior del rango, el de menor consumo de vapor; sin presión", 80, 100),
        P("tiempo_h", "Tiempo de extracción", 2.0, "h", "Literatura", f"{MCHUGH}: 2 a 4 h", "Solo para el volumen útil del extractor", 0.5, 6),
        _T_agua(), _perdidas(), _agitador(),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; y = float(self.v("rendimiento")); c = float(self.v("conc_extracto")); Tx = float(self.v("T_extraccion"))
        Tw = float(self.v("T_agua")); perd = float(self.v("perdidas"))
        r = Resultado()
        fr = float(e.extra.get("fr_naoh", 0.0) or 0.0)
        N = e.s * fr / (1 + fr) if fr > 0 else 0.0
        if N > 1e-9:
            r.avisos.append(f"{self.id}: el alga llega con soda ({_f(N)} kg/h); falta el lavado y neutralización antes de la extracción")
        Sa = e.s - N; A = y * Sa
        W_liq = A * (1 - c) / c                            # agua de la fase líquida
        Wx = max(W_liq - (e.m - e.s), 0.0)
        if Wx == 0.0:
            r.avisos.append(f"{self.id}: el agua que trae el alga ya diluye el agar bajo {_f(100 * c)} %; no se agrega agua")
        m_tot = e.m + Wx
        CP = _CPmezcla(m_tot, e.s)
        T_mez = (e.H() + _h_agua(Wx, Tw)) / CP if CP else Tx
        Q_util = max(CP * (Tx - T_mez), 0.0)
        Q_perd = Q_util * perd / (1 - perd) if perd < 1 else 0.0
        Q = Q_util + Q_perd
        T_out = max(Tx, T_mez)
        x = _corriente("Extracto caliente con el residuo", m_tot, e.s, T_out, fr_naoh=fr, fr_agar=A / e.s if e.s else 0.0)
        W = self._W(e.m)
        r.salidas = {"producto": x}
        r.servicios = dict(vapor_kW=Q, agua_kgh=Wx, electricidad_kW=W)
        r.sumideros = [Sumidero("Agua de extracción", self.id, T_mez, T_out, CP)] if Q_util > 0 else []
        r.energia_in = [("Alga neutralizada", e.H()), ("Agua de extracción", _h_agua(Wx, Tw)), ("Vapor (calor entregado)", Q), ("Electricidad", W)]
        r.energia_out = [("Extracto caliente", x.H()), ("Pérdidas por las paredes", Q_perd), ("Electricidad disipada al ambiente", W)]
        r.detalle = dict(carga_t_h=e.m / 1000, agua_kgh=Wx, agar_extraido_kgh=A, T_mezcla=T_mez, Q_kW=Q, Q_util_kW=Q_util, W_kW=W,
                         volumen_util_m3=m_tot * float(self.v("tiempo_h")) / 1000)
        return r


# ----------------------------------------------------------------------------------------------- filtración
class FiltroPrensaAgar(EquipoAgar):
    tipo = "filtro_prensa_agar"; nombre_tipo = "Filtro prensa para el extracto caliente"
    iso_categoria = 5; iso_letra = "F"; simbolo = "filtro_prensa"
    entradas = [Puerto("entrada", "producto", "Extracto caliente con el residuo")]
    salidas = [Puerto("producto", "producto", "Extracto filtrado"), Puerto("torta", "subproducto", "Torta de residuo de alga")]
    params_base = [
        P("humedad_torta", "Líquido de la torta (fracción de su masa)", 0.70, "kg/kg", "Supuesto", "",
          f"La torta retiene extracto, y con él agar que se pierde; {J_SUP}", 0.2, 0.95),
        P("caida_T", "Enfriamiento del extracto en la filtración", 5.0, "K", "Supuesto", "",
          f"{ARMISEN}: el extracto se filtra caliente, a 85 a 100 °C, para que no gelifique; la caída es Supuesto", 0, 20),
        P("energia_especifica", "Electricidad de la bomba de alimentación del filtro", 2.0, "kWh/t", "Supuesto", "",
          f"Por tonelada de extracto; {J_SUP}", 0, 50),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; Mc = float(self.v("humedad_torta")); dT = float(self.v("caida_T"))
        r = Resultado()
        fa = e.extra.get("fr_agar")
        if fa is None:
            r.avisos.append(f"{self.id}: la corriente no trae el agar extraído (¿falta el extractor?); se supone que toda la materia seca es agar")
            fa = 1.0
        A = e.s * float(fa); Rs = e.s - A                   # agar disuelto y residuo insoluble
        L = e.m - Rs                                       # fase líquida (agua y agar disuelto)
        mc = Rs / (1 - Mc) if Mc < 1 else Rs
        liq_c = min(mc - Rs, L)
        perdida = liq_c * A / L if L else 0.0
        Tf = e.T - dT
        f = _corriente("Extracto filtrado", e.m - Rs - liq_c, A - perdida, Tf, fr_agar=1.0)
        t = _corriente("Torta de residuo de alga", Rs + liq_c, Rs + perdida, Tf, tipo="subproducto")
        W = self._W(e.m)
        r.salidas = {"producto": f, "torta": t}; r.servicios = dict(electricidad_kW=W)
        Q_perd = e.H() - f.H() - t.H()
        r.energia_in = [("Extracto caliente", e.H()), ("Electricidad", W)]
        r.energia_out = [("Extracto filtrado", f.H()), ("Torta", t.H()), ("Calor perdido en la filtración", Q_perd),
                         ("Electricidad disipada al ambiente", W)]
        r.detalle = dict(carga_t_h=e.m / 1000, agar_kgh=A, agar_en_torta_kgh=perdida, torta_kgh=t.m, T_filtrado=Tf, W_kW=W)
        return r


# ----------------------------------------------------------------------------------------------- gelificación
class GelificadorAgar(EquipoAgar):
    """Enfriamiento del extracto filtrado hasta que gelifica. El tramo sobre T_recuperable es calor residual del mapa (el extracto
    todavía no gelifica en el intercambiador); el tramo de abajo va al agua de enfriamiento y a la gelificación en bandejas."""
    tipo = "gelificador_agar"; nombre_tipo = "Enfriador del extracto y gelificación"
    iso_categoria = 4; iso_letra = "W"; simbolo = "intercambiador_placas"
    entradas = [Puerto("entrada", "producto", "Extracto filtrado")]
    salidas = [Puerto("producto", "producto", "Gel de agar")]
    params_base = [
        P("T_recuperable", "Temperatura hasta la que se puede recuperar el calor del extracto", 45.0, "°C", "Supuesto",
          f"{ARMISEN}: el gel se forma a 32 a 43 °C (solución de 1,5 %); {BELAT}: gelifica a 31,7 y 35,4 °C",
          "Sobre la temperatura de gelificación, con margen, para que el extracto no gelifique dentro del intercambiador", 35, 90),
        P("T_gel", "Temperatura del gel al salir", 25.0, "°C", "Supuesto", f"{BELAT}: el gel se forma a temperatura ambiente",
          "Bajo la temperatura de gelificación; se enfría con agua de enfriamiento", 5, 40),
        P("etiqueta", "Nombre de la corriente residual del extracto", "Extracto", "", "Usuario"),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; Tr = float(self.v("T_recuperable")); Tg = min(float(self.v("T_gel")), e.T)
        g = e.fraccion(1.0); g.nombre = "Gel de agar"; g.T = Tg; g.fase = "solido"
        CP = e.CP(); Q = CP * (e.T - Tg)
        r = Resultado(salidas={"producto": g})
        nm = str(self.v("etiqueta")) + "_" + self.id
        res = []
        if e.T > Tr:
            res.append(Residual(nm, self.id, e.T, CP, CP * (e.T - Tr), Tr, "Extracto filtrado que se enfría antes de gelificar"))
        bajo = min(e.T, Tr)
        if bajo > Tg:
            res.append(Residual(nm + "_gel", self.id, bajo, CP, CP * (bajo - Tg), Tg,
                                "Enfriamiento con agua bajo la temperatura recuperable (gelificación)", en_mapa=False))
        r.residuales = res
        r.energia_in = [("Extracto filtrado", e.H())]
        r.energia_out = [("Gel de agar", g.H()), ("Calor al agua de enfriamiento", Q)]
        r.detalle = dict(carga_t_h=e.m / 1000, Q_kW=Q, Q_recuperable_kW=CP * max(e.T - Tr, 0.0), CP_kW_K=CP)
        return r


# ----------------------------------------------------------------------------------------------- prensado del gel
class PrensaGel(EquipoAgar):
    tipo = "prensa_gel_agar"; nombre_tipo = "Prensa del gel (sinéresis)"
    iso_categoria = 5; iso_letra = "F"; simbolo = "filtro"
    entradas = [Puerto("entrada", "producto", "Gel de agar")]
    salidas = [Puerto("producto", "producto", "Gel prensado"), Puerto("agua", "subproducto", "Agua de sinéresis")]
    params_base = [
        P("solidos_salida", "Agar en el gel prensado", 0.20, "kg/kg", "Literatura",
          f"{MCHUGH}: el gel prensado tiene cerca de 20 % de agar; {ARMISEN}, sección 5D: hasta 25 %, en promedio 20 %",
          "McHugh (2003) describe también el congelado y descongelado, que deja el gel con 10 a 12 % de agar", 0.05, 0.30),
        P("energia_especifica", "Electricidad de la prensa hidráulica", 2.0, "kWh/t", "Supuesto", "",
          f"Por tonelada de gel; {J_SUP}", 0, 50),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; x = float(self.v("solidos_salida"))
        r = Resultado()
        if x <= e.x:
            r.avisos.append(f"{self.id}: el gel ya tiene {_f(100 * e.x)} % de agar; la prensa no saca agua")
            x = e.x
        m_p = e.s / x if x else e.m
        p = e.fraccion(1.0); p.m = m_p; p.nombre = "Gel prensado"
        a = _corriente("Agua de sinéresis", e.m - m_p, 0.0, e.T, tipo="subproducto")
        W = self._W(e.m)
        r.salidas = {"producto": p, "agua": a}; r.servicios = dict(electricidad_kW=W)
        r.energia_in = [("Gel", e.H()), ("Electricidad", W)]
        r.energia_out = [("Gel prensado", p.H()), ("Agua de sinéresis", a.H()), ("Electricidad disipada al ambiente", W)]
        r.detalle = dict(carga_t_h=e.m / 1000, agua_sineresis_kgh=a.m, W_kW=W)
        return r


# ----------------------------------------------------------------------------------------------- secado
class SecadorAgar(SecadorBiomasa):
    """Secador de banda con aire calentado por una batería de vapor (el mismo balance del secador de biomasa: materia seca constante,
    aire de secado desde el ambiente y escape húmedo como calor residual). El calor del aire lo pide como vapor a la caldera."""
    tipo = "secador_agar"; nombre_tipo = "Secador de banda del gel de agar (aire con batería de vapor)"
    rubro = RUBRO; rubros = (RUBRO,)
    iso_categoria = 9; iso_letra = "T"; simbolo = "secador_banda"
    entradas = [Puerto("entrada", "producto", "Gel prensado"), Puerto("vapor", "vapor", "Vapor de la batería del aire")]
    salidas = [Puerto("producto", "producto", "Agar seco en escamas"), Puerto("escape", "aire", "Aire húmedo de escape")]
    params_base = _variante(
        SecadorBiomasa.params_base,
        humedad_salida=dict(valor=0.15, categoria="Supuesto", fuente=f"{ARMISEN}: humedad bajo 18 %; {JECFA}: pérdida por secado bajo 22 %",
                            justificacion="Con margen bajo el límite más exigente (18 %)", minimo=0.03, maximo=0.5),
        T_aire_entrada=dict(valor=75.0, categoria="Supuesto", fuente=f"{BELAT}: el gel funde a 78,5 a 82,1 °C; {ARMISEN}: cerca de 85 °C",
                            justificacion="Bajo la temperatura de fusión del gel; ninguna fuente abierta da la del aire del secador industrial",
                            minimo=40, maximo=120),
        T_aire_salida=dict(valor=45.0, categoria="Supuesto", fuente="",
                           justificacion="Igual a la del secador de banda del chip; se varía en la sensibilidad"),
        T_producto=dict(valor=40.0, justificacion="Algo menor que la del escape"),
        perdidas=dict(justificacion="Igual a la del secador del catálogo de biomasa; secador con aislación"),
        T_ambiente=dict(justificacion="Temperatura media anual de la zona sur de Chile, igual a la del alga y del agua de proceso"),
        energia_especifica=dict(valor=19.0, categoria="Derivado",
                                fuente="Müller, Strauch y Schade (2024), lámina 6: secador de banda, cerca de 25 kWh por t de agua evaporada",
                                justificacion="25 kWh/t de agua × (1 − 0,20 / 0,85) t de agua por t de gel prensado que entra ≈ 19 kWh/t"),
    )

    def calcular(self, ent):
        r = super().calcular(ent)
        r.salidas["producto"].nombre = "Agar seco en escamas"
        r.energia_out = [("Agar seco en escamas" if c == "Biomasa seca" else c, v) for c, v in r.energia_out]
        r.energia_in = [("Gel prensado" if c == "Biomasa húmeda" else c, v) for c, v in r.energia_in]
        r.servicios["vapor_kW"] = r.servicios.pop("calor_kW", 0.0)
        r.detalle["Q_kW"] = r.servicios["vapor_kW"]
        return r


# ----------------------------------------------------------------------------------------------- molienda y envasado
class MolinoAgar(EquipoAgar):
    tipo = "molino_agar"; nombre_tipo = "Molino de martillos para agar"
    iso_categoria = 10; iso_letra = "Z"; simbolo = "molino_martillos"
    entradas = [Puerto("entrada", "producto", "Agar seco en escamas")]
    salidas = [Puerto("producto", "producto", "Agar en polvo")]
    params_base = [
        P("malla", "Tamaño del polvo", "80 a 100 mesh", "", "Literatura", f"{MCHUGH}: se muele a 80 a 100 mesh", "Solo descriptivo"),
        P("energia_especifica", "Energía eléctrica específica", 30.0, "kWh/t", "Supuesto",
          "Naehrig (s. f.), KAHL: molino de martillos de biomasa, 25 a 35 kWh por tonelada",
          "A falta de dato para agar se toma el del molino de biomasa del catálogo", 0, 300),
        P("fraccion_calor", "Fracción de la electricidad que calienta el producto", 0.2, "—", "Supuesto", "",
          "El aire que arrastra el polvo se lleva la mayor parte del calor; el resto se pierde al ambiente", 0, 1),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; W = self._W(e.m); f = float(self.v("fraccion_calor"))
        p = e.fraccion(1.0); p.nombre = "Agar en polvo"; CP = p.CP(); p.T = e.T + (W * f / CP if CP else 0.0)
        r = Resultado(salidas={"producto": p}); r.servicios = dict(electricidad_kW=W)
        r.energia_in = [("Agar seco", e.H()), ("Electricidad", W)]
        r.energia_out = [("Agar en polvo", p.H()), ("Electricidad perdida al ambiente", W * (1 - f))]
        r.detalle = dict(carga_t_h=e.m / 1000, W_kW=W, T_salida=p.T)
        return r


class EnvasadoAgar(EquipoAgar):
    """Envasado del polvo: verifica la humedad contra la especificación elegida."""
    tipo = "envasado_agar"; nombre_tipo = "Envasado del agar en polvo"
    iso_categoria = 13; iso_letra = "A"; simbolo = "maquina_acabado"
    entradas = [Puerto("entrada", "producto", "Agar en polvo")]
    salidas = [Puerto("producto", "producto", "Agar envasado")]
    params_base = [
        P("norma", "Especificación de calidad", "Agar grado alimentario (Armisen y Galatas, 1987)", "", "Literatura", ARMISEN, ""),
        P("humedad_max", "Humedad máxima del producto", 0.18, "kg/kg", "Literatura", f"{ARMISEN}, «Specifications»: humedad bajo 18 %",
          f"{JECFA} admite hasta 22 % de pérdida por secado", 0, 1),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; M = humedad_bh(e); Mlim = float(self.v("humedad_max")); ok = M <= Mlim + 1e-12
        r = Resultado()
        if not ok:
            r.avisos.append(f"{self.id}: la humedad del agar ({_f(100 * M)} %) supera el máximo de {self.v('norma')} ({_f(100 * Mlim, 0)} %)")
        p = e.fraccion(1.0); p.nombre = "Agar envasado"
        r.salidas = {"producto": p}
        r.energia_in = [("Agar en polvo", e.H())]; r.energia_out = [("Agar envasado", p.H())]
        r.detalle = dict(carga_t_h=e.m / 1000, producto_t_h=e.m / 1000, humedad_bh=M, agar_seco_t_h=e.s / 1000, cumple_humedad=ok, T=e.T)
        return r


CATALOGO = [RecepcionAlga, LavadoAlga, TratamientoAlcalino, LavadoNeutralizacion, ExtractorAgar, FiltroPrensaAgar, GelificadorAgar,
            PrensaGel, SecadorAgar, MolinoAgar, EnvasadoAgar]
