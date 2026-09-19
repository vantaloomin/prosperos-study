"""Conservative proposals; native activation semantics still require author review."""
import re

KEY_FIELDS = {'sillytavern-lorebook': 'key', 'agnai-lorebook': 'keywords', 'risu-lorebook': 'key'}
ALWAYS_FIELDS = {'novelai-lorebook': 'forceActivation', 'risu-lorebook': 'alwaysActive'}


def native_keywords(fields, source_format):
    keys = fields.get(KEY_FIELDS.get(source_format, 'keys'), [])
    if source_format == 'risu-lorebook' and isinstance(keys, str):
        keys = [term.strip() for term in keys.split(',') if term.strip()]
    regex = fields.get('use_regex', fields.get('useRegex', False)) in (True, 'true')
    if source_format in {'sillytavern-lorebook', 'novelai-lorebook', 'risu-lorebook'} and isinstance(keys, list):
        regex = regex or any(isinstance(key, str) and re.fullmatch(r'/.*?/[a-z]*', key) for key in keys)
    if source_format == 'novelai-lorebook' and isinstance(keys, list):
        regex = regex or any(isinstance(key, str) and '&' in key for key in keys)
    # Never turn a partially supported condition into an apparently complete rule.
    keys = [] if regex else keys
    constant = fields.get(ALWAYS_FIELDS.get(source_format, 'constant'), False) in (True, 'true')
    return keys, constant
