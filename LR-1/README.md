**Тема:** Реализация удаленного импорта собственного пакета

**Цель работы:** изучить механизм импорта модулей в Python и реализовать собственный загрузчик (Loader) и поисковик (Finder), позволяющий импортировать и выполнять Python-модули напрямую с удаленного HTTP-сервера, не сохраняя их локально на диске.
## Ход работы

## Часть 1. Импорт с локального http-сервера

### Подготовка серверной части

В директории `rootserver` создан файл `myremotemodule.py` с тестовой функцией `myfoo()`. 

```python
def myfoo():
	author = "trofimtsovaee"
	print(f"{author}'s module is imported")
```

Запущен локальный HTTP-сервер командой:

```bash
python3 -m http.server 8000
```

### Разработка кастомного загрузчика (`URLLoader`)

Реализован класс `URLLoader`, наследующий протокол загрузчика:
- `create_module`: возвращает `None`, делегируя создание модуля стандартной логике Python.
- `exec_module`: скачивает исходный код по URL (из `module.__spec__.origin`) с помощью `urllib.request.urlopen`, компилирует его функцией `compile` и выполняет в пространстве имен модуля через `exec`.

### Разработка поисковика (`URLFinder`)

Реализован класс `URLFinder`, наследующий `importlib.abc.PathEntryFinder`:
- Принимает базовый URL и множество доступных имен модулей.
- Метод `find_spec` проверяет, запрашивается ли модуль из этого множества. Если да, возвращает `ModuleSpec`, связывая имя модуля с экземпляром `URLLoader`.

### Реализация и регистрация хука (`url_hook`)

Создана функция `url_hook(path)`:
1. Проверяет, начинается ли путь с `http://` или `https://`. Если нет, вызывает `ImportError` (передавая управление следующему хуку).
2. Скачивает HTML-страницу по указанному пути (directory listing).
3. С помощью регулярного выражения `r"[a-zA-Z_][a-zA-Z0-9_]*\.py"` извлекает имена доступных `.py` файлов.
4. Возвращает экземпляр `URLFinder` с полученными данными.

Регистрация выполнена с учетом приоритета и актуальности кэша:

```python
sys.path_hooks.insert(0, url_hook)          # Приоритетная проверка
sys.path_importer_cache.clear()             # Сброс кэша импортеров
sys.path.insert(0, "http://localhost:8000") # Добавление пути поиска
```

#### Код `activation_script.py `

```python
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



```

### Результаты

Скрипт `activation_script.py` запущен из изолированной директории клиента (с активированным виртуальным окружением).

**Результат выполнения:**
- В консоли клиента успешно выведено сообщение: `trofimtsovaee's module is imported`.

![[Pasted image 20260930010041.png]]

- В логах сервера зафиксированы успешные HTTP-запроса (статус 200):
    - `GET /` (получение списка файлов для парсинга хуком).
    - `GET /myremotemodule.py` (загрузка исходного кода лоадером).

![[Pasted image 20260930010012.png]]



## Часть 2. Импорт с GitHub Pages

**Цель:** проверить работоспособность разработанного кастомного механизма импорта при использовании реального удаленного хостинга вместо локального сервера.

### Подготовка файлов на хостинге

В публичном репозитории были размещены два файла:

- `myremotemodule.py` — целевой модуль с функцией `myfoo()`.
- `index.html` — минимальная HTML-страница, содержащая ссылку на модуль:

```html
<a href="myremotemodule.py">myremotemodule.py</a>
```

### Модификация клиентского скрипта

Единственное изменение в `activation_script.py` — замена локального адреса на URL хостинга:

```python
sys.path.insert(0, "https://trofimtsovaee.github.io/python-remote-import/")
```

Ссылка: https://trofimtsovaee.github.io/python-remote-import/
### Результаты

Скрипт успешно:
1. Подключился к удаленному серверу по протоколу **HTTPS**.
2. Скачал и распарсил `index.html`, обнаружив доступный модуль.
3. Загрузил исходный код `myremotemodule.py` и выполнил функцию `myfoo()`.

![](Pasted%20image%2020260930022019.png)

## Часть 3. Модуль requests

Функция `url_hook` и класс `URLLoader` были переписаны с использованием стороннего модуля `requests` вместо стандартного `urllib.request`.

