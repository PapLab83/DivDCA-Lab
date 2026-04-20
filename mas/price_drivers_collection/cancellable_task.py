# mas/price_drivers_collection/cancellable_task.py
"""
CancellableTask — обёртка для задач с поддержкой мягкой отмены.

Проблема: future.cancel() в ThreadPoolExecutor не останавливает
уже запущенный поток — он продолжает работу до завершения.

Решение: флаг отмены (_cancel_event), который агент/задача
может проверять периодически. Для LLM-вызовов (блокирующих)
используем отдельный поток с join(timeout) и daemon=True.
"""
import logging
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class CancellableTask:
    """
    Запускает callable в daemon-потоке с ограничением по времени.

    Отличие от ThreadPoolExecutor + future.cancel():
        - поток помечен daemon=True → не блокирует завершение процесса
        - join(timeout) корректно ждёт завершения или истечения таймаута
        - результат/исключение передаются через threading.Event + атрибуты

    Использование:
        task = CancellableTask(fn=agent.execute, args=(context,))
        result = task.run(timeout_seconds=30.0)
        if result is None:
            # таймаут истёк
    """

    def __init__(
        self,
        fn: Callable,
        args: tuple = (),
        kwargs: Optional[dict] = None,
    ) -> None:
        self._fn = fn
        self._args = args
        self._kwargs = kwargs or {}
        self._result: Any = None
        self._exception: Optional[BaseException] = None
        self._done_event = threading.Event()

    def _target(self) -> None:
        """Выполняется в daemon-потоке."""
        try:
            self._result = self._fn(*self._args, **self._kwargs)
        except BaseException as e:
            self._exception = e
        finally:
            self._done_event.set()

    def run(self, timeout_seconds: float) -> Any:
        """
        Запускает задачу и ждёт результат не дольше timeout_seconds.

        Returns:
            Результат fn() если завершилась вовремя.

        Raises:
            TimeoutError: если задача не завершилась за timeout_seconds.
            Exception: если задача завершилась с исключением.
        """
        thread = threading.Thread(target=self._target, daemon=True)
        thread.start()

        finished = self._done_event.wait(timeout=timeout_seconds)

        if not finished:
            # Поток продолжает работу в фоне (daemon → не блокирует процесс)
            # Логируем но не пытаемся убить — Python не поддерживает kill thread
            logger.warning(
                "CancellableTask: таймаут %.1fs истёк, поток продолжает в фоне (daemon)",
                timeout_seconds,
            )
            raise TimeoutError(
                f"Задача не завершилась за {timeout_seconds}с. "
                f"Проверьте доступность LLM API или увеличьте PIPELINE_CALL_TIMEOUT."
            )

        if self._exception is not None:
            raise self._exception

        return self._result