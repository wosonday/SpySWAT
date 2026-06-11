import logging
from pathlib import Path

class Logger:
    _initialized = False


    @classmethod
    def init(
        cls,
        log_dir: str = "logs",
        log_file: str = "log.log",
        level: int = logging.INFO,
    ):
        if cls._initialized:
            return

        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)
        log_path = log_path / log_file

        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)

        formatter = logging.Formatter(fmt)
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

        cls._initialized = True

    @classmethod
    def get_logger(cls, name: str = None) -> logging.Logger:
        if name is None:
            return logging.getLogger()
        return logging.getLogger(name)