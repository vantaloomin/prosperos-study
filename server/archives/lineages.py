"""Join released v0.7 and development memory archives without conflating their versions."""
from server.archives.format import TABLES, V31_TABLES, V32_TABLES, V33_TABLES, V36_TABLES
from server.errors import require
from server.prompts import DEFAULT_PROMPTS, LEGACY_PROMPT_LABELS
from server.role_prompts import ROLE_PROMPTS
from server.section_prompts import SECTION_PROMPTS


def lineage_shapes(version):
    legacy = set(LEGACY_PROMPT_LABELS)
    roles = legacy | set(ROLE_PROMPTS)
    complete = roles | set(SECTION_PROMPTS)
    # 32/33 were independently assigned on two branches. Both record groups and
    # prompt heads must match a complete known shape before adding anything.
    shapes = {
        31: [(set(V31_TABLES), legacy)],
        32: [(set(V31_TABLES), roles), (set(V32_TABLES), legacy)],
        33: [(set(V31_TABLES) | {'manuscripts'}, complete), (set(V33_TABLES), legacy)],
        34: [(set(V36_TABLES), legacy)],
        35: [(set(V36_TABLES), legacy)],
        36: [(set(V36_TABLES), legacy)],
    }
    return shapes.get(version, [])


def upgrade_lineages(document):
    version = document['version']
    if version >= 37:
        return document
    actual = (set(document['data']), set(document['prompt_heads']))
    require(actual in lineage_shapes(version), f'Version {version} needs its original record groups and supported prompts.')
    for table in TABLES:
        document['data'].setdefault(table, [])
    templates = {**DEFAULT_PROMPTS, **ROLE_PROMPTS, **SECTION_PROMPTS}
    for key in sorted(set(templates) - set(document['prompt_heads'])):
        identity = f'{key}-archive-upgrade-v{version}-integrated'
        document['data']['prompt_versions'].append({'id': identity, 'key': key, 'number': 1,
            'template': templates[key], 'created_at': document['created_at']})
        document['prompt_heads'][key] = identity
    document['version'] = 37
    return document
