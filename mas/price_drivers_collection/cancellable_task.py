# mas/price_drivers_collection/cancellable_task.py
"""
CancellableTask — обёртка для задач с поддержкой мягкой отмены.

Проблема: future.cancel() в ThreadPoolExecutor не останавливает
уже запущенный поток — он продолжает работу до завершения.

Решение: флаг отмены (_cancel_event), который агент/задача
может проверять периодически. Для LLM-вызовов (блокирующих)
используем отдельный поток с join(timeout) и daemon=True.

Известное ограничение:
    При таймауте daemon-поток продолжает выполнение LLM HTTP-запроса в фоне.
    Python не поддерживает принудительное завершение потоков.
    В скрипте (короткоживущий процесс) — безопасно: daemon=True гарантирует
    завершение потока при выходе из процесса.
    В долгоживущем сервисе (API) — потоки накапливаются, утечка ресурсов.

TODO [P2 / API-layer]: Решить проблему зависших daemon-потоков при таймауте LLM.

    Проблема:
        При таймауте CancellableTask.run() возвращает TimeoutError,
        но daemon-поток продолжает выполнение LLM HTTP-запроса в фоне.
        В скрипте (прототип) — безопасно: daemon=True, процесс короткоживущий.
        В долгоживущем сервисе (API) — потоки накапливаются, утечка ресурсов.
        Мониторинг: get_active_tasks_count() показывает количество зависших потоков.

    Решение (при переходе к API-слою):
        Вариант A (рекомендуется): перейти на asyncio.wait_for() + acall().
            LLMAdapter.acall() уже реализован.
            pipeline.py нужно перевести на async (_process_sequential → async for).
            CancellableTask становится не нужен — удалить.
        Вариант B (промежуточный): добавить Semaphore на количество
            одновременных LLM-вызовов. Ограничивает накопление потоков.
            Риск: Semaphore + rate_limit_delay могут конфликтовать.

    Затронутые файлы при реализации:
        - mas/price_drivers_collection/cancellable_task.py (удалить или переписать)
        - mas/price_drivers_collection/pipeline.py
          (_call_agent_with_timeout → async, _process_sequential → async)
        - agents/core/llm/adapter.py (acall() уже готов)
        - agents/core/base_agent.py (execute_async() уже готов)
"""
import logging
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── Счётчик активных зависших потоков ────────────────────────────
#
# Инкрементируется при старте потока, декрементируется при его завершении.
# При таймауте поток продолжает работу — счётчик остаётся > 0 до завершения потока.
# Используется для мониторинга накопления зависших потоков в долгоживущих процессах.
# Потокобезопасен.
#
_active_tasks_lock = threading.Lock()
_active_tasks_count: int = 0


def get_active_tasks_count() -> int:
    """
    Возвращает количество активных daemon-потоков CancellableTask.

    В норме — 0 (все потоки завершились).
    Значение > 0 означает что есть потоки которые:
        a) ещё выполняются в рамках таймаута, или
        b) зависли после таймаута (продолжают LLM HTTP-запрос в фоне)

    Используется для мониторинга утечки потоков в долгоживущих сервисах.
    В скрипте (прототип) — значение не критично: daemon=True гарантирует
    завершение при выходе из процесса.

    Returns:
        Текущее количество активных потоков CancellableTask.
    """
    with _active_tasks_lock:
        return _active_tasks_count


class CancellableTask:
    """
    Запускает callable в daemon-потоке с ограничением по времени.

    Отличие от ThreadPoolExecutor + future.cancel():
        - поток помечен daemon=True → не блокирует завершение процесса
        - join(timeout) корректно ждёт завершения или истечения таймаута
        - результат/исключение передаются через threading.Event + атрибуты

    Ограничение:
        При таймауте поток продолжает работу в фоне (Python не поддерживает
        принудительное завершение потоков). Счётчик get_active_tasks_count()
        позволяет отслеживать накопление зависших потоков.

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
        global _active_tasks_count
        try:
            self._result = self._fn(*self._args, **self._kwargs)
        except BaseException as e:
            self._exception = e
        finally:
            self._done_event.set()
            # Декрементируем счётчик при завершении потока.
            # Вызывается всегда: и при нормальном завершении, и при таймауте
            # (поток продолжает работу и завершится позже).
            with _active_tasks_lock:
                _active_tasks_count -= 1
            logger.debug(
                "CancellableTask: поток завершён, активных потоков: %d",
                get_active_tasks_count(),
            )

    def run(self, timeout_seconds: float) -> Any:
        """
        Запускает задачу и ждёт результат не дольше timeout_seconds.

        Returns:
            Результат fn() если завершилась вовремя.

        Raises:
            TimeoutError: если задача не завершилась за timeout_seconds.
            Exception: если задача завершилась с исключением.
        """
        global _active_tasks_count

        # Инкрементируем счётчик перед стартом потока
        with _active_tasks_lock:
            _active_tasks_count += 1

        thread = threading.Thread(target=self._target, daemon=True)
        thread.start()

        logger.debug(
            "CancellableTask: поток запущен, активных потоков: %d",
            get_active_tasks_count(),
        )

        finished = self._done_event.wait(timeout=timeout_seconds)

        if not finished:
            # Поток продолжает работу в фоне (daemon → не блокирует процесс).
            # Счётчик будет декрементирован когда поток завершится самостоятельно.
            # Python не поддерживает принудительное завершение потоков.
            logger.warning(
                "CancellableTask: таймаут %.1fs истёк, поток продолжает в фоне (daemon). "
                "Активных зависших потоков: %d. "
                "При большом значении счётчика — см. TODO в cancellable_task.py.",
                timeout_seconds,
                get_active_tasks_count(),
            )
            raise TimeoutError(
                f"Задача не завершилась за {timeout_seconds}с. "
                f"Проверьте доступность LLM API или увеличьте PIPELINE_CALL_TIMEOUT."
            )

        if self._exception is not None:
            raise self._exception

        return self._result