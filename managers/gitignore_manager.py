import collections
import os
import re

from os.path import dirname
from pathlib import Path
from typing import Union

from django.conf import settings


whitespace_re = re.compile(r'(\\ )+$')


class MockSettings:
    FULL_SETTINGS_SET = os.environ


try:
    from django.conf import settings
    hasattr(settings, 'DEBUG')
except Exception as e:
    settings = MockSettings()


class GitignoreManager:
    """Менеджер по работе с .gitignore
       Является самостоятельным сборщиком списка файлов,
       которые не ограничивает .gitignore и которые можно отправить в репозиторий
    """
    matcher = None

    def __init__(self):
        self.base_dir = settings.FULL_SETTINGS_SET.get('BASE_DIR') or os.path.abspath(__file__)
        gitignore_path = os.path.join(self.base_dir, '.gitignore')
        self.matcher = self.read_gitignore(gitignore_path)

    def check_in_gitignore(self, folder: str, fname: str, accumulated: list, ignore_folders: list = None):
        """Проверка на присутствие в .gitignore
           :param folder: папка
           :param fname: файл/папка в folder
           :param accumulated: собранные файлы, которые прошли проверку
           :param ignore_folders: список папок, которые игнорируем
                                  проверяться будет вглубь, поэтому проверяем по startswith
        """
        path = os.path.join(folder, fname)
        ignore = self.matcher(path)
        if not ignore and ignore_folders:
            for item in ignore_folders:
                ignore_folder = os.path.join(self.base_dir, item)
                if path.startswith(ignore_folder):
                    ignore = True
                    break

        if os.path.isfile(path):
            if not ignore:
                accumulated.append({
                    'folder': folder,
                    'fname': fname,
                })
        elif os.path.isdir(path):
            if ignore:
                return
            # print('dir %s' % fname, self.matcher(path))
            for sub_path in os.listdir(path):
                self.check_in_gitignore(
                    folder=path,
                    fname=sub_path,
                    accumulated=accumulated,
                    ignore_folders=ignore_folders,
                )

    def handle_negation(self, file_path: str, rules: list):
        """Проверка на соответствию правилам
           :param file_path: путь к файлу
           :param rules: правила IgnoreRule
        """
        matched = False
        for rule in rules:
            if rule.match(file_path):
                if rule.negation:
                    matched = False
                else:
                    matched = True
        return matched

    def read_gitignore(self, full_path: str):
        """Читаем правила из .gitignore
           Правила, которые ниже могут переопределить правила, которые выше
        """
        base_dir = dirname(full_path)
        rules = []
        with open(full_path) as gitignore:
            counter = 0
            for line in gitignore:
                counter += 1
                line = line.rstrip('\n')
                rule = self.rule_from_pattern(
                    line,
                    base_path=Path(base_dir).resolve(),
                    source=(full_path, counter)
                )
                if rule:
                    rules.append(rule)
        if not any(r.negation for r in rules):
            return lambda file_path: any(r.match(file_path) for r in rules)
        else:
            return lambda file_path: self.handle_negation(file_path, rules)

    def rule_from_pattern(self, pattern, base_path=None, source=None):
        """Делаем правило из шаблона .gitignore
           Например, "*.py[cod]" or "**/*.bak",
           возвращаем IgnoreRule для сравнивания с файлами и папками
           Комменты и пустые строки возращают None
           .gitignore поддерживает вложенные .gitignore файлы,
           поэтому работаем с абсолютными путями
        """
        if base_path and base_path != Path(base_path).resolve():
            raise ValueError('base_path must be absolute')
        # Запомнираем шаблон для отображения __str__, __repr__
        orig_pattern = pattern
        # Комментарии или пустые строки
        if pattern.strip() == '' or pattern[0] == '#':
            return
        # Больше двух звездочек - моветон
        if pattern.find('***') > -1:
            return
        # Убираем восклицалку
        if pattern[0] == '!':
            negation = True
            pattern = pattern[1:]
        else:
            negation = False
        # Убираем двойные звездочки в начале и конце, либо заэкранированные
        for m in re.finditer(r'\*\*', pattern):
            start_index = m.start()
            if (start_index != 0 and start_index != len(pattern) - 2 and
                    (pattern[start_index - 1] != '/' or
                     pattern[start_index + 2] != '/')):
                return

        # Если у нас '/', что не должно соответствовать файлу или папке
        if pattern.rstrip() == '/':
            return

        directory_only = pattern[-1] == '/'
        anchored = '/' in pattern[:-1]
        if pattern[0] == '/':
            pattern = pattern[1:]
        if pattern[0] == '*' and len(pattern) >= 2 and pattern[1] == '*':
            pattern = pattern[2:]
            anchored = False
        if pattern[0] == '/':
            pattern = pattern[1:]
        if pattern[-1] == '/':
            pattern = pattern[:-1]
        # хэш символы в начале строки экранируются, убираем
        if pattern[0] == '\\' and pattern[1] == '#':
            pattern = pattern[1:]
        # пробелы в конце инорируются без экранирования
        i = len(pattern) - 1
        striptrailingspaces = True
        while i > 1 and pattern[i] == ' ':
            if pattern[i - 1] == '\\':
                pattern = pattern[:i - 1] + pattern[i:]
                i = i - 1
                striptrailingspaces = False
            else:
                if striptrailingspaces:
                    pattern = pattern[:i]
            i = i - 1
        regex = self.fnmatch_pathname_to_regex(
            pattern, directory_only, negation, anchored=bool(anchored)
        )
        return IgnoreRule(
            pattern=orig_pattern,
            regex=regex,
            negation=negation,
            directory_only=directory_only,
            anchored=anchored,
            base_path=Path(base_path) if base_path else None,
            source=source
        )

    def fnmatch_pathname_to_regex(self, pattern, directory_only: bool, negation: bool, anchored: bool = False):
        """Приводим путь к регулярному выражению IgnoreRule

           В *nix fnmatch - сравнивает имя файла и путь и
           возвращает ноль, если строка string совпадает с шаблоном pattern,
           возвращает FNM_NOMATCH, если строка и шаблон не совпадают,
           или другое ненулевое значение, если есть какая-либо ошибка в шаблоне

           К сожалению, в Python не предоставляет FNM_PATHNAME.
           FNM_PATHNAME сравнивает косую черту в строке string с косой чертой в шаблоне pattern
           и не сравнивает ее, например, с последовательностью [] -, содержащую эту черту
           поэтому здесь есть небольшая неточность

           Пробуем реализовать стиль поведения fnmatch как будто с FNM_PATHNAME;
           разделитель пути не будет учитывать wildcard '*' и '.'
        """
        i, n = 0, len(pattern)

        seps = [re.escape(os.sep)]
        if os.altsep is not None:
            seps.append(re.escape(os.altsep))
        seps_group = '[' + '|'.join(seps) + ']'
        nonsep = r'[^{}]'.format('|'.join(seps))

        res = []
        while i < n:
            c = pattern[i]
            i += 1
            if c == '*':
                try:
                    if pattern[i] == '*':
                        i += 1
                        res.append('.*')
                        if pattern[i] == '/':
                            i += 1
                            res.append(''.join([seps_group, '?']))
                    else:
                        res.append(''.join([nonsep, '*']))
                except IndexError:
                    res.append(''.join([nonsep, '*']))
            elif c == '?':
                res.append(nonsep)
            elif c == '/':
                res.append(seps_group)
            elif c == '[':
                j = i
                if j < n and pattern[j] == '!':
                    j += 1
                if j < n and pattern[j] == ']':
                    j += 1
                while j < n and pattern[j] != ']':
                    j += 1
                if j >= n:
                    res.append('\\[')
                else:
                    stuff = pattern[i:j].replace('\\', '\\\\')
                    i = j + 1
                    if stuff[0] == '!':
                        stuff = ''.join(['^', stuff[1:]])
                    elif stuff[0] == '^':
                        stuff = ''.join('\\' + stuff)
                    res.append('[{}]'.format(stuff))
            else:
                res.append(re.escape(c))
        if anchored:
            res.insert(0, '^')
        res.insert(0, '(?ms)')
        if not directory_only:
            res.append('$')
        elif directory_only and negation:
            res.append('/$')
        else:
            res.append('($|\/)')
        return ''.join(res)


class IgnoreRule(collections.namedtuple('IgnoreRule_', [
    'pattern', 'regex',  # Basic values
    'negation', 'directory_only', 'anchored',  # Behavior flags
    'base_path',  # Meaningful for gitignore-style behavior
    'source'  # (file, line) tuple for reporting
])):

    def __str__(self):
        return self.pattern

    def __repr__(self):
        return ''.join(['IgnoreRule(\'', self.pattern, '\')'])

    def match(self, abs_path: Union[str, Path]):
        matched = False
        if self.base_path:
            rel_path = str(Path(abs_path).resolve().relative_to(self.base_path))
        else:
            rel_path = str(Path(abs_path))
        # Path() убирает слеши в конце, надо вернуть их
        if self.negation and type(abs_path) == str and abs_path[-1] == '/':
            rel_path += '/'
        if rel_path.startswith('./'):
            rel_path = rel_path[2:]
        if re.search(self.regex, rel_path):
            matched = True
        return matched
