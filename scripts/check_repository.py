"""Check public document placement and local Markdown file links without dependencies."""

import argparse
import posixpath
import re
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ROOT_DOCUMENTS = {'README.md', 'CHANGELOG.md', 'CONTRIBUTING.md', 'ROADMAP.md', 'SECURITY.md'}
LOCAL_DIRECTORIES = {'planning', 'test-results', 'playwright-report', 'blob-report',
                     'logs', 'tmp', 'temp', 'data', 'backups', 'exports', 'imports'}
SOURCE_DIRECTORIES = ('.github', 'docs', 'releases', 'design', 'public', 'scripts',
                      'server', 'src', 'tests')


def placement_problem(name):
    path = PurePosixPath(name)
    if path.parts[0] in LOCAL_DIRECTORIES:
        return 'local working files must not be tracked'
    if path.suffix.lower() != '.md':
        return None
    if len(path.parts) == 1 and name not in ROOT_DOCUMENTS:
        return 'put maintained guides in docs/ and temporary records in planning/'
    if path.parts[0] == 'docs' and (
        path.stem.endswith('-goal') or re.match(r'v\d+(?:[._]\d+)*[-_]', path.name)
    ):
        return 'put implementation goals and versioned session records in planning/'
    if path.parts[0] == 'design' and path.stem.endswith(('-prompt', '-prompts')):
        return 'put image-generation prompts in planning/'
    return None


def local_links(name, text):
    # Documentation uses inline Markdown links; fenced examples are not navigation.
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    for target in re.findall(r'\]\(([^)\s]+)\)', text):
        url = urlsplit(target)
        if url.scheme or url.netloc or not url.path:
            continue
        yield target, posixpath.normpath(posixpath.join(
            posixpath.dirname(name), unquote(url.path)))


def check_files(names, read_text):
    names = set(names)
    problems = []
    for name in sorted(names):
        problem = placement_problem(name)
        if problem:
            problems.append(f'{name}: {problem}')
        if not name.lower().endswith('.md'):
            continue
        for target, resolved in local_links(name, read_text(name)):
            if resolved not in names:
                problems.append(f'{name}: link target is not in the checked files: {target}')
    return problems


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def source_files(root):
    # Source ZIPs have no Git index or local dependency/build directories.
    paths = [path for path in root.iterdir() if path.is_file()]
    for folder in SOURCE_DIRECTORIES:
        paths.extend(path for path in (root / folder).rglob('*') if path.is_file())
    return {path.relative_to(root).as_posix() for path in paths}


def inventory(root, staged):
    if staged or (root / '.git').exists():
        options = () if staged else ('--others', '--exclude-standard')
        output = git(root, 'ls-files', '--cached', '-z', *options)
        names = set(output.decode('utf-8').split('\0')) - {''}
        if staged:
            return names, lambda name: git(root, 'show', ':' + name).decode('utf-8')
        names = {name for name in names if (root / name).is_file()}
    else:
        names = source_files(root)
    return names, lambda name: (root / name).read_text(encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='check Git index bytes and paths')
    args = parser.parse_args()
    try:
        names, read_text = inventory(ROOT, args.staged)
        problems = check_files(names, read_text)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f'Repository check could not run: {error}')
        return 1
    if problems:
        print('\n'.join(problems))
        print('See CONTRIBUTING.md for document placement and publication rules.')
        return 1
    count = sum(name.lower().endswith('.md') for name in names)
    print(f'Repository hygiene passed: {len(names)} files, {count} Markdown documents.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
