"""Read historical task heads without reintroducing specialist UI cards."""
from server.agent_switches import disabled_agents, switch_state
from server.database import decode, encode, one
from server.prompts import display_prompt, original_prompt


def saved_prompt(client, key, story_id=None):
    with client.app.state.database.connect() as connection:
        story = one(connection, 'SELECT * FROM stories WHERE id=?', (story_id,)) if story_id else None
        return {**display_prompt(original_prompt(connection, key, story)),
                'enabled': key not in disabled_agents(connection, story),
                'activation_revision': switch_state(connection)['revision']}


def pin_historical_tasks(client, story, keys):
    """Create a genuine older request before exercising a legacy archive format."""
    with client.app.state.database.connect(write=True) as connection:
        stored = one(connection, 'SELECT settings FROM stories WHERE id=?', (story['story_id'],))
        settings = decode(stored['settings'])
        pins = settings.setdefault('prompt_versions', {})
        for key in keys:
            row = one(connection, "SELECT id FROM prompt_versions WHERE key=? AND id IN (?,?) ORDER BY number DESC LIMIT 1",
                      (key, f'{key}-default-v1', f'{key}-default-v2'))
            pins[key] = row['id']
        connection.execute('UPDATE stories SET settings=? WHERE id=?', (encode(settings), story['story_id']))
