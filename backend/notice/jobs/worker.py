"""Run: python -m notice.jobs.worker"""

import logging
import time

from .queue import run_one


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log = logging.getLogger("notice.worker")
    log.info("worker started")
    while True:
        try:
            if not run_one():
                time.sleep(1.0)
        except Exception:  # noqa: BLE001
            log.exception("worker loop error")
            time.sleep(5)


if __name__ == "__main__":
    main()
