# Producto: app, pagos y onboarding (obra social / privado)

Addendum de arquitectura para la nueva dirección: que esto sea una **app**, con
**login + gestión de pagos**, y dos formas de entrar: **vinculado a la cartilla de la
obra social/prepaga** o **por privado**. Decisiones presumidas con defaults sensatos
(ajustables); lo que necesita credenciales/acuerdos externos está marcado 🔑.

## 1. "Que sea una app"
- **Default: PWA primero.** La web actual se vuelve **instalable** (manifest + service
  worker + íconos), funciona en el celular como app, sin fricción de tiendas. Es el
  camino rápido y reutiliza todo lo hecho.
- **Nativa (React Native/Capacitor): más adelante**, si se necesita push nativo,
  biometría, etc. Es una decisión 🔑 (esfuerzo grande); la PWA cubre el 90% ya.

## 2. Login + gestión de pagos
- Login ya existe (JWT). Falta el **módulo de suscripción/pagos**.
- **Default de pasarela (Argentina): Mercado Pago**, con una **interfaz de pagos
  agnóstica** (`PaymentProvider`) para poder enchufar Stripe u otra. 🔑 Necesita tus
  credenciales de Mercado Pago + webhook de confirmación.
- **Planes:** trial (ya está) → privado mensual; para obra social, la cobertura la
  paga el prestador (ver abajo), no el usuario final.
- **Estado de suscripción** ya gobernado por `Usuario.plan` / `suscripcion_vence` y
  `require_active_subscription`. El pago solo actualiza ese estado.

## 3. Dos formas de entrar
- **Privado (B2C):** registro normal + suscripción paga (Mercado Pago). Es el flujo actual + pagos.
- **Obra social / prepaga (B2B2C):** el usuario elige su obra social y carga su
  **número de afiliado**; el sistema **valida contra la cartilla** del prestador y, si
  es afiliado activo, la cobertura corre por cuenta del prestador (sin pago privado).
  - **Validación de cartilla:** interfaz `validar_afiliacion(obra_social, nro_afiliado)`.
    Hoy valida formato; la **integración real por prestador** (cada obra social expone
    su API distinta, o se sube un padrón) es 🔑 (acuerdo + credenciales por prestador).
  - El número de afiliado es PII → se guarda **cifrado**.

## Modelo de cuenta (`Usuario`)
- `tipo_cuenta`: `privado | obra_social`
- `obra_social`: nombre del prestador (si aplica)
- `nro_afiliado_enc`: número de afiliado **cifrado** (si aplica)
- `afiliacion_validada`: bool (resultado de la validación de cartilla)

## Orden sugerido de construcción
1. ✅ Cimiento de cuenta: tipo (privado/obra social) + afiliación en el registro.
2. [ ] Onboarding en la UI: elegir "Mi obra social" vs "Cuenta privada".
3. [ ] PWA: manifest + service worker + íconos (instalable).
4. [ ] Módulo de pagos: interfaz `PaymentProvider` + Mercado Pago + pantalla "Mi
   suscripción" + webhook. 🔑
5. [ ] Integración real de cartillas por prestador. 🔑

## Pendientes de decisión / externos
- 🔑 Pasarela de pago y credenciales (default propuesto: Mercado Pago).
- 🔑 Con qué obra social/prepaga se arranca y cómo valida (API o padrón).
- 🔑 PWA ahora vs app nativa después (default: PWA ahora).
