from pydantic import ValidationError

from server.database import identifier, now
from server.errors import DomainError, require
from server.profiles import Profiles, profile_snapshot
from server.providers.config import ProfileCreate, SavedProfileConfig


def configuration_proposal(connection, conversion, body):
    keys = body.sampling_keys
    require(len(keys) == len(set(keys)), 'Choose each sampling proposal once.')
    available = {item['target']: item for item in conversion['sampling'] if item['supported']}
    require(set(keys) <= set(available), 'Only supported sampling proposals can be selected.')
    if not keys:
        require(body.base_profile_id is None and body.expected_profile_version_id is None,
                'Clear the model selection when retaining all sampling values as proposals.')
        return {'config': None, 'changes': [], 'base_name': ''}
    require(body.base_profile_id is not None and body.expected_profile_version_id is not None,
            'Choose a local model profile to review these sampling values.')
    base = profile_snapshot(connection, body.base_profile_id)
    require(base['id'] == body.expected_profile_version_id, 'The selected model profile changed. Review its current version.', 409)
    proposed = {key: available[key]['value'] for key in keys}
    try:
        config = SavedProfileConfig.model_validate({**base['config'], **proposed}).model_dump()
    except ValidationError as error:
        raise DomainError('This local profile cannot use the selected proposals: ' + '; '.join(item['msg'] for item in error.errors()), 400) from None
    return {'config': config, 'changes': [{'field': key, 'before': base['config'].get(key), 'after': value} for key, value in proposed.items()],
            'base_name': base['name']}


def copy_configuration(connection, database, proposal, name):
    if proposal['config'] is None:
        return None
    identity = identifier()
    connection.execute('INSERT INTO profiles VALUES (?,NULL,?)', (identity, now()))
    # No credential is copied and no foreign connection field is used. This new
    # model profile is never made primary or assigned to a Story/recipe.
    body = ProfileCreate(name=(name + ' · imported sampling')[:120], config=proposal['config'], make_primary=False)
    return Profiles(database, None)._publish(connection, identity, 1, body, None)
