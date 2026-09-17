"""Exercise real Bash scripts with fake runtimes; no installs, servers, or network."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
GIT_BASH = Path('C:/Program Files/Git/bin/bash.exe')
BASH = str(GIT_BASH) if os.name == 'nt' and GIT_BASH.is_file() else shutil.which('bash')
pytestmark = pytest.mark.skipif(not BASH, reason='Bash is required for shell workflow tests')

PYTHON = r'''#!/bin/bash
set -eu
printf 'python|%s|%s\n' "$PWD" "$*" >> "$PROSPERO_TEST_LOG"
if [[ "$0" == *'/.venv/'* && "${BROKEN_VENV:-0}" == 1 ]]; then exit 1; fi
if [[ "$0" == *'/fake-bin/'* && "${OLD_PYTHON:-0}" == 1 ]]; then exit 1; fi
if [[ "${1:-}" == -m && "${2:-}" == venv ]]; then
    [[ "$#" == 3 ]] || exit 88
    mkdir -p "$3/bin"
    cp "$PROSPERO_TEST_STUBS/python3" "$3/bin/python"
    chmod +x "$3/bin/python"
fi
if [[ "$*" == *'pip install'* && "${FAIL_PIP:-0}" == 1 ]]; then exit 23; fi
if [[ "$*" == *'scripts.launch_interface'* ]]; then exit "${LAUNCH_EXIT:-0}"; fi
'''
NODE = r'''#!/bin/bash
printf 'node|%s|%s\n' "$PWD" "$*" >> "$PROSPERO_TEST_LOG"
if [[ "$0" == *'/fake-bin/'* && "${OLD_NODE:-0}" == 1 ]]; then exit 1; fi
'''
NPM = r'''#!/bin/bash
set -eu
printf 'npm|%s|%s\n' "$PWD" "$*" >> "$PROSPERO_TEST_LOG"
if [[ "${1:-}" == run && "${2:-}" == build ]]; then
    mkdir -p dist
    printf 'fixture build' > dist/index.html
fi
'''
BREW = r'''#!/bin/bash
set -eu
if [[ "$1" == --prefix ]]; then cd -- "$PROSPERO_TEST_BREW"; pwd; exit 0; fi
[[ "$1" == install ]] || exit 89
printf 'brew|%s|%s\n' "$PWD" "$*" >> "$PROSPERO_TEST_LOG"
if [[ "${FAIL_BREW:-0}" == 1 ]]; then exit 24; fi
mkdir -p "$PROSPERO_TEST_BREW/bin" "$PROSPERO_TEST_BREW/opt/node@24/bin"
cp "$PROSPERO_TEST_STUBS/python3" "$PROSPERO_TEST_BREW/bin/python3.12"
cp "$PROSPERO_TEST_STUBS/node" "$PROSPERO_TEST_BREW/opt/node@24/bin/node"
cp "$PROSPERO_TEST_STUBS/npm" "$PROSPERO_TEST_BREW/opt/node@24/bin/npm"
chmod +x "$PROSPERO_TEST_BREW/bin/python3.12" "$PROSPERO_TEST_BREW/opt/node@24/bin/"*
'''


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')
    path.chmod(0o755)


@pytest.fixture
def shell_project(tmp_path):
    project = tmp_path / 'Study with spaces'
    project.mkdir()
    for name in ('install.sh', 'launch.sh'):
        text = (ROOT / name).read_text(encoding='utf-8')
        # Never discover a real host Homebrew installation in a test.
        for prefix in ('/opt/homebrew', '/usr/local'):
            text = text.replace(prefix + '/bin/brew', (tmp_path / 'absent-brew').as_posix())
        executable(project / name, text)
    bins = tmp_path / 'fake-bin'
    for name, text in {'python3': PYTHON, 'python3.12': PYTHON, 'node': NODE, 'npm': NPM, 'brew': BREW,
                       'uname': '#!/bin/bash\nprintf "%s\\n" "${TEST_OS:-Darwin}"\n'}.items():
        executable(bins / name, text)
    environment = {**os.environ, 'PROSPERO_TEST_LOG': (tmp_path / 'commands.log').as_posix(),
                   'PROSPERO_TEST_STUBS': bins.as_posix(),
                   'PROSPERO_TEST_BREW': (tmp_path / 'brew-prefix').as_posix()}
    (tmp_path / 'brew-prefix').mkdir()
    (project / 'data').mkdir()
    (project / 'data' / 'story.txt').write_text('Keep this story.')
    return project, bins, environment


def run_script(fixture, script='install.sh', *args, **overrides):
    project, bins, environment = fixture
    result = subprocess.run([BASH, '--noprofile', '--norc', '-c',
                             'export PATH="$(cd -- "$1" && pwd):/usr/bin:/bin"; exec /bin/bash "$2" "${@:3}"',
                             'test', bins.as_posix(), (project / script).as_posix(), *args],
                            cwd=project.parent, env={**environment, **overrides},
                            capture_output=True, text=True, timeout=25)
    assert (project / 'data' / 'story.txt').read_text() == 'Keep this story.'
    log = Path(environment['PROSPERO_TEST_LOG'])
    return result, log.read_text() if log.exists() else ''


def installed(fixture):
    project, _, _ = fixture
    executable(project / '.venv' / 'bin' / 'python', PYTHON)
    (project / 'dist').mkdir(exist_ok=True)
    (project / 'dist' / 'index.html').write_text('Already built')


@pytest.mark.parametrize('script', ['install.sh', 'launch.sh'])
def test_shell_syntax_and_help_without_dependencies(shell_project, script):
    subprocess.run([BASH, '-n', (ROOT / script).as_posix()], check=True, capture_output=True)
    result, log = run_script(shell_project, script, '--help')
    assert result.returncode == 0, result.stderr
    assert 'Usage:' in result.stdout
    assert not log


def test_installer_uses_existing_runtimes_and_quoted_project_path(shell_project):
    result, log = run_script(shell_project)
    assert result.returncode == 0, result.stderr
    assert 'pip install --disable-pip-version-check --no-input -r requirements.lock.txt' in log
    assert 'ci --no-audit --no-fund' in log
    assert 'run build' in log and 'pip check' in log and 'ls --depth=0' in log
    assert 'brew|' not in log
    assert (shell_project[0] / '.venv' / 'bin' / 'python').is_file()
    assert 'Ready.' in result.stdout


def test_installer_reuses_existing_environment(shell_project):
    installed(shell_project)
    result, log = run_script(shell_project)
    assert result.returncode == 0, result.stderr
    assert '-m venv' not in log


def test_brew_fallback_finds_new_runtimes_behind_older_path_entries(shell_project):
    result, log = run_script(shell_project, OLD_PYTHON='1', OLD_NODE='1')
    assert result.returncode == 0, result.stderr
    assert 'install python@3.12 node@24' in log
    assert 'run build' in log


def test_missing_brew_gives_manual_setup_without_installing(shell_project):
    (shell_project[1] / 'brew').unlink()
    result, log = run_script(shell_project, OLD_PYTHON='1', OLD_NODE='1')
    assert result.returncode == 1
    assert 'https://brew.sh' in result.stderr
    assert 'pip install' not in log and '-m venv' not in log


def test_check_only_never_installs_or_builds(shell_project):
    installed(shell_project)
    result, log = run_script(shell_project, 'install.sh', '--check-only')
    assert result.returncode == 0, result.stderr
    assert 'pip check' in log and 'ls --depth=0' in log
    assert 'pip install' not in log and 'run build' not in log and 'brew|' not in log


def test_check_only_missing_runtime_never_uses_brew_install(shell_project):
    result, log = run_script(shell_project, 'install.sh', '--check-only', OLD_NODE='1')
    assert result.returncode == 1
    assert 'required' in result.stderr
    assert 'brew|' not in log


def test_foreign_or_broken_environment_is_not_overwritten(shell_project):
    (shell_project[0] / '.venv' / 'Scripts').mkdir(parents=True)
    marker = shell_project[0] / '.venv' / 'Scripts' / 'python.exe'
    marker.write_text('existing environment')
    result, log = run_script(shell_project)
    assert result.returncode == 1
    assert 'Rename it' in result.stderr
    assert marker.read_text() == 'existing environment'
    assert '-m venv' not in log and 'brew|' not in log


@pytest.mark.parametrize('flag,expected', [('FAIL_PIP', 23), ('FAIL_BREW', 24)])
def test_failed_dependency_install_stops_before_build(shell_project, flag, expected):
    options = {flag: '1'}
    if flag == 'FAIL_BREW':
        options.update(OLD_PYTHON='1', OLD_NODE='1')
    result, log = run_script(shell_project, **options)
    assert result.returncode == expected
    assert 'run build' not in log and 'Ready.' not in result.stdout


def test_launch_forwards_arguments_and_exit_status_without_installing(shell_project):
    installed(shell_project)
    result, log = run_script(shell_project, 'launch.sh', '--no-browser', '--port', '8877', LAUNCH_EXIT='7')
    assert result.returncode == 7
    assert '-m scripts.launch_interface --no-browser --port 8877' in log
    assert 'pip install' not in log and 'npm|' not in log and 'brew|' not in log


def test_launch_missing_environment_explains_setup(shell_project):
    result, log = run_script(shell_project, 'launch.sh')
    assert result.returncode == 1
    assert 'bash install.sh' in result.stderr
    assert 'scripts.launch_interface' not in log


@pytest.mark.parametrize('script', ['install.sh', 'launch.sh'])
def test_other_platforms_get_correct_launcher_guidance(shell_project, script):
    result, log = run_script(shell_project, script, TEST_OS='MINGW64_NT')
    assert result.returncode == 1
    assert script.replace('.sh', '.bat') in result.stderr
    assert not log


def test_windows_dependency_is_selected_only_on_windows():
    line = next(line for line in (ROOT / 'requirements.lock.txt').read_text().splitlines()
                if line.startswith('pywin32-ctypes'))
    requirement = Requirement(line)
    assert requirement.marker.evaluate({'sys_platform': 'win32'})
    assert not requirement.marker.evaluate({'sys_platform': 'darwin'})
