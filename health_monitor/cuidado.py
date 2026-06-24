"""Preguntas inteligentes de tratamiento según las patologías cargadas.

Después del alta, en función de lo que el familiar marcó (insomnio, hipertensión,
dolor, etc.), el sistema pregunta CÓMO se trata, con lógica simple, y cada "sí"
arma un ítem de rutina (un medicamento, una automedición o un ejercicio). Así la
rutina queda completa sin que el familiar tenga que pensar qué cargar.

Es un motor de reglas PURO (sin IA, sin red): determinístico y testeable. La
clave de cada patología coincide con los valores normalizados del front
(normalizaPatologia en app.js): "Insomnio", "Hipertensión", "Diabetes", etc.
"""
from __future__ import annotations

# Cada regla: (pregunta, ítem de rutina que se crea si la respuesta es "sí").
# El "tipo" coincide con los del formulario de rutina (medicamento, presion,
# glucemia, oximetria, peso, ejercicio, ...).
_REGLAS: dict[str, list[dict]] = {
    "Insomnio": [
        {"id": "insomnio_pastilla", "pregunta": "¿Toma alguna pastilla para dormir?",
         "crea": {"tipo": "medicamento", "nombre": "Pastilla para dormir"}},
    ],
    "Hipertensión": [
        {"id": "hta_pastilla", "pregunta": "¿Toma alguna pastilla para la presión?",
         "crea": {"tipo": "medicamento", "nombre": "Pastilla para la presión"}},
        {"id": "hta_medir", "pregunta": "¿Se toma la presión en casa?",
         "crea": {"tipo": "presion", "nombre": "Tomar la presión"}},
    ],
    "Diabetes": [
        {"id": "dbt_glucemia", "pregunta": "¿Se controla la glucemia (el azúcar) en casa?",
         "crea": {"tipo": "glucemia", "nombre": "Medir la glucemia"}},
        {"id": "dbt_medicacion", "pregunta": "¿Toma pastillas o se aplica insulina para la diabetes?",
         "crea": {"tipo": "medicamento", "nombre": "Medicación para la diabetes"}},
    ],
    "Colesterol alto (dislipidemia)": [
        {"id": "col_pastilla", "pregunta": "¿Toma medicación para el colesterol?",
         "crea": {"tipo": "medicamento", "nombre": "Medicación para el colesterol"}},
    ],
    "Cardiopatía": [
        {"id": "card_medicacion", "pregunta": "¿Toma medicación del corazón?",
         "crea": {"tipo": "medicamento", "nombre": "Medicación del corazón"}},
        {"id": "card_peso", "pregunta": "¿Conviene controlarle el peso (para retención de líquidos)?",
         "crea": {"tipo": "peso", "nombre": "Pesarse"}},
    ],
    "Artrosis": [
        {"id": "artrosis_ejercicio", "pregunta": "¿Hace ejercicio o kinesiología para las articulaciones?",
         "crea": {"tipo": "ejercicio", "nombre": "Ejercicios / kinesiología"}},
        {"id": "artrosis_dolor", "pregunta": "¿Toma algo para el dolor?",
         "crea": {"tipo": "medicamento", "nombre": "Medicación para el dolor"}},
    ],
    "Artritis": [
        {"id": "artritis_ejercicio", "pregunta": "¿Hace ejercicio o kinesiología?",
         "crea": {"tipo": "ejercicio", "nombre": "Ejercicios / kinesiología"}},
        {"id": "artritis_medicacion", "pregunta": "¿Toma medicación para la artritis?",
         "crea": {"tipo": "medicamento", "nombre": "Medicación para la artritis"}},
    ],
    "Riesgo de caídas": [
        {"id": "caidas_ejercicio", "pregunta": "¿Hace ejercicios de equilibrio o fuerza?",
         "crea": {"tipo": "ejercicio", "nombre": "Ejercicios de equilibrio"}},
    ],
    "Depresión": [
        {"id": "depre_medicacion", "pregunta": "¿Toma medicación para el ánimo?",
         "crea": {"tipo": "medicamento", "nombre": "Medicación para el ánimo"}},
    ],
    "Ansiedad": [
        {"id": "ansiedad_medicacion", "pregunta": "¿Toma medicación para la ansiedad?",
         "crea": {"tipo": "medicamento", "nombre": "Medicación para la ansiedad"}},
    ],
    "EPOC": [
        {"id": "epoc_inhalador", "pregunta": "¿Usa inhaladores?",
         "crea": {"tipo": "medicamento", "nombre": "Inhalador"}},
        {"id": "epoc_saturacion", "pregunta": "¿Se controla la saturación con un oxímetro?",
         "crea": {"tipo": "oximetria", "nombre": "Medir la saturación (oxímetro)"}},
    ],
    "Asma": [
        {"id": "asma_inhalador", "pregunta": "¿Usa inhaladores?",
         "crea": {"tipo": "medicamento", "nombre": "Inhalador"}},
    ],
    "Parkinson": [
        {"id": "park_medicacion", "pregunta": "¿Toma la medicación a horario (es clave en Parkinson)?",
         "crea": {"tipo": "medicamento", "nombre": "Medicación para el Parkinson"}},
    ],
    "Deterioro cognitivo": [
        {"id": "cognitivo_medicacion", "pregunta": "¿Toma medicación para la memoria?",
         "crea": {"tipo": "medicamento", "nombre": "Medicación para la memoria"}},
    ],
    "Demencia": [
        {"id": "demencia_medicacion", "pregunta": "¿Toma medicación indicada por el neurólogo?",
         "crea": {"tipo": "medicamento", "nombre": "Medicación neurológica"}},
    ],
    "Alzheimer": [
        {"id": "alzheimer_medicacion", "pregunta": "¿Toma la medicación para el Alzheimer?",
         "crea": {"tipo": "medicamento", "nombre": "Medicación para el Alzheimer"}},
    ],
    "Trastorno de tiroides": [
        {"id": "tiroides_pastilla", "pregunta": "¿Toma la pastilla de tiroides (suele ser en ayunas)?",
         "crea": {"tipo": "medicamento", "nombre": "Pastilla de tiroides"}},
    ],
    "Hipoacusia": [
        {"id": "hipoacusia_audifono", "pregunta": "¿Usa audífonos? (conviene recordarle ponérselos)",
         "crea": {"tipo": "otro", "nombre": "Ponerse los audífonos"}},
    ],
}

