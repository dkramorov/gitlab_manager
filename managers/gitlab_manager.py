import logging
import base64
import datetime
import re
import traceback
from enum import Enum
import os
import time

import gitlab

from managers.simple_logger import logger, json_pretty_print
from django.conf import settings


class MRStates(Enum):
    """Состояния запросов на слияние"""
    ALL = 'all'
    MERGED = 'merged'
    OPENED = 'opened'
    CLOSED = 'closed'
    LOCKED = 'locked'


class GitlabManager:
    """Менеджер для работы с gitlab репозиториями
       https://python-gitlab.readthedocs.io/en/stable/api-usage-advanced.html
       Если сертификат самоподписанный
       python-gitlab relies on the CA certificate bundle in the certifi package
       that comes with the requests library.
       import os; os.environ['REQUESTS_CA_BUNDLE'] = '/Users/.../ca-cert.crt'
       GitlabManager.get_projects()(**{'hostname': 'gitlab.domain', 'token':'token'})
    """
    manager = None
    project = None
    global_branch = 'master'
    author_email = 'admin@example.ru'
    author_name = 'Den'
    hostname = 'git.example.ru'
    token = 'Set token here'
    group_id = 1324
    project_name = 'test-project1'
    branch_name = 'new_branch_%s' % datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    mr_states = ('all', 'merged', 'opened', 'closed', 'locked')
    nginx_filename = 'demo_nginx.conf'
    port_api = None
    port_back = None
    admin_login = 'admin'
    admin_passwd = 'nimda'
    repeat_count = 5

    access_levels = {
        10: gitlab.const.AccessLevel.GUEST,
        20: gitlab.const.AccessLevel.REPORTER,
        30: gitlab.const.AccessLevel.DEVELOPER,
        40: gitlab.const.AccessLevel.MAINTAINER,
        50: gitlab.const.AccessLevel.OWNER,
    }

    txt_extensions = [
        'py',
        'txt',
        'toml',
        'md',
    ]

    def __init__(self, **kwargs):
        """Инициализация, все переменные получаем из kwargs опционально
           по одноименному атрибуту
        """
        if kwargs:
            for kwarg in (
                    'global_branch',
                    'author_email',
                    'author_name',
                    'hostname',
                    'token',
                    'group_id',
                    'project_name',
                    'branch_name',
                    'port_api',
                    'port_back',
                    'admin_login',
                    'admin_passwd',
            ):
                if kwarg in kwargs:
                    setattr(self, kwarg, kwargs[kwarg])
        self.manager = gitlab.Gitlab(url='https://%s' % self.hostname, private_token=self.token)

    def auth(self):
        """Авторизация"""
        for i in range(self.repeat_count):
            try:
                self.manager.auth()
                break
            except Exception as e:
                logger.info('--- auth error: %s ---' % e)
                time.sleep(1)

    def enable_debug(self):
        """Включает подробную отладку"""
        self.manager.enable_debug()

    def get_obj_list(self, obj, per_page: int = None, page: int = None):
        """Получение списка с постраничной навигацией, но предпочтительнее использовать iterator=True
           Можно также глобально передавать значение per_page, например,
                 gitlab.Gitlab(url, token, pagination="keyset", order_by="id", per_page=100)
           :param obj: объект-менеджер который запрашиваем, например, obj=project.pipelines
           :param per_page: запрашиваемое кол-во
           :param page: номер странички # The first page is page 1, not page 0.
        """
        return obj.list(per_page=per_page, page=page)

    def get_deploy_tokens(self, group=None, project=None):
        """Получение списка токенов для деплоя
           :param group: группа
           :param project: проект
        """
        if group:
            return group.deploytokens.list(iterator=True)
        if project:
            return project.deploytokens.list(iterator=True)
        return self.manager.deploytokens.list(iterator=True)

    def create_deploy_token(self,
                            group_or_project,
                            name: str = 'my_token',
                            scopes: list = None,
                            username: str = ''):
        """Создание токена для деплоя
           :param group_or_project: группа или проект
        """
        if not scopes:
            scopes = [
                'read_repository',
                #'read_registry',
                #'read_package_registry',
                #'write_registry',
                #'write_package_registry',
            ]
        deploy_token = group_or_project.deploytokens.create({
            'name': name,
            'scopes': scopes,
            'username': username,
            'expires_at': '',
        })
        return deploy_token  # deploy_token.id / deploy_token.token

    def get_groups(self, get_all: bool = False):
        """Получение списка групп,
           по умолчанию 20 первых, но с get_all/iterator будут получены все
           :param get_all: выведет все группы
        """
        if not get_all:
            return self.manager.groups.list(iterator=True)
        return self.manager.groups.list(get_all=True)

    def get_subgroups(self, group, get_all: bool = False):
         """Получение списка подгруп
            The GroupSubgroup objects don’t expose the same API as the Group objects.
            If you need to manipulate a subgroup as a group, create a new Group object
            :param group: группа
            :param get_all: выведет все подгруппы
         """
         if not get_all:
             return group.subgroups.list(iterator=True)
         return group.subgroups.list(get_all=True)

    def get_group(self, group_id: int):
        """Получаем группу по ид
           :param group_id: ид группы
        """
        for i in range(self.repeat_count):
            try:
                return self.manager.groups.get(id=group_id)
            except Exception as e:
                logger.info('get_group error: %s' % e)

    def get_projects(self, get_all: bool = False):
        """Получение списка проектов,
           по умолчанию 20 первых, но с get_all/iterator будут получены все
           :param get_all: выведет все проекты
        """
        if not get_all:
            return self.manager.projects.list(iterator=True)
        return self.manager.projects.list(get_all=True)

    def get_project(self, project_id: int, statistics: bool = True):
        """Получаем проект по ид
           :param project_id: ид проекта
           :param statistics: статистика (например, размер репозитория)
        """
        return self.manager.projects.get(id=project_id, statistics=statistics)

    def get_group_project(self, group, project_name: str = None):
        """Получить конкретный проект группы
           :param group: менеджер для группы
           :param project_name: название проекта, который ищем
        """
        if not project_name:
            project_name = self.project_name
        for item in group.projects.list(iterator=True):
            if item.name == project_name:
                return self.manager.projects.get(item.get_id())

    def create_group_project(self, group_id: int = None, project_name: str = None):
        """Создание проекта в группе
           :param group_id: идентификатор группы
           :param project_name: название проекта
        """
        if not project_name:
            project_name = self.project_name
        if not group_id:
            group_id = self.group_id
        return self.manager.projects.create({
            'name': project_name,
            'namespace_id': group_id,
            'default_branch': self.global_branch,
            'initialize_with_readme': True,
        })

    def drop_project(self, project_id: int):
        """Удаление проекта
           :param project_id: идентификатор проекта
        """
        return self.manager.projects.delete(project_id)

    def search_projects(self, search_str: str):
        """Поиск проектов
           :param search_str: поисковая строка, например, 'bazis'
        """
        return self.manager.projects.list(search=search_str)

    def get_group_by_id(self, group_id: int = None):
        """Получение группы проектов
           :param group_id: идентификатор группы
        """
        return self.manager.groups.get(group_id or self.group_id)

    def get_pipelines(self, project=None):
        """Получение пайпланов
           :param project: менеджер проекта
        """
        pipelines = []
        if not project:
            project = self.project
        pipelines = project.pipelines.list(iterator=True)
        return pipelines

    def get_mr_pipelines(self, mr):
        """Получение пайплайнов на мерж реквест
           TODO: Ничего не получает
           :param mr: мерж реквест
        """
        return mr.pipelines.list(iterator=True)

    def get_mr_commits(self, mr):
        """Получение комитов на мерж реквест
           :param mr: мерж реквест
        """
        return mr.commits()

    def get_mr(self, mr_id: int, project=None):
        """Получение мерж реквеста
           :param mr_id: ид мерж реквеста
        """
        if not project:
            project = self.project
        return project.mergerequests.get(mr_id)

    def get_mrs(self, project=None):
        """Получение мерж реквестов"""
        if not project:
            project = self.project
        return project.mergerequests.list(iterator=True)

    def pipeline_action(self, pipeline, action: str = 'retry'):
        """Действие над пайплайном
           :param pipeline: пайплайн
           :param action: действие retry/cancel/delete
        """
        if pipeline and hasattr(pipeline, action):
            return getattr(pipeline, action)()
        else:
            logger.info('attr %s absent in pipeline %s' % (action, pipeline))

    def get_jobs(self, pipeline):
        """Получить список jobs"""
        jobs = []
        for item in pipeline.jobs.list():
            jobs.append(item)
        return jobs

    def get_job(self, job_id: int, project=None):
        """Получение джобы
           :param project: менеджер проекта
           :param job_id: ид джобы
        """
        if not project:
            project = self.project
        return project.jobs.get(job_id)

    def job_retry(self, project, job):
        """Перезапустить job (job.status == 'failed')
           :param project: менеджер проекта
           :param job: джоба
        """
        if not hasattr(job, 'status'):  # если lazy=True для project.jobs.get()
            logger.info('job without status: %s' % job.asdict())
        elif job.status == 'failed':
            #job = project.jobs.get(job.id, lazy=True)
            job = self.get_job(job_id=job.id, project=project)
            job.retry()
            return job

    def get_branches(self, project=None, protected: bool = False):
        """Получение веток проекта
           :param project: менеджер проекта
           :param protected: только защищенные ветки
        """
        if not project:
            project = self.project
        if protected:
            return project.protectedbranches.list(iterator=True)
        return project.branches.list(iterator=True)

    def get_branch(self, project=None, branch_name: str = None):
        """Получение/проверка ветки
           по умолчанию используем название ветки куда хотим сливать (master)
           :param project: менеджер проекта
           :param branch_name: название новой ветки
        """
        if not project:
            project = self.project
        if not branch_name:
            branch_name = self.global_branch
        try:
            return project.branches.get(branch_name)
        except Exception:  # maybe 404 Branch Not Found
            traceback.print_exc()

    def create_branch(self,
                      project: str = None,
                      branch_name: str = None,
                      ref: str = None):
        """Создание ветки
           :param project: менеджер проекта
           :param branch_name: название новой ветки
           :param ref: от какой ветки отпочковываем новую
        """
        if not project:
            project = self.project
        if not branch_name:
            branch_name = self.branch_name
        if not ref:
            ref = self.global_branch
        # Если ветка существует - удаляем
        for branch in project.branches.list(iterator=True):
            if branch.name == self.branch_name:
                branch.delete()
        try:
            return project.branches.create(
                {'branch': branch_name, 'ref': ref}
            )
        except Exception:
            traceback.print_exc()

    def get_commits(self,
                    project=None):
        """Получение комитов к проекту"""
        if not project:
            project = self.project
        commits = project.commits.list(iterator=True)
        return commits

    def create_merge_request(self,
                             project=None,
                             branch_name: str = None,
                             ref: str = None,
                             title: str = None,
                             labels: list = None):
        """Создание Merge Request
           С мерж реквестом можно производить различные манипуляции до слияния, например,
           mr.description = 'New description'
           mr.labels = ['foo', 'bar']
           mr.save()
           mr.state_event = 'close'  # or 'reopen'
           mr.save()
           project.mergerequests.delete(mr_iid) or mr.delete()
           mr.merge()
           commits = mr.commits()
           changes = mr.changes()
           :param project: менеджер проекта
           :param branch_name: с какой ветки делаем МР
           :param ref: на какую ветку делаем МР
           :param title: название МР
           :param labels: метки на МР
        """
        if not project:
            project = self.project
        if not branch_name:
            branch_name = self.branch_name
        if not ref:
            ref = self.global_branch
        if not title:
            title = 'auto merge request %s' % branch_name
        if not labels:
            labels = ['automergerequest']
        # Если открытый мр существует, то удаляем
        for mr in project.mergerequests.list(state=MRStates.OPENED.value, iterator=True):
            if mr.source_branch == branch_name and mr.target_branch == ref:
                mr.delete()
        return project.mergerequests.create({
            'source_branch': branch_name,
            'target_branch': ref,
            'title': title,
            'labels': labels,
        })

    def merge(self, project, branch, mr, files, project_files, title: str = 'auto_merge_request'):
        """Мерж МР
           :param project: проект
           :param branch: ветка
           :param mr: мерж реквест
           :param files: отправляемые файлы (после check_in_gitignore)
           :param project_files: имеющиеся файлы на gitlab (после get_project_path_files)
        """
        is405 = False
        time.sleep(5)
        try:
            mr.merge()
        except gitlab.exceptions.GitlabMRClosedError as e:
            logger.info('--- 405: %s ---' % e)
            is405 = True

        if is405:
            for i in range(self.repeat_count):
                try:
                    branch.delete()
                except Exception:
                    logger.info('[ERROR]: branch.delete failed')
                logger.info('--- trying retry ---')
                branch = self.create_branch(project=project)
                mr = self.create_merge_request(project=project, title=title)
                commit = self.create_commit(
                    files=files,
                    project=project,
                    project_path_files=project_files,
                )
                time.sleep(10)
                try:
                    mr.merge()
                    break
                except Exception as e:
                    #traceback.print_exc()
                    logger.info('[ERROR]: merge: %s' % e)
                    time.sleep(10)

    def get_project_path_files(self,
                               project=None,
                               get_all: bool = True,
                               recursive: bool = True):
        """Получить все существующие файлы (их пути) в проекте,
           потому что от того существует файл или нет
           мы будем выбирать операцию create/update
           :param project: менеджер проекта
           :param get_all: получить все файлы
           :param recursive: обходить вложенные папки
        """
        if not project:
            project = self.project

        # path=..., ref=branch1
        try:
            project_files = project.repository_tree(**{'all': get_all, 'recursive': recursive})
        except gitlab.exceptions.GitlabGetError:
            return []
        return [item.get('path') for item in project_files]

    def find_binary(self, files: list):
        """Находим все файлы, которые надо промаркировать как binary (и маркируем)
           :param files: список словарей с файлами, например, [{'fname': '1.png', 'folder': '/opt/static'}]
                         этот список можно получить из GitignoreManager::check_in_gitignore метода
        """
        for item in files:
            if ('folder' not in item or 'fname' not in item) and 'file_path' in item:
                item['folder'], item['fname'] = item['file_path'].rsplit('/', 1)
            item['is_binary'] = self.is_binary(os.path.join(item['folder'], item['fname']))

    def is_binary(self, file_name: str):
        """Проверяем является ли файл бинарным
           бинарным он не являестя, если удается открыть его в текстовом режиме
           Мы заранее определяем набор расширений, встретив которые, считаем, что файл - текстовый
           :param file_name: путь к файлу
        """
        if file_name.count('.') > 0:
            ext = file_name.split('.')[-1]
            if ext in self.txt_extensions:
                return False
        try:
            with open(file_name, 'tr') as fname:
                fname.read()
                return False
        except Exception:
            return True

    def content_replace_helper(self, prefix: str, exclude_folders_arr: list, action: dict):
        """Отключение из конфигурационных файлов
           исключенных папок, вспомогательная функция
           :param prefix: префикс в регулярке, например, INSTALLED_APPS =
           :param exclude_folders_arr: массив с иключенными папками
           :param action: словарь с содержимым файла (action['content']),
                          где необходимо скорректировать содержимое если папка исключена
        """
        logger.info('exclude_folders_arr: %s' % exclude_folders_arr)
        rega_compiled = re.compile(prefix + '\[(.+?)]', re.I + re.U + re.DOTALL)
        search_result = rega_compiled.search(action['content'])
        new_content = []
        for item in search_result.group(1).split('\n'):
            pass_line = False
            check = item.replace(',', '').replace('\'', '').split('#')[0].strip()
            if not check:
                continue
            for exclude_folder in exclude_folders_arr:
                if exclude_folder in check:
                    pass_line = True
                    break
            if not pass_line:
                new_content.append(item)
        replacement = ('%s[\n' % prefix) + '\n'.join(new_content) + '\n]'
        action['content'] = rega_compiled.sub(replacement, action['content'])

    def check_exclude_and_include_folders(self,
                                          exclude_folders_arr: list,
                                          include_folders_arr: list,
                                          action: dict,
                                          project_name: str = None):
        """Отключение из конфигурационных файлов
           исключенных папок
           :param exclude_folders_arr: массив с иключенными папками
           :param include_folders_arr: массив с включенными папками
           :param action: словарь с содержимым файла (action['content']),
                          где необходимо скорректировать содержимое если папка исключена
           :param project_name: название проекта
        """
        # Если мы исключили папки, то надо исключить их подключение в проект
        if not isinstance(action, dict) or 'file_path' not in action:
            return

        settings_path = os.environ['DJANGO_SETTINGS_MODULE'].replace('.', '/') + '.py'
        settings_folder = os.environ['DJANGO_SETTINGS_MODULE'].split('.')[0]

        if not project_name:
            project_name = self.project_name
        file_path = action['file_path']

        if file_path == settings_path:
            self.content_replace_helper(
                prefix='INSTALLED_APPS = ',
                exclude_folders_arr=exclude_folders_arr,
                action=action,
            )
            # обязательно пишем в настройки все, что переопределяем,
            # чтобы пере-переопределять из получившегося проекта
            if hasattr(settings, 'PROJECT_NAME'):
                action['content'] = action['content'].replace('PROJECT_NAME = \'%s\'' % settings.PROJECT_NAME,
                                                              'PROJECT_NAME = \'%s\'' % project_name)

            # TODO: Пока нужна для перезагрузки проектов-приёмников, дальше посмотрим
            #middleware = '    \'bazis_models.middleware.ProjectConstructorMiddleware\','
            #action['content'] = action['content'].replace(middleware, '')

        elif file_path == '%s/urls.py' % settings_folder:
            self.content_replace_helper(
                prefix='urlpatterns = ',
                exclude_folders_arr=exclude_folders_arr,
                action=action,
            )
        elif file_path == '%s/router.py' % settings_folder:
            new_router = []
            for line in action['content'].split('\n'):
                pass_line = False
                if line.startswith('router.register('):
                    # Машруты конструктоа пока оставляем
                    # if 'bazis_models.router' in line:
                    #    pass_line = True  # Пока просто пропускаем маршруты конструктора
                    for exclude_folder in exclude_folders_arr:
                        if exclude_folder in line:
                            pass_line = True
                            break
                if not pass_line:
                    new_router.append(line)
            action['content'] = '\n'.join(new_router)
        elif file_path == 'bazis_models/routes.py':
            # Прячем апи конструктора из схемы
            action['content'] = action['content'].replace(', include_in_schema=True)', ', include_in_schema=False)')
        elif file_path == 'bazis_models/admin.py':
            # Прячем админку конструктора
            action['content'] = ''
        # Не надо переопределять подключенные приложения в данный момент (иначе обратный деплой их пустыми отправит)
        #elif file_path == '%s/custom_apps.py' % settings_folder:
        #    action['content'] = 'custom_apps=[%s]' % ','.join(['\'%s\'' % item for item in include_folders_arr])

    def create_commit(self,
                      files: list,
                      project_path_files: list,
                      project=None,
                      branch_name: str = None,
                      exclude_folders: str = None,
                      include_folders: str = None):
        """Создание commit и добавления в merge request
           :param files: список словарей с файлами, например, [{'fname': '1.png', 'folder': '/opt/static'}]
                         этот список можно получить из GitignoreManager::check_in_gitignore метода
           :param project_path_files: список путей существующих файлов в проекте (self.get_project_path_files)
           :param project: менеджер проекта
           :param branch_name: имя ветки, куда будем делать мр
           :param exclude_folders: исключенные папки из проекта,
                                   в конфигурационных файлах надо выполнить их отключение
           :param include_folders: включенные папки в проект
        """
        if not exclude_folders:
            exclude_folders_arr = []
        else:
            exclude_folders_arr = [item.strip() for item in exclude_folders.replace(' ', ',').split(',') if
                                   item.strip()]
        if not include_folders:
            include_folders_arr = []
        else:
            include_folders_arr = [item.strip() for item in include_folders.replace(' ', ',').split(',') if
                                   item.strip()]
        if not project:
            project = self.project
        if not branch_name:
            branch_name = self.branch_name
        data = {
            'branch': branch_name,
            'commit_message': 'auto commit',
            'actions': [],
        }
        # Макрируем бинарники
        self.find_binary(files)
        for item in files:
            file_path = os.path.join(item['folder'], item['fname'])
            # в контейнере может быть settings.BASE_DIR=/app (а у нас /app/apps, тогда a.replace(settings.BASE_DIR, '') = s)
            gitlab_path = os.path.join(item['folder'].replace(settings.BASE_DIR, '', 1), item['fname']).lstrip('/')
            action = 'update' if gitlab_path in project_path_files else 'create'
            action = {
                'action': action,
                'file_path': gitlab_path,
            }
            logger.info(action)
            # Бинарники надо слать в base64 кодированном виде
            if item.get('is_binary'):
                action['encoding'] = 'base64'
                with open(file_path, mode='r+b') as f:
                    action['content'] = base64.b64encode(f.read()).decode()
            else:
                with open(file_path, mode='r', encoding='utf-8') as f:
                    action['content'] = f.read()
                self.check_exclude_and_include_folders(exclude_folders_arr=exclude_folders_arr,
                                                       include_folders_arr=include_folders_arr,
                                                       action=action)
            data['actions'].append(action)
        # Файлы для автодеплоя
        autodeploy_files = self.autodeploy_files(project_path_files=project_path_files)
        # Проверка на исключенные папки (если в исключенных есть файл автодеплоя, надо оставить оригинал)
        for item in autodeploy_files:
            if item['file_path'] in exclude_folders_arr:
                item['excluded'] = True
        autodeploy_files = [item for item in autodeploy_files if not item.get('excluded')]
        # Необходимо убрать оригинальные файлы и подложить созданные
        autodeploy_files_paths = [item['file_path'] for item in autodeploy_files]
        for file_path in autodeploy_files_paths:
            for i, item in enumerate(data['actions']):
                if item['file_path'] == file_path:
                    del data['actions'][i]
                    break
        data['actions'] += autodeploy_files
        return project.commits.create(data)

    def autodeploy_files(self, project_path_files: list):
        """Пишем конфигурацию деплоя приложения перед отправкой в репозиторий
           :param project_path_files: список путей существующих файлов в проекте (self.get_project_path_files)
           TODO: подтягивать пути для группы и регистри из апи гитлаба
                 более изящно подкидывать их в мр после сбора
        """
        return [] # пока не используем файлы для переопределения стандартных
        from bazis_gitlab.deploy_config import (
            NginxConfig,
            DeployScriptConfig,
            DockerConfig,
            EntryPointConfig,
            CIConfig,
        )
        actions = []
        actions.append({
            'action': 'update' if GitlabManager.nginx_filename in project_path_files else 'create',
            'file_path': GitlabManager.nginx_filename,
            'content': NginxConfig.conf % (
                self.project_name,
                NginxConfig.default_domain,
                NginxConfig.default_folder,
                self.port_api,
                self.port_api,
                self.port_api,
                self.port_api,
                self.port_back,
            ),
        })
        actions.append({
            'action': 'update' if DeployScriptConfig.drop_filename in project_path_files else 'create',
            'file_path': DeployScriptConfig.drop_filename,
            'content': DeployScriptConfig.drop % (
                self.project_name,
            ),
        })
        actions.append({
            'action': 'update' if DeployScriptConfig.update_filename in project_path_files else 'create',
            'file_path': DeployScriptConfig.update_filename,
            'content': DeployScriptConfig.update % (
                self.project_name,
                DeployScriptConfig.default_registry,
                DeployScriptConfig.default_gitlab_group,
            ),
        })
        actions.append({
            'action': 'update' if DeployScriptConfig.upgrade_filename in project_path_files else 'create',
            'file_path': DeployScriptConfig.upgrade_filename,
            'content': DeployScriptConfig.upgrade % (
                self.project_name,
                DeployScriptConfig.default_registry,
                DeployScriptConfig.default_gitlab_group,
            ),
        })
        actions.append({
            'action': 'update' if DeployScriptConfig.run_filename in project_path_files else 'create',
            'file_path': DeployScriptConfig.run_filename,
            'content': DeployScriptConfig.run % (
                self.project_name,
                DeployScriptConfig.default_registry,
                DeployScriptConfig.default_gitlab_group,
                self.port_api,
                self.port_back,
                self.admin_login,
                self.admin_passwd,
            ),
        })
        actions.append({
            'action': 'update' if EntryPointConfig.entrypoint_filename in project_path_files else 'create',
            'file_path': EntryPointConfig.entrypoint_filename,
            'content': EntryPointConfig.conf,
        })
        actions.append({
            'action': 'update' if DockerConfig.docker_filename in project_path_files else 'create',
            'file_path': DockerConfig.docker_filename,
            'content': DockerConfig.conf,
        })
        actions.append({
            'action': 'update' if CIConfig.ci_filename in project_path_files else 'create',
            'file_path': CIConfig.ci_filename,
            'content': CIConfig.conf,
        })
        return actions

    def get_variables_manager(self, group_or_project=None):
        """Получить менеджер переменных
           :param group_or_project: группа или проект
        """
        if group_or_project:
            return group_or_project.variables
        return self.manager.variables

    def get_variables(self, group_or_project=None):
        """Получить список variables (ci/cd)
           :param group_or_project: группа или проект
        """
        variables = []
        for item in self.get_variables_manager(group_or_project=group_or_project).list(iterator=True):
            variables.append(item)
        return variables

    def get_variable(self, k: str, group_or_project=None):
        """Получить список variables (ci/cd)
           :param k: ключ
           :param group_or_project: группа или проект
        """
        return self.get_variables_manager(group_or_project=group_or_project).get(k)

    def create_variable(self, k: str, v: str, group_or_project=None, **kwargs):
        """Создать переменную
           :param k: ключ
           :param v: значение
           :param group_or_project: группа или проект
        """
        try:
            data = {'key': k, 'value': v}
            for kwarg in kwargs:
                data[kwarg] = kwargs[kwarg]
            return self.get_variables_manager(group_or_project=group_or_project).create(data)
        except Exception as e:
            return e  # gitlab.exceptions.GitlabCreateError: 400: {'key': ['(TEST_KEY) has already been taken']}

    def update_variable(self, k, v, group_or_project=None, **kwargs):
        """Обновить переменную
           :param k: ключ
           :param v: значение
           :param group_or_project: группа или проект
        """
        try:
            variable = self.get_variables_manager(group_or_project=group_or_project).get(k)
            variable.value = v
            for k, v in kwargs.items():
                setattr(variable, k, v)
            variable.save()
            return variable
        except Exception as e:
            return e

    def drop_variable(self, k, group_or_project=None):
        """Удалить переменную
           :param k: ключ
           :param group_or_project: группа или проект
        """
        try:
            return self.get_variables_manager(group_or_project=group_or_project).delete(k)
        except Exception as e:
            return e  # gitlab.exceptions.GitlabDeleteError: 404: 404 Variable Not Found

    def replace_all_vars(self,
                         search_key: str = None,
                         search_value: str = None,
                         search_in_projects: bool = True,
                         search_in_groups: bool = True,
                         variable_type: str = 'env_var',
                         set_new_value: str = None):
        """Заменить переменные во всех проектах
           :param search_key: ключ переменной (название)
           :param search_value: значение переменной
           :param search_in_projects: поиск в проектах
           :param search_in_groups: поиск в группах
           :param variable_type: тип переменной (env_var/file)
           :param set_new_value: новое значение
           TODO: environment
        """
        result = []
        def replace_all_vars_helper(project_or_group, rows: list):
            """Вспомогательная функция замены переменных
               :param project_or_group: проект или группа
               :param rows: список найденных переменных
            """
            for row in rows:
                if not row.value:
                    # Если скрыто значение
                    logger.info('replace_all_vars_helper: value absent for %s' % row)
                    continue
                value = row.value.strip()
                if row.variable_type != variable_type:
                    continue
                if search_key and row.key == search_key:
                    logger.info('replace_all_vars_helper: found var %s by key in %s' % (
                        row.key,
                        project_or_group.web_url,
                    ))
                elif search_value and value == search_value:
                    logger.info('replace_all_vars_helper: found var %s by value %s in %s' % (
                        row.key,
                        value,
                        project_or_group.web_url,
                    ))
                else:
                    continue
                # ЗАМЕНА
                if set_new_value:
                    if value == set_new_value:
                        logger.info('replace_all_vars_helper: key %s (scope=%s) already has value=%s in %s' % (
                            row.key,
                            row.environment_scope,
                            set_new_value,
                            project_or_group.web_url,
                        ))
                        continue
                    logger.info('replace_all_vars_helper: changing %s (scope=%s) from %s to %s in %s' % (
                        row.key,
                        row.environment_scope,
                        row.value,
                        set_new_value,
                        project_or_group.web_url,
                    ))
                    result.append({
                        'url': project_or_group.web_url,
                        'key': row.key,
                        'old_value': row.value,
                        'new_value': set_new_value,
                        'scope': row.environment_scope,
                    })
                    row.value = set_new_value
                    row.save(filter={'environment_scope': row.environment_scope})

        if search_in_projects:
            for project in self.get_projects():
                try:
                    items = self.get_variables(group_or_project=project)
                except Exception as e:
                    logger.info('[ERROR]: %s, %s' % (project.web_url, e))
                    continue
                replace_all_vars_helper(project_or_group=project, rows=items)

        if search_in_groups:
            for group in self.get_groups():
                try:
                    items = self.get_variables(group_or_project=group)
                except Exception as e:
                    logger.info('[ERROR]: %s, %s' % (group.web_url, e))
                    continue
                replace_all_vars_helper(project_or_group=group, rows=items)

        return result