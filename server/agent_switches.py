"""Workspace agent switches affect new work without changing recorded prompts."""
from server.database import decode, encode
from server.errors import require
from server.roles import LEGACY_KEYS


def switch_state(connection):
    row = connection.execute("SELECT value FROM preferences WHERE key='agent_switches'").fetchone()
    return decode(row['value']) if row else {'revision': 0, 'disabled': []}


def disabled_agents(connection, story=None):
    disabled = set(switch_state(connection)['disabled'])
    settings = decode(story['settings']) if story else {}
    inherited = settings.get('disabled_prompts', [])
    if isinstance(inherited, list):
        disabled.update(key for key in inherited if isinstance(key, str))
    disabled.update(key for key, role in LEGACY_KEYS.items() if role in disabled)
    return disabled


def agent_enabled(connection, key, story=None):
    return key not in disabled_agents(connection, story)


def require_agent(connection, key, story=None):
    require(agent_enabled(connection, key, story),
            f'The {key} agent is disabled in {"Settings > Prompts" if enabled_source(connection, key, story) == "workspace" else "Story setup > Agents"}. Enable it before requesting this work.', 409)


def enabled_source(connection, key, story=None):
    if key in disabled_agents(connection):
        return 'workspace'
    return 'story' if key in disabled_agents(connection, story) else 'on'


def set_agent(connection, key, enabled, expected_revision):
    return set_agents(connection, [key], enabled, expected_revision)


def set_agents(connection, keys, enabled, expected_revision):
    current = switch_state(connection)
    require(current['revision'] == expected_revision, 'Agent switches changed. Refresh and try again.', 409)
    disabled = set(current['disabled'])
    disabled.difference_update(keys) if enabled else disabled.update(keys)
    next_state = {'revision': current['revision'] + 1, 'disabled': sorted(disabled)}
    connection.execute("INSERT INTO preferences VALUES ('agent_switches',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (encode(next_state),))
    return next_state
