"""Live reference links are distinct from immutable provider-input identities."""
from server.errors import require


def source_link(source):
    identity = ('node_id',) if 'node_id' in source else ('asset_id', 'version_id', 'field')
    link = {key: source[key] for key in ('id', 'start', 'end', 'sha256', *identity)}
    return {**link, **{'frozen_' + key: source[key] for key in identity if key != 'field'}}


def evidence_key(source):
    identity = source.get('node_id') or (source.get('asset_id'), source.get('version_id'), source.get('field'))
    return (identity, source['start'], source['end'], source['sha256'])


def restored_source(source, links):
    link = links.get(evidence_key(source))
    require(link is not None, 'A character evidence source has no preserved live link.')
    identity = ('node_id',) if 'node_id' in source else ('asset_id', 'version_id')
    frozen = {**source, **{key: link['frozen_' + key] for key in identity}}
    original = source_identity(frozen)
    expected_id = chunk_identity(original, source)
    require(link['id'] == expected_id, 'A character evidence identity was altered.')
    return {**frozen, 'id': link['id'], 'source_id': original}


def source_identity(source):
    if 'node_id' in source:
        return 'message:' + source['node_id']
    return f"version:{source['version_id']}:field:{source['field']}"


def chunk_identity(source_id, source):
    return f"{source_id}@{source['start']}:{source['end']}:{source['sha256'][:12]}"
