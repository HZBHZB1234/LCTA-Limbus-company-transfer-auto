import requests
from . import LogManager
def function_llc_main(modal_id, logger_: LogManager):
    logger_.log_modal_process("成功链接后端", modal_id)