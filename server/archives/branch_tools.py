from server.branch_tools.lineage import StorySources
from server.database import decode, one
from server.errors import require


def validate_branch_tools(connection, data):
    sources = {}
    for row in data['branch_curation']:
        require(row['revision'] >= 1, 'Saved branch curation needs a published revision.')
    for row in data['branch_comparisons']:
        require(row['left_branch_id'] != row['right_branch_id'], 'A comparison needs two distinct tellings.')
        labels = decode(row['labels'])
        require(isinstance(labels, dict) and set(labels) == {'left', 'right'} and all(isinstance(value, str) and 0 < len(value) <= 200
                                                       for value in labels.values()), 'Comparison labels are invalid.')
        if row['story_id'] not in sources:
            sources[row['story_id']] = StorySources(connection, row['story_id'])
        source = sources[row['story_id']]
        for side in ('left', 'right'):
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (row[f'{side}_branch_id'],))
            require(branch['story_id'] == row['story_id'], 'A comparison crosses Story boundaries.')
            require(row[f'{side}_revision'] <= branch['revision'], 'A comparison claims a future source revision.')
            require(row[f'{side}_head_id'] is None or row[f'{side}_head_id'] in {
                node['id'] for node in source.path(branch['head_id'])}, 'A comparison head is outside its source telling.')


def upgrade_branch_tools(document):
    from server.archives.format import BRANCH_TOOL_TABLES, V39_TABLES
    if document['version'] == 39:
        require(set(document['data']) == set(V39_TABLES), 'Version 39 needs its original record groups.')
        document['data'].update({table: [] for table in BRANCH_TOOL_TABLES})
        document['version'] = 40
    return document
