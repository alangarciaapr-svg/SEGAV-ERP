"""Tests de la lógica pura del DS 44 (tramos y elementos exigibles)."""

from segav_core import ds44


def test_tramos_por_numero_trabajadores():
    assert ds44.worker_tier(0)["key"] == "micro"
    assert ds44.worker_tier(9)["key"] == "micro"
    assert ds44.worker_tier(10)["key"] == "pequena"
    assert ds44.worker_tier(25)["key"] == "pequena"
    assert ds44.worker_tier(26)["key"] == "mediana"
    assert ds44.worker_tier(100)["key"] == "mediana"
    assert ds44.worker_tier(101)["key"] == "grande"


def test_tramo_robusto_ante_valores_invalidos():
    assert ds44.worker_tier(None)["key"] == "micro"
    assert ds44.worker_tier("x")["key"] == "micro"


def _keys(n):
    return {e["key"] for e in ds44.required_elements(n)}


def test_micro_no_exige_riohs_ni_cphs():
    k = _keys(5)
    assert "iper" in k and "pdtp" in k and "capacitaciones" in k
    assert "riohs" not in k
    assert "cphs" not in k
    assert "delegado_sst" not in k
    assert "depto_prevencion" not in k


def test_pequena_exige_riohs_y_delegado_no_cphs():
    k = _keys(15)
    assert "riohs" in k
    assert "delegado_sst" in k
    assert "cphs" not in k


def test_mediana_exige_cphs_y_actas_no_delegado():
    k = _keys(50)
    assert "riohs" in k
    assert "cphs" in k
    assert "cphs_actas" in k
    assert "delegado_sst" not in k
    assert "depto_prevencion" not in k


def test_grande_exige_departamento_prevencion():
    k = _keys(150)
    assert "cphs" in k
    assert "depto_prevencion" in k


def test_summarize_excluye_no_aplica():
    estados = {
        "a": "Cumple",
        "b": "Cumple",
        "c": "No cumple",
        "d": "No aplica",
    }
    s = ds44.summarize(estados)
    assert s["aplicables"] == 3  # excluye 'd'
    assert s["no_aplica"] == 1
    # 2 cumple de 3 aplicables = 66.7% -> 67
    assert s["pct"] == 67
    assert s["faltantes"] == ["c"]


def test_summarize_en_proceso_vale_medio():
    estados = {"a": "Cumple", "b": "En proceso"}
    s = ds44.summarize(estados)
    # (1 + 0.5) / 2 = 75%
    assert s["pct"] == 75


def test_summarize_vacio():
    s = ds44.summarize({})
    assert s["pct"] == 0
    assert s["aplicables"] == 0


def test_company_profile_vacio():
    s = ds44.company_profile_status({})
    assert s["pct"] == 0
    assert s["completos"] == 0
    assert len(s["missing"]) == s["total"]


def test_company_profile_parcial():
    company = {
        "razon_social": "ACME Ltda",
        "rut": "76123456-7",
        "direccion": "Av. Siempre Viva 123",
        "telefono": "",
        "email": None,
        "organismo_admin": "ACHS",
    }
    s = ds44.company_profile_status(company)
    assert s["completos"] == 4  # razon_social, rut, direccion, organismo_admin
    keys_missing = {k for k, _ in s["missing"]}
    assert "telefono" in keys_missing
    assert "email" in keys_missing
    assert "razon_social" not in keys_missing


def test_company_profile_ignora_valores_basura():
    company = {"razon_social": "  ", "rut": "none", "direccion": "nan"}
    s = ds44.company_profile_status(company)
    assert s["completos"] == 0
