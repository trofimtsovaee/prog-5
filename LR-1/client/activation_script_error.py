"""
Модуль для демонстрации кастомного импорта Python-модулей по HTTP/HTTPS.
Использует модуль requests для работы с HTTP.

Включает обработку ситуации недоступности удалённого хоста.
"""

import re
import sys
import warnings
from importlib.abc import PathEntryFinder
from importlib.util import spec_from_loader

import requests
from requests.exceptions import (
    ConnectionError,
    HTTPError,
    RequestException,
    Timeout,
)


# Флаг для защиты от рекурсивного импорта
_in_hook = False

# Таймаут HTTP-запросов (в секундах)
HTTP_TIMEOUT = 5


class RemoteHostUnavailableError(ImportError):
    """
    Исключение, выбрасываемое при недоступности удалённого хоста.
    Наследуется от ImportError, чтобы корректно интегрироваться
    с механизмом импорта Python.
    """
    pass


class URLLoader:
    """Загрузчик модуля по URL с использованием requests."""

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        """
        Загружает и выполняет исходный код модуля.
        Обрабатывает ситуации, когда хост стал недоступен
        в момент загрузки.
        """
        url = module.__spec__.origin
        try:
            response = requests.get(url, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
        except Timeout:
            raise RemoteHostUnavailableError(
                f"Превышено время ожидания ответа от {url} "
                f"(таймаут {HTTP_TIMEOUT} сек)"
            )
        except ConnectionError:
            raise RemoteHostUnavailableError(
                f"Не удалось установить соединение с {url}. "
                f"Проверьте доступность хоста."
            )
        except HTTPError as e:
            raise RemoteHostUnavailableError(
                f"Сервер {url} вернул ошибку: {e.response.status_code}"
            )
        except RequestException as e:
            raise RemoteHostUnavailableError(
                f"Ошибка при обращении к {url}: {e}"
            )

        source = response.content
        code = compile(source, url, mode="exec")
        exec(code, module.__dict__)


class URLFinder(PathEntryFinder):
    """Поисковик модулей по URL."""

    def __init__(self, url: str, available: set):
        self.url = url.rstrip('/')
        self.available = available

    def find_spec(self, fullname: str, target=None):
        if fullname in self.available:
            origin = f"{self.url}/{fullname}.py"
            loader = URLLoader()
            return spec_from_loader(fullname, loader, origin=origin)
        return None


def url_hook(path: str):
    """
    Функция-хук для sys.path_hooks.
    Перехватывает URL-пути и создаёт URLFinder.
    Обрабатывает ситуации недоступности хоста.
    """
    global _in_hook

    # Защита от рекурсии
    if _in_hook:
        raise ImportError("Рекурсивный вызов url_hook")

    if not path.startswith(("http://", "https://")):
        raise ImportError(f"Это не URL: {path}")

    _in_hook = True
    try:
        response = requests.get(path, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        data = response.text
    except Timeout:
        _in_hook = False
        warnings.warn(
            f"\n⚠️ Удалённый хост '{path}' не отвечает "
            f"(таймаут {HTTP_TIMEOUT} сек). "
            f"Модули с этого хоста будут недоступны.",
            RuntimeWarning,
        )
        raise ImportError(f"Таймаут подключения к {path}")
    except ConnectionError:
        _in_hook = False
        warnings.warn(
            f"\n⚠️ Не удалось подключиться к '{path}'. "
            f"Хост недоступен или отсутствует сетевое соединение. "
            f"Модули с этого хоста будут недоступны.",
            RuntimeWarning,
        )
        raise ImportError(f"Нет соединения с {path}")
    except HTTPError as e:
        _in_hook = False
        warnings.warn(
            f"\n⚠️ Хост '{path}' вернул HTTP-ошибку: "
            f"{e.response.status_code}. "
            f"Модули с этого хоста будут недоступны.",
            RuntimeWarning,
        )
        raise ImportError(f"HTTP-ошибка от {path}: {e.response.status_code}")
    except RequestException as e:
        _in_hook = False
        warnings.warn(
            f"\n⚠️ Ошибка при обращении к '{path}': {e}. "
            f"Модули с этого хоста будут недоступны.",
            RuntimeWarning,
        )
        raise ImportError(f"Ошибка запроса к {path}: {e}")
    finally:
        _in_hook = False

    filenames = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*\.py", data)
    modnames = {name[:-3] for name in filenames}

    return URLFinder(path, modnames)


if __name__ == "__main__":
    sys.path_hooks.insert(0, url_hook)
    sys.path_importer_cache.clear()

    # Попробуем импортировать с недоступного хоста для демонстрации
    unavailable_url = "http://nonexistent-host-12345.com/"
    sys.path.insert(0, "https://trofimtsovaee.github.io/python-remote-import/")

    try:
        import myremotemodule
        myremotemodule.myfoo()
    except RemoteHostUnavailableError as e:
        print(f"\n❌ Ошибка удалённого хоста: {e}")
    except ModuleNotFoundError as e:
        print(f"\n❌ Модуль не найден: {e}")
        print("Возможно, хост недоступен или модуль отсутствует.")