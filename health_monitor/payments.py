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


# Dos planes (B2C). Los de obra social no pagan: lo cubre el prestador.
#   - app: la persona charla desde la app (entra con su código de 6 dígitos).
#   - telefono: la llamamos por teléfono y charla por ahí (usa la línea, sale más).
PLANES: dict[str, Plan] = {
    "app": Plan("app", "Plan App — charla desde la app", 10000, "ARS"),
    "telefono": Plan("telefono", "Plan Teléfono — la llamamos", 20000, "ARS"),
}
PLAN_DEFAULT = PLANES["app"]


def url_checkout(plan: Plan) -> str:
    """Link de Mercado Pago para ese plan (cada plan tiene su propio precio/link)."""
    s = get_settings()
    if plan.id == "telefono":
        return s.mercadopago_suscripcion_url_telefono or s.mercadopago_suscripcion_url
    return s.mercadopago_suscripcion_url


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
        s = get_settings()
        return bool(s.mercadopago_suscripcion_url or s.mercadopago_access_token)

    def crear_checkout(self, usuario, plan: Plan) -> dict:
        s = get_settings()
        # Modo sin código: link de plan de suscripción de Mercado Pago (uno por plan).
        url = url_checkout(plan)
        if url:
            return {
                "status": "ok",
                "detail": "Te llevamos al pago seguro de Mercado Pago.",
                "checkout_url": url,
                "plan_id": plan.id,
            }
        if not s.mercadopago_access_token:
            return {
                "status": "no_disponible",
                "detail": ("Los pagos todavía no están configurados. Cuando se cargue el "
                           "link o las credenciales de Mercado Pago, este botón cobra."),
            }
        # 🔑 Integración avanzada (API): crear la preferencia/preapproval y devolver
        # su init_point. Requiere el SDK + el access token + webhook de confirmación.
        return {
            "status": "pendiente",
            "detail": "Integración avanzada de Mercado Pago pendiente.",
            "checkout_url": "",
        }


def get_provider() -> PaymentProvider:
    """Pasarela activa (hoy Mercado Pago; agnóstico para cambiarla)."""
    return MercadoPagoProvider()
