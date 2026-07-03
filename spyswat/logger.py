"""
SpySWAT logging utilities.

Three-mode design
─────────────────
1. Main process  — Logger.init()
   Sets up FileHandler + StreamHandler on the root logger.
   Writes a session separator to the log file so runs are visually distinct.

2. Parallel mode — Logger.init_queue_listener() + Logger.init_worker()
   Avoids concurrent file writes from multiple subprocesses.

   Architecture:

       Main process                    Worker process (subprocess)
       ───────────────────────         ──────────────────────────
       queue = init_queue_listener()
       │                               Logger.init_worker(queue)
       │                                       │
       │◄──── multiprocessing.Queue ───────────┘  QueueHandler
       │
       QueueListener  (daemon thread in main process)
       │
       FileHandler + StreamHandler
       (single writer — no concurrent writes possible)

3. Stop          — Logger.stop_listener()
   Flushes remaining records and shuts down the listener thread.
   Always call in a `finally` block after ProcessPoolExecutor exits.

Typical usage in CalibrationManager.run_batch()
────────────────────────────────────────────────
    queue = Logger.init_queue_listener()
    try:
        wf.run_parallel(..., log_queue=queue)
    finally:
        Logger.stop_listener()

Typical usage in a worker function (_run_single_timed)
──────────────────────────────────────────────────────
    def _run_single_timed(worker_dir, swat_exe, params, param_path, log_queue=None):
        if log_queue is not None:
            from spyswat.logger import Logger
            Logger.init_worker(log_queue)
        ...
"""

import logging
import logging.handlers
from datetime import datetime
from pathlib import Path


class Logger:
    _initialized: bool = False
    _listener: "logging.handlers.QueueListener | None" = None
    _log_queue = None   # multiprocessing.Manager().Queue() proxy — picklable, safe for ProcessPoolExecutor
    _manager  = None    # multiprocessing.SyncManager — must be kept alive while queue is in use

    # ──────────────────────────────────────────────────────────────────
    # 1. Main-process initialisation
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def init(
        cls,
        log_dir: str = "logs",
        log_file: str = "run.log",
        level: int = logging.INFO,
    ) -> None:
        """
        Initialise main-process logging (FileHandler + StreamHandler).

        Writes a session separator to the log file so each Python session
        is visually distinct.  Safe to call multiple times — subsequent
        calls are no-ops.

        Args:
            log_dir:  Directory for the log file (created if missing).
            log_file: Log filename inside log_dir.
            level:    Logging level for both handlers (default INFO).
        """
        if cls._initialized:
            return

        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        log_path = log_path / log_file

        # ── session separator ──────────────────────────────────────────
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'=' * 60}\n")

        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        formatter = logging.Formatter(fmt)

        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)

        root = logging.getLogger()
        root.setLevel(level)
        root.addHandler(file_handler)
        root.addHandler(console_handler)

        cls._initialized = True

    # ──────────────────────────────────────────────────────────────────
    # 2. Parallel mode  (QueueHandler / QueueListener)
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def init_queue_listener(
        cls,
        log_dir: str = "logs",
        log_file: str = "run.log",
        level: int = logging.INFO,
    ):
        """
        Start a QueueListener for parallel worker processes (main process only).

        Call once before launching a ProcessPoolExecutor.  If the listener is
        already running this is a no-op and the existing queue is returned.

        How it works
        ────────────
        - Creates a multiprocessing.Queue (unbounded, size=-1).
        - Starts a QueueListener daemon thread that reads from that queue
          and writes each log record to FileHandler + StreamHandler serially.
        - Worker processes call Logger.init_worker(queue) so their log calls
          route through the queue instead of writing directly to the file.

        Returns
        ───────
        multiprocessing.Queue
            Pass this object to every worker function that should log.

        Example
        ───────
        >>> queue = Logger.init_queue_listener()
        >>> executor.submit(my_worker, ..., log_queue=queue)
        >>> Logger.stop_listener()          # in finally block
        """
        if cls._log_queue is not None:
            return cls._log_queue  # listener already running

        # Ensure main process has its own handlers
        cls.init(log_dir=log_dir, log_file=log_file, level=level)

        import multiprocessing

        log_path = Path(log_dir) / log_file
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        formatter = logging.Formatter(fmt)

        # Dedicated handlers for the listener thread (separate from main process)
        worker_file = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        worker_file.setLevel(level)
        worker_file.setFormatter(formatter)

        worker_console = logging.StreamHandler()
        worker_console.setLevel(level)
        worker_console.setFormatter(formatter)

        # Manager().Queue() returns a proxy object that is picklable and can be
        # passed to ProcessPoolExecutor workers via submit() on Windows (spawn).
        # Plain multiprocessing.Queue is NOT picklable and fails with:
        #   "Queue objects should only be shared between processes through inheritance"
        cls._manager  = multiprocessing.Manager()
        cls._log_queue = cls._manager.Queue(-1)
        cls._listener = logging.handlers.QueueListener(
            cls._log_queue,
            worker_file,
            worker_console,
            respect_handler_level=True,
        )
        cls._listener.start()
        return cls._log_queue

    @classmethod
    def init_worker(cls, queue) -> None:
        """
        Worker process: redirect ALL logging through the shared queue.

        Call this at the VERY TOP of every worker function body, before any
        logger calls.  It clears whatever handlers the subprocess may have
        inherited or created on module import, and replaces them with a
        single QueueHandler that forwards records to the main process.

        Args:
            queue: the multiprocessing.Queue returned by init_queue_listener().

        Example (inside worker function)
        ─────────────────────────────────
        >>> def _run_single_timed(worker_dir, swat_exe, params,
        ...                       param_path=None, log_queue=None):
        ...     if log_queue is not None:
        ...         from spyswat.logger import Logger
        ...         Logger.init_worker(log_queue)
        ...     # all logger.info / logger.error calls below now go through queue
        ...     logger.info("Worker started")
        """
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(logging.handlers.QueueHandler(queue))
        root.setLevel(logging.DEBUG)

    @classmethod
    def stop_listener(cls) -> None:
        """
        Stop the QueueListener after all parallel work is done.

        The listener flushes remaining records from the queue before
        terminating its daemon thread.

        Always call in a ``finally`` block so the listener shuts down even
        if an exception occurs inside the executor:

        >>> queue = Logger.init_queue_listener()
        >>> try:
        ...     run_parallel_work(queue)
        ... finally:
        ...     Logger.stop_listener()
        """
        if cls._listener is not None:
            cls._listener.stop()
            cls._listener = None
            cls._log_queue = None
        if cls._manager is not None:
            cls._manager.shutdown()
            cls._manager = None

    # ──────────────────────────────────────────────────────────────────
    # 3. Logger factory
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def get_logger(cls, name: str = None) -> logging.Logger:
        """Return a named logger (or root if name is None)."""
        return logging.getLogger(name)
