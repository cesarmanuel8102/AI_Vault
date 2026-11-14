"""Non-authoritative dependency logging isolation for the PAPER runtime."""

from __future__ import annotations

import logging


def configure_runtime_dependency_logging() -> None:
    """Keep broker-library diagnostics off inherited blocking console sinks.

    Broker state, errors, and alerts are recorded by explicit application
    events.  The dependency logger is therefore non-authoritative and must
    never be allowed to hold the runtime's root logging handler lock.
    """

    broker_logger = logging.getLogger("ib_insync")
    broker_logger.handlers.clear()
    broker_logger.addHandler(logging.NullHandler())
    broker_logger.propagate = False
