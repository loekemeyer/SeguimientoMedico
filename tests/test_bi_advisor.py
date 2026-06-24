"""Tests del asesor de rentabilidad (heurísticas puras)."""
from health_monitor.bi_advisor import recomendaciones_heuristicas


def _resumen(**kw):
    base = dict(clientes_total=3, clientes_activos=1, clientes_trial=1, margen_ars=5000)
    base.update(kw)
    return base


def test_detecta_clientes_en_perdida():
    clientes = [
        {"email": "a@x.com", "en_perdida": True, "plan_tipo": "app", "costo_periodo_usd": 0.1,
         "ultima_actividad": "2026-06-20"},
    ]
    recs = recomendaciones_heuristicas(_resumen(), clientes)
    assert any("pérdida" in r["titulo"].lower() for r in recs)
    assert any(r["prioridad"] == "alta" for r in recs)


def test_detecta_app_con_uso_intensivo():
    clientes = [
        {"email": "b@x.com", "en_perdida": False, "plan_tipo": "app", "costo_periodo_usd": 5.0,
         "ultima_actividad": "2026-06-20"},
    ]
    recs = recomendaciones_heuristicas(_resumen(), clientes)
    assert any("intensivo" in r["titulo"].lower() or "App" in r["titulo"] for r in recs)


def test_detecta_inactivos():
    clientes = [
        {"email": "c@x.com", "en_perdida": False, "plan_tipo": "telefono", "costo_periodo_usd": 0.0,
         "ultima_actividad": None},
    ]
    recs = recomendaciones_heuristicas(_resumen(), clientes)
    assert any("actividad" in r["titulo"].lower() for r in recs)


def test_negocio_en_perdida():
    recs = recomendaciones_heuristicas(_resumen(margen_ars=-1000), [])
    assert any("pérdida" in r["titulo"].lower() for r in recs)


def test_sin_focos_devuelve_todo_sano():
    recs = recomendaciones_heuristicas(_resumen(clientes_trial=0, margen_ars=10000), [])
    assert len(recs) == 1
    assert "sano" in recs[0]["titulo"].lower()
