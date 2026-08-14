"""Off-chain support toolkit for AegisInsuranceProtocol.

The package mirrors operational calculations used by brokers, reviewers and
underwriting desks. The on-chain settlement contract remains the source of
truth for capital movements.
"""

from .claims import ClaimDecision, ClaimReviewBook
from .capital_model import (
    DEFAULT_CAPITAL_STRESS,
    CapitalAssessment,
    CapitalModel,
    CapitalStressScenario,
    ExposureCell,
)
from .ledger import CapitalLedger, PoolPosition
from .monitoring import (
    ExposureMonitor,
    MonitoringLimits,
    MonitoringSnapshot,
    PoolMonitoringRow,
    RiskFlag,
)
from .models import (
    ClaimRequest,
    CoverageProduct,
    IncidentSignal,
    PoolConfig,
    PolicySnapshot,
    RiskPoolState,
    UnderwriterAccount,
)
from .pricing import PremiumBreakdown, PremiumEngine
from .reporting import ExposureReport, ReportBuilder

__all__ = [
    "CapitalLedger",
    "CapitalAssessment",
    "CapitalModel",
    "CapitalStressScenario",
    "ClaimDecision",
    "ClaimRequest",
    "ClaimReviewBook",
    "CoverageProduct",
    "DEFAULT_CAPITAL_STRESS",
    "ExposureCell",
    "ExposureMonitor",
    "ExposureReport",
    "IncidentSignal",
    "MonitoringLimits",
    "MonitoringSnapshot",
    "PoolConfig",
    "PoolMonitoringRow",
    "PolicySnapshot",
    "PoolPosition",
    "PremiumBreakdown",
    "PremiumEngine",
    "ReportBuilder",
    "RiskPoolState",
    "RiskFlag",
    "UnderwriterAccount",
]