# Pistas por subcadena para texto libre que no quedó en una clave exacta.
_PISTAS = {
    "dolor": [{"id": "dolor_ejercicio", "pregunta": "¿Hace ejercicio o kinesiología para el dolor?",
               "crea": {"tipo": "ejercicio", "nombre": "Ejercicios / kinesiología"}},
              {"id": "dolor_medicacion", "pregunta": "¿Toma algo para el dolor?",
               "crea": {"tipo": "medicamento", "nombre": "Medicación para el dolor"}}],
    "dormir": [{"id": "dormir_pastilla", "pregunta": "¿Toma alguna pastilla para dormir?",
                "crea": {"tipo": "medicamento", "nombre": "Pastilla para dormir"}}],
}


def preguntas_de_alta(patologias: list[str]) -> list[dict]:
    """Devuelve las preguntas de tratamiento para esas patologías (sin repetir).

    Cada pregunta: {id, patologia, pregunta, crea: {tipo, nombre}}. El front las
    muestra; por cada "sí" crea el ítem de rutina indicado en ``crea``.
    """
    vistas: set[str] = set()
    out: list[dict] = []
    for pat in patologias or []:
        pat = (pat or "").strip()
        if not pat:
            continue
        reglas = _REGLAS.get(pat)
        if reglas is None:
            low = pat.lower()
            reglas = next((v for k, v in _PISTAS.items() if k in low), None)
        for regla in reglas or []:
            if regla["id"] in vistas:
                continue
            vistas.add(regla["id"])
            out.append({"patologia": pat, **regla})
    return out
