"""Pagos / suscripción: interfaz agnóstica de pasarela (Mercado Pago por default).

La integración real (crear preferencia + webhook de confirmación) necesita las
credenciales de Mercado Pago. Sin ellas, el proveedor responde "no disponible" y la
app sigue funcionando: el estado de la suscripción ya vive en `Usuario.plan` /
`suscripcion_vence`. Para enchufar Stripe u otra pasarela, basta otra subclase.
"""
from __future__ import annotations

from dataclasses import dataclass

from shared.config import get_settings


@dataclass(frozen=True)
class Plan:
    id: str
    nombre: str
    precio: int        # por mes
    moneda: str = "ARS"


# Plan privado (B2C). Los de obra social no pagan: lo cubre el prestador.
PLANES: dict[str, Plan] = {
    "privado_mensual": Plan("privado_mensual", "Plan privado — mensual", 9900, "ARS"),
}
PLAN_DEFAULT = PLANES["privado_mensual"]


class PaymentProvider:
    """Interfaz de pasarela de pago."""

    nombre = "base"

    def configurado(self) -> bool:
        raise NotImplementedError

    def crear_checkout(self, usuario, plan: Plan) -> dict:
        """Devuelve {status, detail, checkout_url?}. No lanza: degrada con elegancia."""
        raise NotImplementedError


class MercadoPagoProvider(PaymentProvider):
    nombre = "mercadopago"

    def configurado(self) -> bool:
        return bool(get_settings().mercadopago_access_token)

    def crear_checkout(self, usuario, plan: Plan) -> dict:
        if not self.configurado():
            return {
                "status": "no_disponible",
                "detail": ("Los pagos todavía no están configurados. Cuando se carguen "
                           "las credenciales de Mercado Pago, este botón te lleva al checkout."),
            }
        # 🔑 Punto de integración: crear la preferencia en Mercado Pago y devolver
        # su init_point como checkout_url. Requiere el SDK + el access token.
        return {
            "status": "pendiente",
            "detail": "Integración de Mercado Pago pendiente de implementar.",
            "checkout_url": "",
        }


def get_provider() -> PaymentProvider:
    """Pasarela activa (hoy Mercado Pago; agnóstico para cambiarla)."""
    return MercadoPagoProvider()
