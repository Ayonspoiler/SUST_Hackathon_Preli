import logging
import sys


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    # Suppress noisy library logs
    for lib in ("httpx", "httpcore", "google_genai", "google.genai"):
        logging.getLogger(lib).setLevel(logging.WARNING)
