"""
Модуль для демонстрации кастомного импорта Python-модулей по HTTP/HTTPS.

Использует механизмы importlib (sys.path_hooks, PathEntryFinder, Loader) 
для перехвата запросов на импорт, скачивания исходного кода с локального 
веб-сервера и его динамического выполнения.
"""

import re
import sys
from urllib.request import urlopen
from importlib.abc import PathEntryFinder
from importlib.util import spec_from_loader

class URLLoader:
    """
    Кастомный загрузчик (Loader), который скачивает исходный код модуля 
    по URL и выполняет его в пространстве имён целевого модуля.
    """

    def create_module(self, spec):
        """
        Возвращает объект модуля. 
        Возврат None указывает интерпретатору использовать стандартную 
        семантику создания модуля (что нам и нужно).
        """
        return None
    
    def exec_module(self, module):
        """
        Загружает и выполняет исходный код модуля.
        
        :param module: Объект модуля, созданный интерпретатором.
        """
        # Скачиваем исходный код по URL, сохраненному в spec.origin
        with urlopen(module.__spec__.origin) as page:
            source = page.read()
        
        # Компилируем исходный код в байт-код
        code = compile(source, module.__spec__.origin, mode="exec")
        
        # Выполняем код в пространстве имён модуля
        exec(code, module.__dict__)

# В URLFinder и будет срабатывать функция url_hook, которая и будет перехватывать ситуацию, в которой загрузка модуля 
# должна идти по URL-адресу
class URLFinder(PathEntryFinder):
    """
    Поисковик (Finder), который проверяет, запрашивается ли модуль, 
    доступный по заданному URL-адресу.
    """

    def __init__(self, url, available):
        """
        :param url: Базовый URL-адрес репозитория (без завершающего слэша).
        :param available: Множество имен доступных модулей (без расширения .py).
        """
        self.url = url.rstrip('/') # Избегаем двойных слешей при формировании пути
        self.available = available
        
    def find_spec(self, name, target=None):
        """
        Ищет спецификацию модуля по его полному имени.
        
        :param name: Полное имя импортируемого модуля (например, 'myremotemodule').
        :param target: Целевой модуль (используется при перезагрузке, здесь не нужен).
        :return: Объект ModuleSpec или None, если модуль не найден.
        """
        if name in self.available:
            origin = "{}/{}.py".format(self.url, name)
            loader = URLLoader()
            return spec_from_loader(name, loader, origin=origin)
        return None


def url_hook(some_str):
    """
    Функция-хук для sys.path_hooks. 
    
    Перехватывает пути, начинающиеся с http:// или https://, скачивает 
    HTML-страницу со списком файлов (directory listing), парсит её и 
    создает экземпляр URLFinder.
    
    :param path: Путь из sys.path, который проверяет интерпретатор.
    :return: Экземпляр URLFinder.
    :raises ImportError: Если путь не является URL или сервер недоступен.
    """
    if not some_str.startswith(("http://", "https://")):
        raise ImportError(f"Это не URL: {some_str}")
    try:
        with urlopen(some_str) as page: # requests.get()
            data = page.read().decode("utf-8")
    except Exception as e:
        raise ImportError(f"Не удалось получить доступ к {some_str}: {e}")
    
    # Ищем имена файлов, соответствующие правилам именования модулей Python
    filenames = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*\.py", data)
    
    # Преобразуем список файлов в множество имен модулей (убираем '.py')
    modnames = {name[:-3] for name in filenames}
    
    return URLFinder(some_str, modnames)


if __name__ == "__main__":
    # 1. Регистрируем хук в начале списка для наивысшего приоритета проверки
    sys.path_hooks.insert(0, url_hook)

    # 2. Очищаем кэш импортеров, чтобы Python заново проверил все пути
    sys.path_importer_cache.clear()

    # 3. Добавляем целевой URL в начало списка путей поиска модулей
    sys.path.insert(0, "http://localhost:8000")
    
    print("Зарегистрированные хуки:", sys.path_hooks)

    # 4. Проверка работы кастомного импорта
    # Убедитесь, что в другой консоли запущен сервер: python3 -m http.server 8000
    import myremotemodule
    myremotemodule.myfoo()

