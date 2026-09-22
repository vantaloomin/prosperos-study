from server.errors import DomainError, require


def utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


def index_at(text, position):
    raw = text.encode('utf-16-le')
    require(0 <= position <= len(raw) // 2, 'The selected range is outside this text.', 409)
    try:
        return len(raw[:position * 2].decode('utf-16-le'))
    except UnicodeDecodeError:
        raise DomainError('The selection splits a Unicode character. Select the complete character.', 400) from None


def apply_selection(text, selection, action, replacement):
    require(selection.end >= selection.start, 'The selected range is reversed.')
    start, end = index_at(text, selection.start), index_at(text, selection.end)
    require(text[start:end] == selection.text, 'The selected text changed. Review a fresh selection.', 409)
    if action == 'update':
        require(start == 0 and end == len(text), 'Updating a field requires its complete text selection.')
    if action == 'add':
        require(start == end == len(text), 'Adding text requires a caret at the end of the target.')
    if action == 'insert-before':
        end = start
    elif action == 'insert-after':
        start = end
    return text[:start] + replacement + text[end:]


def whole_text(text):
    return {'start': 0, 'end': utf16_length(text), 'text': text}
