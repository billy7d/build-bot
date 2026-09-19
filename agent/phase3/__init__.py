"""Trading Agent Phase 3: live shadow bridge và forward evidence."""

from .bundle import ShadowBundle, freeze_bundle, validate_bundle
from .config import Phase3Config
from .forward import ForwardRuntimeConfig, PersistentForwardCollector
from .runtime import Phase3Runtime
from .mt5_watchdog import MT5InstanceSpec, WatchdogConfig, WatchdogSafetyError

__all__ = [
    "ForwardRuntimeConfig",
    "PersistentForwardCollector",
    "Phase3Config",
    "Phase3Runtime",
    "MT5InstanceSpec",
    "WatchdogConfig",
    "WatchdogSafetyError",
    "ShadowBundle",
    "freeze_bundle",
    "validate_bundle",
]
