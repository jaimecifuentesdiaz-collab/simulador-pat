"""Catálogo de equipos de la línea de pasta de tomate.

Cada equipo declara su categoría de la Tabla C.1 y su letra código del Anexo D de la ISO 10628
(UNE-EN ISO 10628:2001), el símbolo con que se dibuja y su balance de materia y energía.
Las ecuaciones reproducen el modelo de la planta basada en Agrozzi (model.py, 26-10-2026).
"""
from __future__ import annotations
import numpy as np
from ..motor.equipos import Equipo, Puerto, Resultado, Sumidero, P, capacidad_param
from ..motor.corrientes import Corriente, Residual
from ..motor.propiedades import CPW, sat, trabajo_isentropico

RUBRO = "tomate"


class AlimentacionTomate(Equipo):
    tipo = "alimentacion_tomate"; nombre_tipo = "Recepción de tomate (tolva)"; rubro = RUBRO
    iso_categoria = 1; iso_letra = "B"; simbolo = "tolva"
    entradas = []
    salidas = [Puerto("producto", "producto", "Tomate fresco")]
    params_base = [
        P("temporada_t", "Tomate fresco procesado por temporada", 450000.0, "t", "Agrozzi", "DIA_Agrozzi_rev0.pdf, p. 47"),
        P("dias", "Días de operación de la temporada", 76, "d", "Derivado", "Balance de Masa_Rev0.pdf, p. 6: febrero a abril, lunes a sábado",
          "La energía de la temporada es proporcional a los días", 1, 366),
        P("horas_dia", "Horas de operación por día", 24, "h/d", "Agrozzi", "Tres turnos, Balance de Masa_Rev0.pdf, p. 6", "", 1, 24),
        P("T", "Temperatura del tomate en recepción", 25.0, "°C", "Supuesto", "Amon et al. (2015, p. 530) usan 26,7 °C",
          "Cercano al valor de la literatura", 5, 40),
        P("cp", "Calor específico del tomate", 3.98, "kJ/kg·K", "Literatura", "Amon et al. (2015, p. 529)"),
    ]

    def horas(self):
        return float(self.v("dias")) * float(self.v("horas_dia"))

    def calcular(self, ent):
        h = self.horas(); m = float(self.v("temporada_t")) / h * 1000
        c = Corriente("Tomate fresco", "producto", m=m, s=0.0, T=float(self.v("T")), cp=float(self.v("cp")))
        r = Resultado(salidas={"producto": c})
        r.energia_in = [("Tomate fresco", c.H())]; r.energia_out = [("Tomate fresco", c.H())]
        r.detalle = dict(horas=h, carga_t_h=m / 1000)
        return r


