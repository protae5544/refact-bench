import logging

from colorama import Fore, Style, init
from datetime import datetime
from pathlib import Path

# Initialize colorama (for Windows support)
init(autoreset=True)

class CustomFormatter(logging.Formatter):
    LEVEL_LABEL = {
        logging.DEBUG:    "DEBUG",
        logging.INFO:     "INFO",
        logging.WARNING:  "WARN",
        logging.ERROR:    "ERROR",
        logging.CRITICAL: "CRIT",
    }

    LEVEL_COLOR = {
        logging.DEBUG:    Fore.CYAN,
        logging.INFO:     Fore.GREEN,
        logging.WARNING:  Fore.YELLOW,
        logging.ERROR:    Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def __init__(self, color: bool = False):
        self.color = color
        super().__init__()

    def format(self, record):
        label = self.LEVEL_LABEL.get(record.levelno)
        color = self.LEVEL_COLOR.get(record.levelno) if self.color else ""

        log_fmt = f"{color}{label}{Style.RESET_ALL}{(6 - len(label)) * ' '}| %(message)s"

        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def logger_init(verbose: bool):
    global global_logger

    global_logger.propagate = False

    global_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    logs_dir = Path("fakeide-logs")
    logs_dir.mkdir(exist_ok=True)
    year = datetime.now().year % 100
    file_handler = logging.FileHandler(f"{logs_dir}/{year}-{datetime.now().strftime('%m-%d_%H-%M-%S')}-fakeide.log")
    file_formatter = CustomFormatter(color=False)
    file_handler.setFormatter(file_formatter)
    global_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    terminal_formatter = CustomFormatter(color=True)
    console_handler.setFormatter(terminal_formatter)
    global_logger.addHandler(console_handler)

    global_logger.info("Logger initialized.")

    return global_logger

global_logger = logging.getLogger('refact-scenarios')

def task_logger(
    task_name: str,
    task_workdir: Path,
    running_only_one_task: bool = False,
):
    logger = global_logger.getChild(f"{task_name}-logger")

    formatter = CustomFormatter(color=False)
    file_handler = logging.FileHandler(task_workdir / "fakeide-task.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # We don't want to fill the console with task logs when running multiple tasks
    logger.propagate = running_only_one_task

    return logger
