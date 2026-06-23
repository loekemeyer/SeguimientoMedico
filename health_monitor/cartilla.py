"""Validación de afiliación contra la cartilla de la obra social / prepaga.

Punto de integración B2B2C: cada obra social expone su validación de forma distinta
(API propia, o un padrón que se sube). Esta es la interfaz; la integración real por
prestador se enchufa acá sin tocar el resto del sistema.

Hoy valida FORMATO (presencia de obra social + número de afiliado con dígitos
suficientes). No confirma que el afiliado exista realmente: eso requiere el acuerdo
y las credenciales de cada prestador.
"""
from __future__ import annotations

import re

# Prestadores ofrecidos en el onboarding. CEMIC es el principal (primero en la lista).
OBRAS_SOCIALES = ["CEMIC", "OSDE", "Swiss Medical", "Galeno", "Medifé", "Otra"]


def validar_afiliacion(obra_social: str, nro_afiliado: str) -> bool:
    """¿La afiliación es válida? Por ahora chequea formato; la integración real va acá."""
    digitos = re.sub(r"\D", "", nro_afiliado or "")
    return bool((obra_social or "").strip()) and len(digitos) >= 5