#### **Основные изменения:**
1. В `url_hook` метод `urlopen` заменен на `requests.get()`, что позволило использовать атрибут `.text` для автоматического декодирования ответа вместо ручного вызова `.decode("utf-8")`.
2. В `URLLoader.exec_module` для получения исходного кода в виде байтов используется `response.content` (вместо `page.read()`).
3. Добавлен вызов `response.raise_for_status()` в обоих местах для явной обработки HTTP-ошибок (4xx, 5xx).
4. Исключения `URLError` и `HTTPError` заменены на единое базовое исключение `requests.exceptions.RequestException`, что упростило блок `try/except`.

#### Ключевые изменения по сравнению с `urllib.request`:

|                      | `urllib.request`                            | `requests`                                    |
| -------------------- | ------------------------------------------- | --------------------------------------------- |
| Получение текста     | `page.read().decode("utf-8")`               | `response.text` (автодекодирование)           |
| Получение байтов     | `page.read()`                               | `response.content`                            |
| Проверка HTTP-ошибок | Нужно вручную проверять код                 | `response.raise_for_status()`                 |
| Обработка исключений | Разные исключения (`URLError`, `HTTPError`) | Одно базовое `RequestException`               |
| Контекстный менеджер | `with urlopen(...) as page:`                | Не нужен, `requests` закрывает соединение сам |

При замене `urllib.request` на `requests` возникла ошибка `RecursionError: maximum recursion depth exceeded`. Причина — особенность работы `requests`: при первом вызове он импортирует служебные модули стандартной библиотеки (например, `netrc`). Поскольку кастомный `url_hook` зарегистрирован в `sys.path_hooks` с наивысшим приоритетом, каждый такой служебный импорт снова проходил через него, вызывая новый `requests.get()` и порождая бесконечную рекурсию.

**Решение:** введена глобальная переменная-флаг `_in_hook`, которая устанавливается в `True` на время выполнения хука. При рекурсивном вызове хук немедленно выбрасывает `ImportError`, передавая управление стандартным механизмам поиска модулей. Блок `try/finally` гарантирует сброс флага даже в случае ошибки.

#### Код `activation_script_requests.py `

```python
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
```


## Часть 4. Обработка недоступности хоста

1. **Введён таймаут** `HTTP_TIMEOUT = 5` секунд для всех HTTP-запросов, что предотвращает зависание скрипта.
2. **Создано кастомное исключение** `RemoteHostUnavailableError`, наследующееся от `ImportError`, для явного обозначения проблемы недоступности хоста.
3. **Раздельная обработка типов ошибок** `requests`:
    - `Timeout` — сервер не отвечает в течение таймаута;
    - `ConnectionError` — отсутствует сетевое соединение или DNS;
    - `HTTPError` — сервер вернул код ошибки (4xx, 5xx);
    - `RequestException` — прочие ошибки библиотеки.
4. **Информирование пользователя** через модуль `warnings` — при каждой ошибке выводится понятное сообщение на русском языке с указанием проблемного URL и причины.
5. **Обработка ошибок в `URLLoader`** — если хост стал недоступен между моментом поиска модуля (`URLFinder`) и моментом его загрузки (`URLLoader`), пользователь получает корректное `RemoteHostUnavailableError`, а не «сырое» сетевое исключение.

### Тестирование и результаты

#### Тест 1: Недоступный домен (DNS-ошибка)

```python
sys.path.insert(0, "http://nonexistent-host-12345.com/")
```

![](Pasted%20image%2020261007093917.png)

#### Тест 2: Таймаут (медленный/неотвечающий сервер)

```python
sys.path.insert(0, "http://httpbin.org/delay/10")
```

![](Pasted%20image%2020261007094236.png)

#### Тест 3: HTTP-ошибка (404)

```python
sys.path.insert(0, "https://httpbin.org/status/404")
```

![](Pasted%20image%2020261007094405.png)

#### Тест 4: Рабочий хост (GitHub Pages)

```python
sys.path.insert(0, "https://trofimtsovaee.github.io/python-remote-import/")
```

![](Pasted%20image%2020261007094524.png)

**Итог:** проверены сценарии недоступного домена (DNS-ошибка), таймаута (через `httpbin.org/delay/10`), HTTP-ошибки 404, а также штатная работа с доступным хостом (GitHub Pages). Во всех случаях пользователь получает информативное сообщение о причине сбоя.

### Код `activation_script_error.py `

```python
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
```



