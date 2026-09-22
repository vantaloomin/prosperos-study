from server.archives.format import SIDE_ORGANIZATION_TABLES, V40_TABLES
from server.errors import require


def upgrade_side_organization(document):
    if document['version'] == 40:
        require(set(document['data']) == set(V40_TABLES), 'Version 40 needs its original record groups.')
        document['data'].update({table: [] for table in SIDE_ORGANIZATION_TABLES})
        document['version'] = 41
    return document
