# Security Policy

## Modelo De Seguridad

AegisInsuranceProtocol modela un mercado de cobertura con capital aportado por underwriters.
El contrato principal debe preservar estas propiedades:

- el capital bloqueado por polizas no debe retirarse mientras respalde obligaciones activas;
- las primas deben registrarse antes de emitir la poliza;
- una poliza solo puede reclamar dentro de su ventana valida;
- los claims requieren un incidente activo y una revision autorizada;
- el pago de claims debe reducir capital y exposicion de los pools participantes;
- las retiradas solo pueden ejecutarse contra capital libre;
- los roles operativos deben quedar separados entre router, reviewer y keeper.

## Alcance

El alcance de revision incluye:

- `src/AegisInsuranceProtocol.vy`;
- el paquete `src/aegis_protocol/`;
- pruebas en `tests/`;
- scripts de CI y validacion local.

Quedan fuera de alcance:

- integraciones con oraculos reales;
- bridges externos;
- tokens ERC-20 de produccion;
- interfaces web o dashboards;
- despliegues en redes publicas.

## Validaciones Automatizadas

La validacion local esperada es:

```bash
bash scripts/ci.sh
```

El script compila el contrato Vyper, ejecuta pruebas Python, compila los modulos auxiliares y
verifica que `src/` permanezca dentro del rango de LOC del proyecto.

## Gestion De Dependencias

Las dependencias estan declaradas en `pyproject.toml` y se instalan con:

```bash
python -m pip install -e ".[dev]"
```

Dependabot revisa dependencias `pip` y GitHub Actions semanalmente.

## Reporte Interno

Los reportes deben incluir:

- descripcion del comportamiento observado;
- impacto economico;
- pasos de reproduccion;
- contratos o modulos afectados;
- prueba o script minimo;
- mitigacion propuesta.

No incluya claves privadas, endpoints de produccion ni datos de usuarios reales en reportes,
issues o fixtures.

## Criterios De Cambios Sensibles

Un cambio requiere revision adicional si modifica:

- formulas de primas o deducibles;
- contabilidad de exposicion;
- cesiones entre pools;
- expiracion de polizas;
- asignacion o liquidacion de claims;
- permisos operativos;
- retiradas de capital.
