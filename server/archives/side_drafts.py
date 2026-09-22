from server.archives.format import V45_TABLES
from server.errors import require


def upgrade_side_drafts(document):
    if document['version'] == 45:
        require(set(document['data']) == set(V45_TABLES), 'Version 45 needs its original record groups.')
        document['data']['side_drafts'] = []
        document['version'] = 46
    return document
