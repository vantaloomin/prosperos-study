import json

import pytest

from server.migration.preset_conversion import convert_preset, literal_instructions
from server.writing.resources import parse_content
from server.writing.variables import render


def convert(value):
    return convert_preset('Example.json', json.dumps(value).encode())


def test_text_preset_maps_bounded_sampling_without_guessing_instruction_authority():
    value = {'temp': .8, 'top_k': 40, 'top_p': .9, 'rep_pen': 1.1, 'freq_pen': .3, 'presence_pen': .1,
             'sampler_order': [6, 0, 1], 'dynatemp': True, 'system_prompt': 'Not a portable instruction field'}
    result = convert(value)
    assert result['format'] == 'sillytavern-text-preset' and result['instructions'] == []
    assert {row['target']: row['value'] for row in result['sampling'] if row['supported']} == {
        'temperature': .8, 'top_p': .9, 'top_k': 40, 'repetition_penalty': 1.1, 'frequency_penalty': .3, 'presence_penalty': .1}
    assert 'sampler_order' in result['source_fields'] and 'dynatemp' in result['source_fields']


def test_chat_preset_preserves_macros_as_literal_native_recipe_text():
    instruction = 'Write {{char}} beside {{user}}. {{roll 1d20}} {{unknown}}'
    result = convert({'temperature': .7, 'openai_max_tokens': 800, 'prompts': [
        {'identifier': 'main', 'name': 'Main', 'content': instruction, 'injection_depth': 2}],
        'prompt_order': [{'character_id': 100001, 'order': [{'identifier': 'main', 'enabled': False}]}]})
    candidate = result['instructions'][0]
    assert candidate['text'] == instruction and candidate['supported']
    native = parse_content('recipe', {'instructions': literal_instructions(instruction)})
    assert native['variables'] == [] and native['steps'] == [] and native['randomness'] is None
    assert render(native['instructions'], {}) == instruction
    assert 'prompt_order' in result['source_fields']


def test_novelai_v3_sampling_keeps_unsupported_engine_semantics_visible():
    result = convert({'presetVersion': 3, 'name': 'Quiet', 'parameters': {
        'temperature': .6, 'max_length': 160, 'top_p': .9, 'repetition_penalty': 1.4,
        'order': [{'id': 'temperature', 'enabled': True}], 'repetition_penalty_range': 512,
        'repetition_penalty_frequency': .8, 'tail_free_sampling': .9}})
    assert result['format'] == 'novelai-preset-v3' and result['name'] == 'Quiet'
    targets = {row['target']: row['value'] for row in result['sampling']}
    assert targets['max_output_tokens'] == 160 and 'frequency_penalty' not in targets
    assert 'repetition_penalty_frequency' in result['parameter_fields']


@pytest.mark.parametrize('value', [-1, 1001, 2.5, True, '40', pytest.param(10**400, id='huge-int')])
def test_out_of_range_or_wrong_type_stays_reference_without_coercion(value):
    result = convert({'temp': .8, 'top_k': value, 'top_p': .9, 'rep_pen': 1.1})
    proposal = next(row for row in result['sampling'] if row['target'] == 'top_k')
    assert not proposal['supported'] and proposal['value'] == value


@pytest.mark.parametrize('key', ['api_key', 'apiKey', 'proxy_password', 'Authorization', 'openai_api_key', 'credential_ref'])
def test_exports_with_credentials_are_rejected_before_preservation(key):
    with pytest.raises(ValueError, match='credential field'):
        convert({'temp': .8, 'top_k': 40, 'top_p': .9, 'rep_pen': 1.1, 'extensions': {key: 'SECRET'}})


@pytest.mark.parametrize('value', [
    {'presetVersion': 4, 'parameters': {}}, {'presetVersion': True, 'parameters': {}},
    {'temperature': .7}, {'temp': .7, 'top_k': 40, 'top_p': .9, 'rep_pen': 1.1, 'temperature': .7, 'prompts': []},
    {'temperature': .7, 'prompts': [False]}, {'temperature': .7, 'prompts': [{'content': {}}]},
])
def test_ambiguous_and_unsupported_shapes_reject(value):
    with pytest.raises(ValueError):
        convert(value)


def test_preset_size_and_nested_metadata_are_bounded():
    with pytest.raises(ValueError, match='1 MiB'):
        convert_preset('oversized.json', b'x' * (1024 * 1024 + 1))
    value = {}
    for _ in range(42):
        value = {'nested': value}
    with pytest.raises(ValueError, match='deeply nested'):
        convert({'temp': .8, 'top_k': 40, 'top_p': .9, 'rep_pen': 1.1, 'extensions': value})
