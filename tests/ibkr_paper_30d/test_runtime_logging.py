from __future__ import annotations

import logging

from ibkr_paper_30d.runtime_logging import configure_runtime_dependency_logging


def test_broker_dependency_logging_does_not_reach_blocking_root_handler() -> None:
    reached_root: list[logging.LogRecord] = []

    class BlockingRootHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            reached_root.append(record)
            raise AssertionError("broker dependency log reached inherited root handler")

    root = logging.getLogger()
    handler = BlockingRootHandler()
    root.addHandler(handler)
    dependency = logging.getLogger("ib_insync")
    original_handlers = list(dependency.handlers)
    original_propagate = dependency.propagate
    try:
        configure_runtime_dependency_logging()
        dependency.error("simulated broker callback diagnostic")
        assert reached_root == []
        assert dependency.propagate is False
        assert any(isinstance(item, logging.NullHandler) for item in dependency.handlers)
    finally:
        dependency.handlers[:] = original_handlers
        dependency.propagate = original_propagate
        root.removeHandler(handler)
