"""Preserve embedded card lore as editable Markdown entry files."""
from server.library_formats.markdown import document


def issue(report, path, message):
    report.append({'path': path, 'message': message})


def entry_issues(entry, index, report):
    path = f'data.character_book.entries[{index}]'
    if entry.get('use_regex'):
        issue(report, path + '.use_regex', 'Regex activation needs compatibility review; no regex is executed.')
    if any(line.lstrip().startswith('@@') for line in entry['content'].splitlines()):
        issue(report, path + '.content', 'V3 decorators are preserved literally and need activation review.')
    if entry.get('extensions'):
        issue(report, path + '.extensions', 'Extension rules are preserved without assuming their runtime meaning.')


def entry_files(entries, report):
    files, references = {}, []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get('content'), str):
            raise ValueError(f'Lore entry {index + 1} must be an object with string content.')
        entry_issues(entry, index, report)
        path = f'lorebook/entries/{index + 1:04d}.md'
        references.append(path)
        metadata = {key: value for key, value in entry.items() if key != 'content'}
        files[path] = document({'kind': 'lore-entry', 'source_index': index,
                                'source_fields': metadata}, entry['content'])
    return files, references


def convert_lore(book, report):
    if not isinstance(book, dict) or not isinstance(book.get('entries'), list):
        raise ValueError('character_book must be an object containing an entries array.')
    if len(book['entries']) > 5000:
        raise ValueError('Use at most 5,000 entries per conversion package.')
    description = book.get('description', '')
    if not isinstance(description, str):
        raise ValueError('The lorebook description must be text.')
    files, references = entry_files(book['entries'], report)
    metadata = {key: value for key, value in book.items() if key not in {'entries', 'description'}}
    files['lorebook/book.md'] = document({'kind': 'lorebook', 'source_fields': metadata,
                                         'entries': references}, description)
    issue(report, 'data.character_book', 'Activation, ordering and budget fields are retained for review; '
          'conversion does not activate entries or attach this book to a Story.')
    if book.get('recursive_scanning'):
        issue(report, 'data.character_book.recursive_scanning', 'Recursive scanning needs explicit compatibility review.')
    return files
