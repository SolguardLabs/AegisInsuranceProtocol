# Integración

## Instalación

```bash
python -m pip install -e ".[dev]"
```

La versión soportada es Python 3.13+ con Vyper 0.4.3 y titanoboa 0.2.8.

## Compilación del contrato

```bash
python -m vyper -f abi src/AegisInsuranceProtocol.vy
python scripts/check_contract_size.py
```

El segundo comando imprime tamaño y headroom EIP-170. Una compilación que solo emite ABI no
prueba que el runtime sea desplegable.

## Pricing

```python
from aegis_protocol import PremiumEngine
from aegis_protocol.pricing import make_pricing_input

pricing_input = make_pricing_input(
    product=product,
    pool=pool_state,
    pool_config=pool_config,
    coverage=250 * 10**18,
    duration_days=90,
    risk_score_bps=1_200,
)
quote = PremiumEngine().quote(pricing_input)
```

Persiste el breakdown, inputs, timestamp y hash de configuración. No uses floats para importes o
basis points.

## Capital

```python
from aegis_protocol import CapitalModel, DEFAULT_CAPITAL_STRESS

assessment = CapitalModel().assess(
    available_capital=capital,
    exposures=exposure_cells,
    scenario=DEFAULT_CAPITAL_STRESS,
)
```

Campos principales:

- `gross_exposure`;
- `expected_loss`;
- `correlated_loss`;
- `stressed_loss`;
- `required_capital`;
- `capital_after_stress`;
- `shortfall`;
- `coverage_ratio_bps`.

## Monitor

```python
from aegis_protocol import ExposureMonitor, MonitoringLimits

snapshot = ExposureMonitor().evaluate(
    generated_at=block_timestamp,
    pools=pool_states,
    policies=policy_snapshots,
    claims=open_claims,
    claim_allocations=allocations_by_claim,
    limits=MonitoringLimits(),
)

if not snapshot.healthy:
    alert(snapshot.flags)
```

## Serialización

Los enteros de capital pueden exceder el rango seguro de JavaScript. En JSON usa strings
decimales:

```json
{
  "pool_id": 1,
  "total_capital": "1500000000000000000000",
  "utilization_bps": 6400
}
```

## Idempotencia

Una integración debe indexar cada transición con:

```text
chainId:blockNumber:transactionHash:logIndex
```

Los jobs de escritura deben incorporar un request id persistente y verificar estado antes de
reintentar. El contrato no almacena claves idempotentes de aplicación.

## Errores

Clasifica los reverts en:

- autorización (`owner only`, `router only`, `reviewer only`, `keeper only`);
- estado (`paused`, `policy inactive`, `claim state`);
- límites (`capacity exceeded`, `retention policy`, `capital floor`);
- fondos (`value required`, `shares low`, `pool capital low`);
- datos (`pool missing`, `duration invalid`, `approval invalid`).

No reintentes automáticamente errores deterministas de estado o límites.
