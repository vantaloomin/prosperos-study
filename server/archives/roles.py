"""Validate the role and task contract without rewriting recorded requests."""
from server.database import decode
from server.errors import require
from server.roles import TASKS, role_key
from server.workflow.readers import validate_reader_contract


def validate_role_snapshot(snapshot, step):
    require(snapshot['step'] == step, 'A saved task differs from its recorded step.')
    expected = role_key(step)
    if 'role' not in snapshot:
        require(snapshot['prompt']['key'] == step, 'A legacy task has a different prompt role.')
        return
    require(snapshot['role'] == expected and snapshot['prompt']['key'] in {step, expected},
            'A saved task uses an unrelated consolidated role.')
    validate_reader_contract(decode(snapshot['content']), step)
    if step in TASKS:
        _, field, value = TASKS[step]
        require(decode(snapshot['content']).get(field) == value, 'A consolidated task lost its discriminator.')
