"""Text-only transcript dialects. Source metadata is never instruction authority."""
import re
from hashlib import sha256
from pathlib import PureWindowsPath

from server.database import encode
from server.library_formats.cards import MAX_SOURCE_BYTES
from server.library_formats.markdown import read_json

MAX_MESSAGES = 2000
PROTECTED_ROLES = {'system', 'developer', 'tool', 'function'}
ROLE_PROPOSALS = {'user': 'user', 'human': 'user', 'assistant': 'assistant', 'narrator': 'narrator', 'ooc': 'ooc'}
NOTES = [
    'Only reviewed message selections become a new Story, in source order. Existing Stories are unchanged.',
    'System, developer, tool and function messages are reference only. Metadata, hidden reasoning, attachments and unselected alternatives stay in the original file.',
    'Source timestamps are provenance labels, not trusted dates or new Story event times. Macros and markup stay literal; no model runs during import.',
]


def bounded_text(value, label, maximum=100000):
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
        raise ValueError(f'{label} must be text without NUL characters, at most {maximum:,} characters.')
    return value


def message(index, speaker, role, text, timestamp='', alternatives=None, protected=False):
    speaker = bounded_text(speaker, 'Speaker label', 200)
    role = bounded_text(role, 'Source role', 100)
    timestamp = bounded_text(str(timestamp) if timestamp is not None else '', 'Source timestamp', 200)
    variants = [bounded_text(text, 'Message')]
    if alternatives is not None:
        if not isinstance(alternatives, list) or len(alternatives) > 100:
            raise ValueError('A message can contain at most 100 text alternatives.')
        for variant in alternatives:
            value = bounded_text(variant, 'Alternative reply')
            if value not in variants:
                variants.append(value)
    protected = protected or role.strip().lower() in PROTECTED_ROLES
    proposed = 'skip' if protected else ROLE_PROPOSALS.get(role.strip().lower(), 'skip')
    return {'index': index, 'speaker': speaker or 'Unassigned', 'source_role': role,
            'timestamp': timestamp, 'variants': variants, 'protected': protected,
            'proposed_role': proposed if variants[0].strip() else 'skip'}


def sillytavern(records):
    if len(records) < 2 or not isinstance(records[0], dict) or 'mes' in records[0] or not any(key in records[0] for key in ('chat_metadata', 'user_name', 'character_name')):
        raise ValueError('SillyTavern JSONL needs its export header followed by message records.')
    messages = []
    for row in records[1:]:
        if not isinstance(row, dict) or type(row.get('is_user')) is not bool or type(row.get('is_system', False)) is not bool:
            raise ValueError('Each SillyTavern message needs a text mes field and boolean is_user/is_system flags.')
        role = 'system' if row.get('is_system') else 'user' if row['is_user'] else 'assistant'
        messages.append(message(len(messages), row.get('name', ''), role, row.get('mes'), row.get('send_date', ''), row.get('swipes')))
    return messages


def role_messages(value):
    rows = value.get('messages') if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise ValueError('Choose a role/content message array or an object with a messages array.')
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('role'), str):
            raise ValueError('Each JSON message needs an explicit role and text content.')
        result.append(message(len(result), row.get('name', row['role']), row['role'], row.get('content'), row.get('timestamp', ''), row.get('alternatives')))
    return result


def text_messages(text):
    # Recognized boundaries are proposals only: every text block initially stays skipped.
    # The author maps speakers explicitly, including an unlabelled preface or manuscript.
    heading = re.compile(r'^#{2,6}\s+([^\r\n]{1,200}?)\s*$')
    label = re.compile(r'^([\w][\w .\-\'’()]{0,99}):[ \t]*(.*)$')
    result, speaker, lines = [], 'Unassigned', []

    def flush():
        text = ''.join(lines).strip()
        if text:
            result.append(message(len(result), speaker, 'unmapped', text))

    for line in text.splitlines(keepends=True):
        match = heading.match(line) or label.match(line)
        if match:
            flush()
            speaker = match[1].strip()
            lines = [match[2] + ('\n' if line.endswith('\n') else '')] if match.lastindex == 2 else []
        else:
            lines.append(line)
    flush()
    return result


def convert_transcript(filename, source):
    if len(source) > MAX_SOURCE_BYTES:
        raise ValueError('Transcripts are limited to 10 MiB per file.')
    text = source.decode('utf-8-sig')
    suffix = PureWindowsPath(filename).suffix.lower()
    if suffix in {'.txt', '.md', '.markdown'}:
        messages, dialect = text_messages(text), 'text-transcript'
    elif suffix == '.jsonl':
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) > MAX_MESSAGES + 1:
            raise ValueError('Transcripts are limited to 2,000 messages.')
        messages, dialect = sillytavern([read_json(line) for line in lines]), 'sillytavern-jsonl'
    else:
        messages, dialect = role_messages(read_json(text)), 'role-content-json'
    if not 1 <= len(messages) <= MAX_MESSAGES:
        raise ValueError('Choose a transcript containing 1–2,000 messages.')
    if sum(len(text) for row in messages for text in row['variants']) > 5_000_000:
        raise ValueError('A transcript can contain at most 5 million characters including alternatives.')
    notes = NOTES + (['Text boundaries are proposed from speaker labels or Markdown headings. Review every boundary and map speakers; no roles are inferred.'] if dialect == 'text-transcript' else [])
    # This hash indicates equivalent mapped message content, not equivalent hidden metadata.
    content = [{key: row[key] for key in ('speaker', 'source_role', 'variants', 'protected')} for row in messages]
    return {'converter_version': 1, 'format': dialect, 'messages': messages, 'notes': notes,
            'source_sha256': sha256(source).hexdigest(), 'content_sha256': sha256(encode(content).encode()).hexdigest()}
