from __future__ import annotations

import json
import logging
import sys
from typing import Any

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Formatter que emite registros de log em JSON, prontos para o Loki."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["stack"] = self.formatException(record.exc_info)

        # Campos extras passados via logger.info(msg, extra={...})
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "getMessage",
                "exc_info",
                "exc_text",
                "stack_info",
                "created",
            ):
                payload[key] = value

        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", json_output: bool = False) -> None:
    global _CONFIGURED

    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)

    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )

    root = logging.getLogger()
    root.setLevel(level.upper())
    root.addHandler(handler)

    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
