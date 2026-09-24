"""Quick read-only health check, used by 'Start with Windows'.

Runs a handful of fast checks at sign-in and reports only problems worth the
user's attention. It never changes anything; fixes still go through a normal
troubleshooting session with approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.diagnostic_engine import DiagnosticEngine
from app.core.logging_setup import get_logger
from app.core.models import Category, Level
from app.knowledge import troubleshooting

logger = get_logger(__name__)

HEALTH_TOOLS = [
    "get_memory_usage",
    "get_disk_free_space",
    "get_pending_reboot",
    "get_important_services",
    "get_windows_update_status",
    "test_internet",
]


@dataclass
class HealthReport:
    level: Level
    headline: str
    findings: list[str] = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        return self.level in (Level.CAUTION, Level.CRITICAL)


def run_health_check(engine: DiagnosticEngine | None = None) -> HealthReport:
    engine = engine or DiagnosticEngine()
    tools = [t for t in HEALTH_TOOLS if engine.registry.has(t)]
    results = engine.run(tools)
    diagnosis = troubleshooting.analyze(Category.UNKNOWN, results)
    findings = [c.cause for c in diagnosis.possible_causes
                if c.level in (Level.CAUTION, Level.CRITICAL)][:3]
    logger.info("health check finished", extra={"component": "health",
                                                "event": diagnosis.level.value,
                                                "status": str(len(findings))})
    return HealthReport(level=diagnosis.level, headline=diagnosis.headline, findings=findings)
