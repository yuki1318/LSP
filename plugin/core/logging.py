# import os
# import datetime

from .typing import Any
import traceback


log_debug = True
log_exceptions = True

###########################################################################
#                               logging設定                               #
###########################################################################
from logging import getLogger, StreamHandler, Formatter, basicConfig
# from logging import getLogger, StreamHandler, FileHandler, Formatter, basicConfig

# logﾌｫﾙﾀﾞを作成
# os.makedirs('log', exist_ok=True)

CRITICAL = 50
ERROR    = 40
WARNING  = 30
INFO     = 20
DEBUG    = 10
NOTSET   = 0

LOG_LEVEL = INFO
basicConfig(level=LOG_LEVEL, format='%(asctime)s[%(processName)14s(%(process)5d) - %(threadName)10s]\t: %(message)s')

logger      = getLogger(__name__)
handler     = StreamHandler()
# filehandler = FileHandler('log/log_py_{0}.txt'.format(datetime.date.today()), encoding='shift_jis')
log_format  = Formatter('%(asctime)s[%(processName)14s(%(process)5d) - %(threadName)10s]\t: %(message)s')
handler.setFormatter(log_format)
# filehandler.setFormatter(log_format)
# getLogger('xmodem.XMODEM').addHandler(filehandler)
logger.setLevel(LOG_LEVEL)
handler.setLevel(LOG_LEVEL)
# filehandler.setLevel(LOG_LEVEL)
logger.addHandler(handler)
# logger.addHandler(filehandler)
logger.propagate = False


def set_debug_logging(logging_enabled: bool) -> None:
	global log_debug
	log_debug = logging_enabled


def set_exception_logging(logging_enabled: bool) -> None:
	global log_exceptions
	log_exceptions = logging_enabled


def debug(*args: Any) -> None:
	"""Print args to the console if the "debug" setting is True."""
	printf(*args)


def exception_log(message: str, ex: Exception) -> None:
	logger.warning(message)
	ex_traceback = ex.__traceback__
	logger.warning(''.join(traceback.format_exception(ex.__class__, ex, ex_traceback)))


def printf(*args: Any, prefix: str = 'LSP') -> None:
	"""Print args to the console, prefixed by the plugin name."""
	logger.info("{prefix} - {args}".format(prefix=prefix, args="{}".format(*args)))
