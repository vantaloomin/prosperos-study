"""Pinned foreign preset shapes become inert instruction and sampling proposals."""
import math
import re
from hashlib import sha256
from pathlib import PureWindowsPath

from server.database import encode
from server.library_formats.markdown import read_json

MAX_PRESET_BYTES = 1024 * 1024
BOUNDS = {
    'temperature': (0, 2, False), 'top_p': (0, 1, False), 'top_k': (0, 1000, True),
    'min_p': (0, 1, False), 'frequency_penalty': (-2, 2, False), 'presence_penalty': (-2, 2, False),
    'repetition_penalty': (0, 3, False), 'max_output_tokens': (64, 128000, True),
}
SAME_SAMPLING = {key: key for key in BOUNDS if key != 'max_output_tokens'}
TEXT_SAMPLING = {'temp': 'temperature', 'top_p': 'top_p', 'top_k': 'top_k', 'min_p': 'min_p',
                 'rep_pen': 'repetition_penalty', 'freq_pen': 'frequency_penalty', 'presence_pen': 'presence_penalty'}
SECRET_KEYS = {'apikey', 'accesskey', 'accesstoken', 'refreshtoken', 'authorization', 'password',
               'proxypassword', 'secret', 'credentials', 'credentialref', 'token'}
NOTES = [
    'Import creates an inactive Library recipe and sampling proposals. Story pins, primary writer, provider connections and tools stay unchanged.',
    'Review instruction fragments before adding them. Foreign macros become literal text, not Study variables; foreign prompt order, roles, depth and conditions are not reproduced.',
    'Sampling values are proposals within Study limits, not equivalent behavior across models. They need an explicitly chosen local profile and provider-capability review before use.',
    'Unsupported samplers, tokenizer-specific biases, templates, prefill, stop rules, provider/model names and extensions remain source reference only.',
]


def reject_credentials(value, depth=0):
    if depth > 40:
        raise ValueError('Preset metadata is too deeply nested.')
    if isinstance(value, dict):
        for key, item in value.items():
            canonical = re.sub(r'[^a-z0-9]', '', key.lower())
            if item not in (None, '', False) and (canonical in SECRET_KEYS or canonical.endswith(('apikey', 'accesstoken', 'password', 'credentialref'))):
                raise ValueError('This preset contains an exported credential field. Remove credentials from a copy before importing; this file has not been preserved.')
            reject_credentials(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            reject_credentials(item, depth + 1)


def preset_dialect(value):
    if not isinstance(value, dict):
        raise ValueError('A generation preset must be a JSON object.')
    if 'presetVersion' in value:
        if type(value['presetVersion']) is not int or value['presetVersion'] != 3 or not isinstance(value.get('parameters'), dict):
            raise ValueError('Only the inspected NovelAI presetVersion 3 parameters envelope is supported.')
        return 'novelai-preset-v3', value['parameters'], {**SAME_SAMPLING, 'max_length': 'max_output_tokens'}
    text = all(key in value for key in ('temp', 'top_k', 'top_p', 'rep_pen'))
    chat = 'temperature' in value and any(key in value for key in ('openai_max_tokens', 'prompts', 'prompt_order'))
    if text == chat:
        raise ValueError('This preset is ambiguous or unsupported. Choose a SillyTavern text/chat completion export or NovelAI v3 preset.')
    return ('sillytavern-text-preset', value, TEXT_SAMPLING) if text else ('sillytavern-chat-preset', value, {**SAME_SAMPLING, 'openai_max_tokens': 'max_output_tokens'})


def sampling_proposals(values, mapping):
    rows = []
    for key, target in mapping.items():
        if key not in values:
            continue
        value = values[key]
        low, high, integer = BOUNDS[target]
        valid = type(value) in (int, float) and (type(value) is int or math.isfinite(value)) and low <= value <= high
        valid = valid and (not integer or type(value) is int) and (target != 'repetition_penalty' or value > 0)
        rows.append({'source': key, 'target': target, 'value': value, 'supported': valid,
                     'note': 'Proposed; local provider and model support must be reviewed.' if valid else 'Outside the supported native type/range; kept as reference without clamping.'})
    return rows


def instruction_candidates(value, dialect):
    # Text-completion sampling exports and NovelAI v3 parameters have no portable
    # instruction schema here. Their templates/extensions remain exact source data.
    if dialect != 'sillytavern-chat-preset':
        return []
    candidates = [instruction(key, key.replace('_', ' '), value[key])
                  for key in ('main_prompt', 'nsfw_prompt', 'jailbreak_prompt', 'impersonation_prompt', 'continue_nudge_prompt') if key in value]
    prompts = value.get('prompts', [])
    if not isinstance(prompts, list) or len(prompts) > 128:
        raise ValueError('A chat preset can contain at most 128 prompt records.')
    for index, row in enumerate(prompts):
        if not isinstance(row, dict):
            raise ValueError('Chat preset prompts must be objects.')
        if 'content' in row:
            candidates.append(instruction(f'prompts[{index}]', str(row.get('name') or row.get('identifier') or f'Prompt {index + 1}'), row['content']))
    return [item for item in candidates if item is not None]


def instruction(key, label, text):
    if not isinstance(text, str) or '\x00' in text:
        raise ValueError('Preset instruction fields must be text without NUL characters.')
    if text.strip():
        return {'key': key, 'label': label[:200], 'text': text, 'supported': len(literal_instructions(text)) <= 12000}
    return None


def literal_instructions(text):
    return text.replace('{{', '{{{{').replace('}}', '}}}}')


def convert_preset(filename, source):
    if len(source) > MAX_PRESET_BYTES:
        raise ValueError('Generation presets are limited to 1 MiB.')
    value = read_json(source.decode('utf-8-sig'))
    dialect, parameters, mapping = preset_dialect(value)
    reject_credentials(value)
    name = value.get('name') or PureWindowsPath(filename).stem
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise ValueError('Preset names must contain 1–120 characters.')
    sampling = sampling_proposals(parameters, mapping)
    instructions = instruction_candidates(value, dialect)
    if not sampling and not instructions:
        raise ValueError('This preset has no recognized instruction or sampling proposals.')
    content = {'instructions': instructions, 'sampling': sampling}
    return {'converter_version': 1, 'format': dialect, 'name': name.strip(), **content,
            'notes': NOTES, 'source_fields': sorted(value),
            'parameter_fields': sorted(parameters), 'source_sha256': sha256(source).hexdigest(),
            'content_sha256': sha256(encode(content).encode()).hexdigest()}