class RecepcionSeleccion(Equipo):
    tipo = "recepcion_seleccion"; nombre_tipo = "Lavado y selección"; rubro = RUBRO
    iso_categoria = 6; iso_letra = "F"; simbolo = "criba"
    entradas = [Puerto("entrada", "producto")]
    salidas = [Puerto("producto", "producto", "Tomate seleccionado"), Puerto("descarte", "subproducto", "Piedras, tallos, hojas y restos")]
    params_base = [
        P("descarte", "Descarte en recepción y selección", 0.10, "kg/kg", "Agrozzi",
          "1.000 / 10.000 t/d, Balance de Masa_Rev0.pdf, Tabla 2, p. 11", "Razón de la unidad de pastas y pulpas", 0, 0.5),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; f = float(self.v("descarte"))
        p = e.fraccion(1 - f); p.nombre = "Tomate seleccionado"
        d = e.fraccion(f); d.nombre = "Descarte"; d.tipo = "subproducto"
        r = Resultado(salidas={"producto": p, "descarte": d})
        r.energia_in = [("Tomate", e.H())]; r.energia_out = [("Tomate seleccionado", p.H()), ("Descarte", d.H())]
        r.detalle = dict(carga_t_h=e.m / 1000)
        return r


class Trituradora(Equipo):
    tipo = "trituradora"; nombre_tipo = "Trituradora"; rubro = "general"
    iso_categoria = 10; iso_letra = "Z"; simbolo = "trituradora"
    entradas = [Puerto("entrada", "producto")]
    salidas = [Puerto("producto", "producto", "Tomate triturado")]
    params_base = [capacidad_param()]

    def calcular(self, ent):
        e = ent["entrada"]; p = e.fraccion(1.0); p.nombre = "Tomate triturado"
        r = Resultado(salidas={"producto": p})
        r.energia_in = [("Tomate", e.H())]; r.energia_out = [("Tomate triturado", p.H())]
        r.detalle = dict(carga_t_h=e.m / 1000)
        return r


class HotBreak(Equipo):
    tipo = "hot_break"; nombre_tipo = "Calentamiento de inactivación enzimática (hot break)"; rubro = RUBRO
    iso_categoria = 4; iso_letra = "W"; simbolo = "intercambiador_tubular"
    entradas = [Puerto("entrada", "producto"), Puerto("vapor", "vapor", "Vapor de caldera")]
    salidas = [Puerto("producto", "producto", "Tomate a la temperatura de inactivación"), Puerto("condensado", "condensado")]
    params_base = [
        P("T_salida", "Temperatura del hot break", 90.0, "°C", "Agrozzi", "Dentro de 75 a 96 °C, DIA_Agrozzi_rev0.pdf, p. 48",
          "Sensibilidad en la hoja SENSIBILIDADES", 60, 100),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; Ts = float(self.v("T_salida"))
        p = e.fraccion(1.0); p.T = Ts; p.nombre = "Tomate a la salida del hot break"
        CP = e.CP(); Q = CP * (Ts - e.T)
        r = Resultado(salidas={"producto": p})
        r.servicios = dict(vapor_kW=Q)
        r.sumideros = [Sumidero("Hot break", self.id, e.T, Ts, CP)]
        r.energia_in = [("Tomate", e.H()), ("Vapor (calor entregado)", Q)]; r.energia_out = [("Tomate caliente", p.H())]
        r.detalle = dict(carga_t_h=e.m / 1000, CP_kW_K=CP, Q_kW=Q)
        return r


class Refinadora(Equipo):
    tipo = "refinadora"; nombre_tipo = "Extracción y refinado"; rubro = RUBRO
    iso_categoria = 6; iso_letra = "F"; simbolo = "tamiz"
    entradas = [Puerto("entrada", "producto")]
    salidas = [Puerto("jugo", "producto", "Jugo refinado"), Puerto("tomasa", "subproducto", "Pieles y semillas")]
    params_base = [
        P("tomasa", "Tomasa sobre la carga de la refinadora", 0.04 / 0.90, "kg/kg", "Derivado",
          "4 % del tomate recibido (400 / 10.000 t/d, Balance de Masa_Rev0.pdf, Tabla 2, p. 11) sobre el 90 % que llega a la refinadora",
          "Banda de 3 a 5 % del tomate recibido (Lu et al., 2019)", 0, 0.3),
        P("brix_jugo", "Sólidos solubles del jugo (°Brix/100)", 0.05, "kg/kg", "Literatura",
          "Simpson et al. (2008, p. 492); Amon et al. (2015, p. 527); coincide con la entrada del Apollo (CFT)", "", 0.03, 0.08),
        P("cps", "Calor específico de los sólidos solubles", 1.5, "kJ/kg·K", "Supuesto", "Informe 1, Tabla 25"),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; f = float(self.v("tomasa"))
        mj = e.m * (1 - f)
        j = Corriente("Jugo refinado", "producto", m=mj, s=mj * float(self.v("brix_jugo")), T=e.T, cps=float(self.v("cps")))
        t = e.fraccion(f); t.nombre = "Tomasa"; t.tipo = "subproducto"
        r = Resultado(salidas={"jugo": j, "tomasa": t})
        ajuste = e.H() - j.H() - t.H()
        r.energia_in = [("Tomate", e.H())]
        r.energia_out = [("Jugo", j.H()), ("Tomasa", t.H()), ("Cambio de modelo de calor específico (cp del tomate → cp del jugo por °Brix)", ajuste)]
        r.detalle = dict(carga_t_h=e.m / 1000, ajuste_cp_kW=ajuste)
        return r


class EvaporadorMVR(Equipo):
    tipo = "evaporador_mvr"; nombre_tipo = "Evaporador con recompresión mecánica de vapor (MVR)"; rubro = "general"
    iso_categoria = 4; iso_letra = "W"; simbolo = "evaporador_mvr"
    entradas = [Puerto("entrada", "producto"), Puerto("electricidad", "electricidad")]
    salidas = [Puerto("concentrado", "producto"), Puerto("condensado", "condensado"), Puerto("excedente", "vapor", "Vapor excedente al condensador de ajuste")]
    params_base = [
        P("brix_salida", "Concentración a la salida (°Brix/100)", 0.085, "kg/kg", "Fabricante", "CFT (2024a)", "", 0.05, 0.4),
        P("T_ebullicion", "Temperatura de ebullición", 70.0, "°C", "Supuesto", "Bajo 75 °C (DIA, p. 48)", "Bajo la cota que declara la planta", 40, 90),
        P("T_condensado", "Temperatura del condensado", 75.0, "°C", "Supuesto",
          "Ebullición bajo 75 °C (DIA, p. 48) más a lo más 10 °C producto/vapor (CFT)",
          "Banda de 65 a 85 °C: cobertura de la cascada de 48,53 % a 65,53 %", 50, 95),
        P("eta", "Rendimiento isentrópico del compresor", 0.80, "—", "Supuesto", "Cierra el balance de energía de los MVR", "Banda 0,70 a 0,90", 0.5, 0.95),
        P("etiqueta_condensado", "Nombre de la corriente residual del condensado", "F4", "", "Usuario"),
        P("etiqueta_excedente", "Nombre del calor excedente", "F6", "", "Usuario"),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; x = float(self.v("brix_salida")); Tb = float(self.v("T_ebullicion")); Tc = float(self.v("T_condensado"))
        if e.x >= x:
            raise ValueError(f"{self.id}: la concentración de salida ({x:.3f}) debe ser mayor que la de entrada ({e.x:.3f})")
        mc = e.s / x
        c = Corriente("Concentrado", "producto", m=mc, s=e.s, T=Tb, cps=e.cps)
        V = e.m - mc
        cond = Corriente("Condensado", "condensado", m=V, T=Tc, cp=CPW)
        w = trabajo_isentropico(Tb, Tc) / float(self.v("eta"))
        W = V * w / 3600
        vent = e.H() + W - c.H() - cond.H()
        hg = sat(Tb)[1]
        m_vent = vent * 3600 / (hg - CPW * Tc) if vent > 0 else 0.0
        r = Resultado(salidas={"concentrado": c, "condensado": cond,
                               "excedente": Corriente("Vapor excedente", "vapor", m=0.0, T=Tb, fase="vapor", extra=dict(Q_kW=vent))})
        r.servicios = dict(electricidad_kW=W)
        r.residuales = [Residual(str(self.v("etiqueta_condensado")), self.id, Tc, V * CPW / 3600, 0.0, None, "Condensado del " + self.nombre),
                        Residual(str(self.v("etiqueta_excedente")) + "_" + self.id, self.id, Tb, None, vent, None,
                                 "Calor excedente del " + self.nombre + " al condensador de ajuste", en_mapa=False)]
        r.energia_in = [("Alimentación", e.H()), ("Trabajo del compresor", W)]
        r.energia_out = [("Concentrado", c.H()), ("Condensado", cond.H()), ("Excedente al condensador de ajuste", vent)]
        r.detalle = dict(carga_t_h=e.m / 1000, agua_evaporada_kgh=V, w_kJ_kg=w, W_kW=W, excedente_kW=vent,
                         vapor_excedente_equivalente_kgh=m_vent, kWh_por_t_agua=W / (V / 1000) if V else 0)
        if vent < -1e-6:
            r.avisos.append(f"{self.id}: el balance pide calor externo ({-vent:.1f} kW); revise temperaturas o rendimiento")
        return r


class EvaporadorMultiefecto(Equipo):
    """Evaporador de múltiple efecto en contracorriente, con termocompresión (TVR) opcional en el efecto 1.
    El producto entra por el efecto más frío y sale por el más caliente (Venus T1500 de CFT)."""
    tipo = "evaporador_multiefecto"; nombre_tipo = "Evaporador de múltiple efecto con termocompresión (TVR)"; rubro = "general"
    iso_categoria = 4; iso_letra = "W"; simbolo = "evaporador_multiefecto"
    entradas = [Puerto("entrada", "producto"), Puerto("vapor", "vapor", "Vapor vivo de caldera")]
    salidas = [Puerto("concentrado", "producto"), Puerto("condensados", "condensado", "Condensados de los efectos"),
               Puerto("vapor_ultimo", "vapor", "Vapor del último efecto al condensador"),
               Puerto("condensado_vivo", "condensado", "Condensado del vapor vivo (retorna a caldera)")]
    params_base = [
        P("N", "Número de efectos", 3, "—", "Fabricante", "Venus T1500 de triple efecto, CFT (2024a)", "", 2, 6),
        P("T1", "Temperatura del efecto 1 (el más caliente)", 75.0, "°C", "Agrozzi", "Ebullición bajo 75 °C, DIA_Agrozzi_rev0.pdf, p. 48", "", 50, 100),
        P("TN", "Temperatura del último efecto", 55.57, "°C", "Literatura", "Simpson et al. (2008, Tabla 3, p. 496)", "Fija el pinch", 35, 80),
        P("Ts", "Temperatura del vapor vivo (260 kPa)", 129.08, "°C", "Literatura", "Simpson et al. (2008, p. 496)", "", 100, 180),
        P("tvr", "Termocompresión del vapor en el efecto 1", True, "", "Supuesto", "El fabricante clasifica el Venus como TVR (CFT, s. f.)"),
        P("Ra", "Razón de arrastre del eyector (kg aspirado / kg motriz)", 1.0, "kg/kg", "Supuesto", "Razón no publicada",
          "Sensibilidad de 0,5 a 1,5: cobertura de la cascada de 56,98 % a 56,78 %", 0, 3),
        P("dT_tvr", "Diferencia de temperatura de la mezcla sobre el efecto 1", 10.0, "K", "Fabricante", "Diferencia máxima producto/vapor (CFT, s. f.)", "", 0, 30),
        P("brix_salida", "Concentración a la salida (°Brix/100)", 0.273, "kg/kg", "Derivado",
          "Se ajusta con la especificación de diseño para que la pasta final tenga el °Brix pedido", "", 0.1, 0.45),
        P("etiquetas_condensados", "Nombres de los condensados de cada efecto", "F1a,F1b,F1c", "", "Usuario"),
        P("etiqueta_vapor", "Nombre del vapor del último efecto", "F3", "", "Usuario"),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; N = int(self.v("N")); T1 = float(self.v("T1")); TN = float(self.v("TN")); Ts = float(self.v("Ts"))
        tvr = bool(self.v("tvr")); Ra = float(self.v("Ra")); dTt = float(self.v("dT_tvr")); xV = float(self.v("brix_salida"))
        Ssol = e.s; A2 = e.m; cps = e.cps; k = CPW - cps
        if not 0 < xV < 1 or e.x >= xV:              # PAT 134: 0 °Brix daba una división por cero sin explicación
            raise ValueError(f"{self.id}: la concentración de salida ({xV:.3f}) debe ser mayor que la de entrada ({e.x:.3f}) y menor que 1")
        PV = Ssol / xV; WV = A2 - PV
        if WV <= 0:
            raise ValueError(f"{self.id}: la concentración de salida debe ser mayor que la de entrada")
        T = [T1 - i * (T1 - TN) / (N - 1) for i in range(N)]
        hf = [sat(t)[0] for t in T]; hg = [sat(t)[1] for t in T]; hfs, hgs = sat(Ts); ls = hgs - hfs
        n = N + 1; A = np.zeros((n, n)); b = np.zeros(n)
        for i in range(N):
            row = np.zeros(n); rhs = 0.0
            row[i] += -hg[i]
            for j in range(i): row[j] += -CPW * T[i]
            rhs += (CPW * PV - k * Ssol) * T[i]
            if i < N - 1:
                for j in range(i + 1): row[j] += CPW * T[i + 1]
                rhs -= (CPW * PV - k * Ssol) * T[i + 1]
            else:
                rhs -= (CPW * A2 - k * Ssol) * e.T
            if i == 0:
                if tvr:
                    hfm = sat(T[0] + dTt)[0]
                    row[N] += (hgs - hfm) + Ra * (hg[0] - hfm)
                else:
                    row[N] += ls
            else:
                row[i - 1] += (hg[i - 1] - hf[i - 1])
                if i == 1 and tvr: row[N] += -Ra * (hg[0] - hf[0])
            A[i] = row; b[i] = rhs
        A[N, :N] = 1; b[N] = WV
        sol = np.linalg.solve(A, b); V = [float(v) for v in sol[:N]]; S = float(sol[N])
        Se = Ra * S if tvr else 0.0
        hfm = sat(T[0] + dTt)[0] if tvr else hfs
        nombres = [s.strip() for s in str(self.v("etiquetas_condensados")).split(",")]
        if len(nombres) < N: nombres = [f"F1_{i + 1}" for i in range(N)]
        conc = Corriente("Concentrado", "producto", m=PV, s=Ssol, T=T[0], cps=cps)
        res = []; cond_m = 0.0; cond_H = 0.0
        # el vapor del efecto i (menos lo aspirado por el eyector en el efecto 1) condensa en la calandria del efecto i+1
        for i in range(N - 1):
            Vi = V[i] - (Se if i == 0 else 0.0)
            res.append(Residual(nombres[i], self.id, T[i], Vi * CPW / 3600, 0.0, None, f"Condensado del efecto {i + 2} (vapor del efecto {i + 1})"))
            cond_m += Vi; cond_H += Vi * hf[i] / 3600
        # el vapor del último efecto: condensa en superficie (condensado F1c) o va al condensador (F3)
        lamN = hg[-1] - hf[-1]
        res.append(Residual(nombres[N - 1], self.id, T[-1], V[-1] * CPW / 3600, 0.0, None, "Condensado del vapor del último efecto"))
        res.append(Residual(str(self.v("etiqueta_vapor")), self.id, T[-1], None, V[-1] * lamN / 3600, None, "Calor latente del vapor del último efecto"))
        vap = Corriente("Vapor del último efecto", "vapor", m=V[-1], T=T[-1], fase="vapor")
        condensados = Corriente("Condensados de los efectos", "condensado", m=cond_m, T=(cond_H * 3600 / cond_m / CPW) if cond_m else T[0], cp=CPW)
        m_vivo = S + Se
        cvivo = Corriente("Condensado del vapor vivo y del vapor aspirado", "condensado", m=m_vivo, T=T[0] + dTt if tvr else Ts, cp=CPW)
        r = Resultado(salidas={"concentrado": conc, "condensados": condensados, "vapor_ultimo": vap, "condensado_vivo": cvivo})
        r.servicios = dict(vapor_kgh=S, vapor_kW=S * ls / 3600)
        r.residuales = res
        H_in = e.H() + S * hgs / 3600
        H_out = conc.H() + cond_H + V[-1] * hg[-1] / 3600 + m_vivo * hfm / 3600
        r.energia_in = [("Alimentación", e.H()), ("Vapor vivo", S * hgs / 3600)]
        r.energia_out = [("Concentrado", conc.H()), ("Condensados de los efectos", cond_H),
                         ("Vapor del último efecto", V[-1] * hg[-1] / 3600), ("Condensado del vapor vivo", m_vivo * hfm / 3600)]
        r.detalle = dict(carga_t_h=e.m / 1000, T=T, V=V, S=S, Se=Se, economia=WV / S if S else None, agua_evaporada_kgh=WV,
                         ls=ls, lamN=lamN, cierre_kW=H_in - H_out)
        return r


class Esterilizador(Equipo):
    tipo = "esterilizador"; nombre_tipo = "Esterilizador"; rubro = RUBRO
    iso_categoria = 4; iso_letra = "W"; simbolo = "intercambiador_tubular"
    entradas = [Puerto("entrada", "producto"), Puerto("vapor", "vapor")]
    salidas = [Puerto("producto", "producto"), Puerto("condensado", "condensado")]
    params_base = [P("T_salida", "Temperatura de esterilización", 103.0, "°C", "Agrozzi", "Sobre 103 °C, DIA_Agrozzi_rev0.pdf, p. 48", "", 90, 140),
                   capacidad_param()]

    def calcular(self, ent):
        e = ent["entrada"]; Ts = float(self.v("T_salida"))
        p = e.fraccion(1.0); p.T = Ts; p.nombre = "Pasta esterilizada"
        Q = e.CP() * (Ts - e.T)
        r = Resultado(salidas={"producto": p}); r.servicios = dict(vapor_kW=Q)
        r.energia_in = [("Pasta", e.H()), ("Vapor (calor entregado)", Q)]; r.energia_out = [("Pasta esterilizada", p.H())]
        r.detalle = dict(carga_t_h=e.m / 1000, Q_kW=Q)
        return r


class EnfriamientoFlash(Equipo):
    tipo = "enfriamiento_flash"; nombre_tipo = "Enfriamiento flash al vacío"; rubro = RUBRO
    iso_categoria = 1; iso_letra = "B"; simbolo = "recipiente"
    entradas = [Puerto("entrada", "producto")]
    salidas = [Puerto("producto", "producto"), Puerto("vapor", "vapor", "Vapor flash al condensador")]
    params_base = [
        P("T_final", "Temperatura de la pasta enfriada", 40.0, "°C", "Agrozzi", "Bajo 40 °C, DIA_Agrozzi_rev0.pdf, p. 48", "", 20, 80),
        P("flash", "Enfriamiento flash al vacío", True, "", "Supuesto", "El fabricante informa que la planta adoptó el enfriamiento flash (CFT, 2024a)",
          "Sin flash la cascada sube a 64,43 %"),
        P("etiqueta", "Nombre de la corriente residual", "F2", "", "Usuario"),
        capacidad_param(),
    ]

    def calcular(self, ent):
        e = ent["entrada"]; Tc = float(self.v("T_final")); k = CPW - e.cps
        nm = str(self.v("etiqueta"))
        r = Resultado()
        if self.v("flash"):
            hfF, hgF = sat(Tc)
            mf = (CPW * e.m - k * e.s) * (e.T - Tc) / (hgF - CPW * Tc)
            p = Corriente("Pasta", "producto", m=e.m - mf, s=e.s, T=Tc, cps=e.cps)
            v = Corriente("Vapor flash", "vapor", m=mf, T=Tc, fase="vapor")
            r.salidas = {"producto": p, "vapor": v}
            r.residuales = [Residual(nm, self.id, Tc, None, mf * (hgF - hfF) / 3600, None, "Vapor del enfriamiento flash")]
            r.energia_in = [("Pasta caliente", e.H())]; r.energia_out = [("Pasta", p.H()), ("Vapor flash", v.H())]
            r.detalle = dict(carga_t_h=e.m / 1000, vapor_flash_kgh=mf)
        else:
            p = e.fraccion(1.0); p.T = Tc; p.nombre = "Pasta"
            CP = p.CP(); Q = CP * (e.T - Tc)
            r.salidas = {"producto": p, "vapor": Corriente("Sin vapor", "vapor", m=0.0, T=Tc, fase="vapor")}
            r.residuales = [Residual(nm, self.id, e.T, CP, Q, Tc, "Enfriamiento sensible de la pasta")]
            r.energia_in = [("Pasta caliente", e.H())]; r.energia_out = [("Pasta", p.H()), ("Calor al agua de enfriamiento", Q)]
            r.detalle = dict(carga_t_h=e.m / 1000, vapor_flash_kgh=0.0)
        return r


class LlenadoraAseptica(Equipo):
    tipo = "llenadora_aseptica"; nombre_tipo = "Llenado aséptico"; rubro = RUBRO
    iso_categoria = 13; iso_letra = "A"; simbolo = "maquina_acabado"
    entradas = [Puerto("entrada", "producto")]
    salidas = [Puerto("producto", "producto", "Pasta envasada")]
    params_base = [capacidad_param()]

    def calcular(self, ent):
        e = ent["entrada"]; p = e.fraccion(1.0); p.nombre = "Pasta envasada"
        r = Resultado(salidas={"producto": p})
        r.energia_in = [("Pasta", e.H())]; r.energia_out = [("Pasta envasada", p.H())]
        r.detalle = dict(carga_t_h=e.m / 1000, producto_t_h=e.m / 1000, brix=e.brix)
        return r


CATALOGO = [AlimentacionTomate, RecepcionSeleccion, Trituradora, HotBreak, Refinadora, EvaporadorMVR,
            EvaporadorMultiefecto, Esterilizador, EnfriamientoFlash, LlenadoraAseptica]
