"""Tests del motor de preguntas de tratamiento según patologías."""
from health_monitor.cuidado import preguntas_de_alta


def test_hipertension_pregunta_pastilla_y_medir():
    qs = preguntas_de_alta(["Hipertensión"])
    crea = [q["crea"]["tipo"] for q in qs]
    assert any("presión" in q["pregunta"].lower() or "presion" in q["pregunta"].lower() for q in qs)
    assert "medicamento" in crea and "presion" in crea


def test_insomnio_pregunta_pastilla_para_dormir():
    qs = preguntas_de_alta(["Insomnio"])
    assert len(qs) == 1
    assert "dormir" in qs[0]["pregunta"].lower()
    assert qs[0]["crea"] == {"tipo": "medicamento", "nombre": "Pastilla para dormir"}


def test_diabetes_glucemia_y_medicacion():
    qs = preguntas_de_alta(["Diabetes"])
    tipos = {q["crea"]["tipo"] for q in qs}
    assert "glucemia" in tipos and "medicamento" in tipos


def test_dolor_texto_libre_por_pista():
    qs = preguntas_de_alta(["dolor de cadera"])
    assert any(q["crea"]["tipo"] == "ejercicio" for q in qs)


def test_no_repite_preguntas_entre_patologias():
    # Artrosis y "dolor ..." podrían sugerir lo mismo; no debe duplicar por id.
    qs = preguntas_de_alta(["Artrosis", "dolor de rodilla"])
    ids = [q["id"] for q in qs]
    assert len(ids) == len(set(ids))


def test_patologia_desconocida_no_rompe():
    assert preguntas_de_alta(["Algo raro xyz"]) == []
    assert preguntas_de_alta([]) == []
    assert preguntas_de_alta(["", "  "]) == []
