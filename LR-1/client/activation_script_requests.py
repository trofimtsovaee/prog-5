"""
Модуль для демонстрации кастомного импорта Python-модулей по HTTP/HTTPS.

Использует механизмы importlib (sys.path_hooks, PathEntryFinder, Loader)
для перехвата запросов на импорт, скачивания исходного кода с удаленного
веб-сервера и его динамического выполнения.

В данной версии используется модуль requests вместо urllib.request.
"""

import re
import sys
from importlib.abc import PathEntryFinder
from importlib.util import spec_from_loader

import requests
from requests.exceptions import RequestException

# Флаг для защиты от рекурсивного импорта
_in_hook = False

class URLLoader:
    """
    Кастомный загрузчик (Loader), который скачивает исходный код модуля
    по URL и выполняет его в пространстве имён целевого модуля.
    """

    def create_module(self, spec):
        """
        Возвращает объект модуля.
        Возврат None указывает интерпретатору использовать стандартную
        семантику создания модуля.
        """
        return None

    def exec_module(self, module):
        """
        Загружает и выполняет исходный код модуля.

        :param module: Объект модуля, созданный интерпретатором.
        """
        # Скачиваем исходный код по URL, сохраненному в spec.origin
        response = requests.get(module.__spec__.origin)
        response.raise_for_status()  # Выбросит HTTPError при статусе 4xx/5xx

        # requests.content возвращает байты — то, что нужно для compile()
        source = response.content

        # Компилируем исходный код в байт-код
        code = compile(source, module.__spec__.origin, mode="exec")

        # Выполняем код в пространстве имён модуля
        # (Внимание: exec небезопасен для кода из ненадежных источников)
        exec(code, module.__dict__)


class URLFinder(PathEntryFinder):
    """
    Поисковик (Finder), который проверяет, запрашивается ли модуль,
    доступный по заданному URL-адресу.
    """

    def __init__(self, url: str, available: set):
        """
        :param url: Базовый URL-адрес репозитория (без завершающего слэша).
        :param available: Множество имен доступных модулей (без расширения .py).
        """
        self.url = url.rstrip('/')  # Избегаем двойных слешей при формировании пути
        self.available = available

    def find_spec(self, fullname: str, target=None):
        """
        Ищет спецификацию модуля по его полному имени.

        :param fullname: Полное имя импортируемого модуля.
        :param target: Целевой модуль (используется при перезагрузке).
        :return: Объект ModuleSpec или None, если модуль не найден.
        """
        if fullname in self.available:
            origin = f"{self.url}/{fullname}.py"
            loader = URLLoader()
            return spec_from_loader(fullname, loader, origin=origin)

        return None


def url_hook(path: str):
    """
    Функция-хук для sys.path_hooks.

    Перехватывает пути, начинающиеся с http:// или https://, скачивает
    HTML-страницу со списком файлов (directory listing), парсит её и
    создает экземпляр URLFinder.

    :param path: Путь из sys.path, который проверяет интерпретатор.
    :return: Экземпляр URLFinder.
    :raises ImportError: Если путь не является URL или сервер недоступен.
    """
    global _in_hook

    # Защита от рекурсии: если мы уже внутри хука,
    # значит, это служебный импорт (например, netrc внутри requests).
    # Сразу отдаём управление стандартным механизмам.
    if _in_hook:
        raise ImportError("Рекурсивный вызов url_hook — пропускаем")

    if not path.startswith(("http://", "https://")):
        raise ImportError(f"Это не URL: {path}")

    _in_hook = True

    try:
        # requests.get() возвращает объект Response
        response = requests.get(path)
        # raise_for_status() выбросит HTTPError при 4xx/5xx
        response.raise_for_status()
        # response.text автоматически декодирует байты в строку
        data = response.text
    except RequestException as e:
        raise ImportError(f"Не удалось получить доступ к {path}: {e}")
    finally:
        _in_hook = False

    # Ищем имена файлов, соответствующие правилам именования модулей Python
    filenames = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*\.py", data)

    # Преобразуем список файлов в множество имен модулей (убираем '.py')
    modnames = {name[:-3] for name in filenames}

    return URLFinder(path, modnames)


if __name__ == "__main__":
    # 1. Регистрируем хук в начале списка для наивысшего приоритета проверки
    sys.path_hooks.insert(0, url_hook)

    # 2. Очищаем кэш импортеров, чтобы Python заново проверил все пути
    sys.path_importer_cache.clear()

    # 3. Добавляем целевой URL в начало списка путей поиска модулей
    # (можно использовать как локальный сервер, так и внешний хостинг)
    sys.path.insert(0, "https://trofimtsovaee.github.io/python-remote-import/")

    print("Зарегистрированные path_hooks:", sys.path_hooks)

    # 4. Проверка работы кастомного импорта
    import myremotemodule
    myremotemodule.myfoo()