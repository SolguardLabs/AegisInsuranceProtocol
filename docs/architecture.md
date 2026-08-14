# Arquitectura

## Vista de componentes

```mermaid
flowchart TB
    subgraph ON["Plano on-chain"]
        CORE["AegisInsuranceProtocol.vy"]
        POOLS["Pool ledger"]
        POLICIES["Policy ledger"]
        CLAIMS["Claim ledger"]
        EVENTS["Events + epoch snapshots"]
        CORE --> POOLS
        CORE --> POLICIES
        CORE --> CLAIMS
        CORE --> EVENTS
    end

    subgraph OFF["Plano de servicios"]
        INDEXER["Indexer"]
        PRICE["PremiumEngine"]
        REVIEW["ClaimReviewBook"]
        CAPITAL["CapitalModel"]
        MONITOR["ExposureMonitor"]
        REPORT["ReportBuilder"]
        INDEXER --> PRICE
        INDEXER --> REVIEW
        INDEXER --> CAPITAL
        INDEXER --> MONITOR
        MONITOR --> REPORT
    end

    EVENTS --> INDEXER
    PRICE --> BROKER["Broker / policy API"]
    REVIEW --> REVIEWER["Reviewer service"]
    CAPITAL --> RISK["Risk committee"]
    MONITOR --> ALERTS["Alert manager"]
```

## Contrato Vyper

`AegisInsuranceProtocol.vy` concentra las transiciones que afectan a valor:

- alta y límites de pools;
- depósitos y retiradas de capital;
- catálogo de productos;
- compra y expiración de pólizas;
- transferencias de exposición;
- claims, decisiones y pagos;
- roles, pausa y snapshots.

El runtime se compila con optimización por tamaño y CI exige no superar 24.576 bytes, el límite
EIP-170. La analítica que no necesita consenso se mantiene fuera de la EVM.

## Toolkit Python

| Módulo | Responsabilidad |
| --- | --- |
| `models.py` | Objetos inmutables y validación de dominio. |
| `ledger.py` | Réplica operativa de capital, pólizas y posiciones. |
| `pricing.py` | Breakdown reproducible de prima. |
| `claims.py` | Evidencias y recomendación de revisión. |
| `capital_model.py` | Pérdida esperada, correlación y capital requerido. |
| `monitoring.py` | Reconciliación y flags por pool. |
| `reporting.py` | Exportación Markdown y CSV. |
| `scenarios.py` | Escenarios deterministas de integración. |

## Flujo de escritura

```mermaid
sequenceDiagram
    participant API as Policy API
    participant P as Pricing service
    participant C as Aegis contract
    participant I as Indexer
    participant M as Monitor

    API->>P: quote(product, pool, coverage, term)
    P-->>API: premium breakdown
    API->>C: buy_policy(value = premium)
    C->>C: validate capacity and lock exposure
    C-->>I: PolicyIssued
    I->>M: normalized pool + policy state
    M->>M: reconcile allocations
    M-->>API: snapshot / flags
```

## Consistencia

Los consumidores deben ordenar eventos por `(blockNumber, transactionIndex, logIndex)`, aplicar
reorganizaciones antes de publicar snapshots y releer estado del contrato en cada checkpoint. Un
evento no sustituye una lectura finalizada del storage.
