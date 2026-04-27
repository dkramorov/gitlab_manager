Описание
-----------
Менеджер для работы с api Gitlab/Github
https://python-gitlab.readthedocs.io/en/stable/api-usage.html

Установка пакетом
-----------
Для локальной разработки::
    pip install -e packages/gitlab_manager
Для обычной установки через requirements.txt::
    excel_manager @ git+https://github.com/dkramorov/gitlab_manager.git


Импорт
-----------
Проверка::
    from managers.gitlab_manager import GitlabManager


Удаление
-----------
Удалить пакет::
    pip uninstall gitlab_manager

Для создания пакета
https://docs.python.org/3.10/distutils/introduction.html#distutils-simple-example
https://docs.python.org/3.10/distutils/sourcedist.html
::
    python setup.py sdist




