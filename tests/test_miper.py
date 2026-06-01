"""Tests de la lógica VEP del MIPER (Guía ISP / DS 44)."""

from segav_core import miper


def test_vep_es_producto():
    assert miper.vep(2, 3) == 6
    assert miper.vep(4, 4) == 16
    assert miper.vep(1, 1) == 1


def test_vep_acota_rango_1_a_4():
    assert miper.vep(0, 3) == 3      # 0 -> 1
    assert miper.vep(9, 9) == 16     # >4 -> 4
    assert miper.vep(-2, 2) == 2


def test_vep_robusto_ante_basura():
    assert miper.vep(None, 2) == 1
    assert miper.vep("x", "y") == 1


def test_niveles_de_riesgo():
    assert miper.nivel(1)["nivel"] == "Trivial"
    assert miper.nivel(2)["nivel"] == "Trivial"
    assert miper.nivel(3)["nivel"] == "Tolerable"
    assert miper.nivel(4)["nivel"] == "Tolerable"
    assert miper.nivel(5)["nivel"] == "Moderado"
    assert miper.nivel(8)["nivel"] == "Moderado"
    assert miper.nivel(9)["nivel"] == "Importante"
    assert miper.nivel(12)["nivel"] == "Importante"
    assert miper.nivel(13)["nivel"] == "Intolerable"
    assert miper.nivel(16)["nivel"] == "Intolerable"


def test_nivel_incluye_accion_y_color():
    n = miper.nivel(16)
    assert n["color"] == "🔴"
    assert "no" in n["accion"].lower()
    assert n["tone"] == "danger"


def test_evaluacion_combina_vep_y_nivel():
    e = miper.evaluacion(4, 4)
    assert e["vep"] == 16
    assert e["nivel"] == "Intolerable"


def test_catalogos_presentes():
    assert "Seguridad" in miper.TIPOS_RIESGO
    assert "Psicosocial" in miper.TIPOS_RIESGO
    assert len(miper.PROBABILIDAD) == 4
    assert len(miper.CONSECUENCIA) == 4
    assert len(miper.JERARQUIA_CONTROLES) == 5
