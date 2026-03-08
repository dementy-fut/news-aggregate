# main.py
import logging
import sys

from collector import collect_all
from analyzer import analyze_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    logger.info("=== News Lens pipeline starting ===")

    # Step 1: Collect
    logger.info("--- Phase 1: Collecting RSS feeds ---")
    stats = collect_all()
    total_new = sum(stats.values())
    logger.info(f"Collection done: {total_new} new articles")

    if total_new == 0:
        logger.info("No new articles. Skipping analysis.")
        return

    # Step 2: Analyze
    logger.info("--- Phase 2: Analyzing articles ---")
    analyze_all()

    logger.info("=== Pipeline complete ===")


if __name__ == "__main__":
    main()
