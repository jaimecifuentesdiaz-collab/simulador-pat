"""La inversión de pat_sim.motor.costos reproduce la del Capítulo 4 (A3, 5.355 MM$ con U medio)."""
import pytest
from pat_sim.motor import costos


def test_inversion_A3_capitulo4():
    areas = [296.12, 419.61, 595.88]   # E-101, E-102, E-103 con U medio (Tabla 45 del informe)
    assert costos.inversion_hx_mmclp(areas) == pytest.approx(5355.1, rel=2e-3)


def test_bomba_calor_central():
    assert costos.inversion_bomba_calor_mmclp(15956.0) == pytest.approx(21222.6, rel=1e-3)
