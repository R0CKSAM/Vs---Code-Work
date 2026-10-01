"""Bound technical log storage independently of reporting data."""
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys


def configure_logging(data_dir):
    max_bytes = int(os.environ.get('LOG_MAX_BYTES', '5242880'))
    copies = int(os.environ.get('LOG_BACKUP_COUNT', '5'))
    if not 65536 <= max_bytes <= 104857600 or not 1 <= copies <= 20:
        raise ValueError('LOG_MAX_BYTES must be 65536..104857600; LOG_BACKUP_COUNT must be 1..20.')
    directory = Path(os.environ.get('LOG_DIR') or Path(data_dir) / 'logs')
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / 'revenuelive.log', maxBytes=max_bytes,
                                  backupCount=copies, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)

    def unhandled(exc_type, value, traceback):
        logging.getLogger('revenuelive').critical('Unhandled error', exc_info=(exc_type, value, traceback))

    sys.excepthook = unhandled
