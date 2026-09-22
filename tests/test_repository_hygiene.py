"""Exercise the publication boundary with small isolated repositories."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.check_repository import check_files, inventory


class RepositoryHygieneTests(unittest.TestCase):
    def test_maintained_docs_assets_and_release_notes_are_allowed(self):
        files = {'README.md': '[Guide](docs/guide.md#writing)',
                 'CONTRIBUTING.md': '', 'ROADMAP.md': '', 'SECURITY.md': '',
                 'docs/guide.md': '![Illustration](../design/guide.png)',
                 'design/guide.png': '', 'releases/v1.0.0.md': '[Home](../README.md)',
                 'tests/fixtures/example.md': ''}
        self.assertEqual(check_files(files, files.__getitem__), [])

    def test_work_records_and_forced_local_artifacts_are_rejected(self):
        for name in ('v100-implementation-goal.md', 'feature-checkpoint.md',
                     'docs/v100-validation.md', 'docs/nested/v110-evaluation.md',
                     'docs/nested/v1.0.0-checkpoint.md',
                     'docs/writing-goal.md', 'design/infographics/guide-prompts.md',
                     'planning/notes.md', 'test-results/browser.png', 'data/story.sqlite3'):
            with self.subTest(name=name):
                files = {name: ''}
                self.assertEqual(len(check_files(files, files.__getitem__)), 1)

    def test_links_cannot_depend_on_unpublished_files(self):
        files = {'README.md': '[Roadmap](ROADMAP.md)'}
        problems = check_files(files, files.__getitem__)
        self.assertEqual(len(problems), 1)
        self.assertIn('link target is not in the checked files', problems[0])

    def test_relative_image_links_and_encoded_names_resolve(self):
        files = {'docs/guide.md': '[Home](../README.md) ![Image](../design/my%20guide.png)',
                 'README.md': '', 'design/my guide.png': ''}
        self.assertEqual(check_files(files, files.__getitem__), [])

    def test_historical_links_anchors_and_code_examples_are_not_local_files(self):
        files = {'README.md': '[Old evidence](https://github.com/example/repo/blob/v1/check.md)\n'
                 '[Top](#top) [Email](mailto:author@example.com)\n'
                 '```md\n[Example](missing.md)\n```'}
        self.assertEqual(check_files(files, files.__getitem__), [])

    def test_source_bundle_does_not_need_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('[Guide](docs/guide.md)', encoding='utf-8')
            (root / 'docs').mkdir()
            (root / 'docs/guide.md').write_text('Read this.', encoding='utf-8')
            names, reader = inventory(root, staged=False)
            self.assertEqual(names, {'README.md', 'docs/guide.md'})
            self.assertEqual(check_files(names, reader), [])

    @unittest.skipUnless(shutil.which('git'), 'Git is required for index isolation')
    def test_staged_check_uses_index_bytes_and_not_local_fixes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git(root, 'init', '-q')
            (root / 'README.md').write_text('[Private](local.md)', encoding='utf-8')
            self.git(root, 'add', 'README.md')
            (root / 'README.md').write_text('Locally fixed.', encoding='utf-8')
            (root / 'local.md').write_text('Not staged.', encoding='utf-8')
            names, reader = inventory(root, staged=True)
            problems = check_files(names, reader)
            self.assertEqual(len(problems), 1)
            self.assertIn('local.md', problems[0])

    @unittest.skipUnless(shutil.which('git'), 'Git is required for staged deletions')
    def test_staged_deletions_and_ignored_working_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git(root, 'init', '-q')
            (root / '.gitignore').write_text('planning/\n', encoding='utf-8')
            (root / 'v100-validation.md').write_text('Old checkpoint.', encoding='utf-8')
            self.git(root, 'add', '.gitignore', 'v100-validation.md')
            self.git(root, 'rm', '--cached', '-q', 'v100-validation.md')
            (root / 'v100-validation.md').unlink()
            (root / 'planning').mkdir()
            (root / 'planning/goal.md').write_text('Local work.', encoding='utf-8')
            for staged in (False, True):
                names, reader = inventory(root, staged)
                self.assertEqual(check_files(names, reader), [])

    @staticmethod
    def git(root, *args):
        subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)

    @unittest.skipUnless(shutil.which('git'), 'Git is required for ignore rules')
    def test_ignore_rules_keep_scratch_out_and_public_docs_visible(self):
        ignored = {'v100-validation.md', 'planning/release/goal.md', 'test-results/log.txt',
                   'docs/nested/v1.0.0-evaluation.md', 'docs/nested/topic-goal.md',
                   'design/promo/example-prompt.md'}
        public = {'README.md', 'CHANGELOG.md', 'CONTRIBUTING.md', 'ROADMAP.md',
                  'SECURITY.md', 'docs/migration-compatibility.md', 'releases/v1.0.0.md'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git(root, 'init', '-q')
            source = Path(__file__).resolve().parents[1] / '.gitignore'
            (root / '.gitignore').write_bytes(source.read_bytes())
            result = subprocess.run(['git', '-C', str(root), 'check-ignore', '--no-index',
                                     '--stdin', '-z'],
                                    input=('\0'.join(sorted(ignored | public)) + '\0').encode(),
                                    capture_output=True, check=True)
            self.assertEqual(set(result.stdout.decode().split('\0')) - {''}, ignored)


if __name__ == '__main__':
    unittest.main()
