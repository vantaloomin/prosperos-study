from hashlib import sha256
from pathlib import PurePosixPath

from server.errors import DomainError
from server.library_formats.artwork import decode_image, prepare_artwork
from server.library_formats.card_lore import issue
from server.library_formats.containers import read_container, safe_member

SUPPORTED_IMAGES = {'.png', '.jpg', '.jpeg', '.webp'}


def inspect_asset(members, path, label, kind, issues):
    result = {'label': label[:200], 'kind': kind[:100], 'uri': path, 'status': 'reference', 'reason': ''}
    safe_member(path)
    result['path'] = path
    if path not in members:
        result.update(status='missing', reason='Referenced file is absent from the container.')
    elif PurePosixPath(path).suffix.lower() not in SUPPORTED_IMAGES:
        result['reason'] = 'Preserved for download; this media type is not rendered or executed.'
    else:
        result = inspect_image(result, members[path])
    if result['reason']:
        issue(issues, path, result['reason'])
    return result


def inspect_image(result, source):
    try:
        image = decode_image(source)
        return {**result, 'status': 'image', 'sha256': sha256(source).hexdigest(),
                'width': image.width, 'height': image.height}
    except DomainError as error:
        return {**result, 'status': 'reference', 'reason': 'Image retained only as a source: ' + error.message}


def charx_assets(members, definitions, issues):
    if not isinstance(definitions, list) or len(definitions) > 64:
        raise ValueError('A character container may declare up to 64 assets.')
    result = []
    for asset in definitions:
        if not isinstance(asset, dict) or any(not isinstance(asset.get(key), str) for key in ('uri', 'name', 'type', 'ext')):
            raise ValueError('Each CHARX asset needs text uri, name, type and ext fields.')
        uri = asset['uri']
        if uri.startswith('embeded://'):
            result.append({**inspect_asset(members, uri[len('embeded://'):], asset['name'], asset['type'], issues), 'uri': uri})
        else:
            result.append({'uri': uri, 'label': asset['name'][:200], 'kind': asset['type'][:100], 'status': 'reference',
                           'reason': 'External, default and unsupported asset URIs remain reference data. Nothing is fetched.'})
            issue(issues, uri, result[-1]['reason'])
    return result


def propose_artwork(converted):
    images = [asset for asset in converted['assets'] if asset['status'] == 'image']
    if images:
        portrait = next((asset for asset in images if asset['kind'] == 'icon'), images[0])
        converted['drafts'][0]['content']['artwork_sha256'] = portrait['sha256']
    issue(converted['issues'], 'assets', 'Supported embedded images can be chosen as artwork below. Other media and unlisted files stay in the original container. Artwork is never sent to the writer.')
    return converted


def imported_artwork(source, conversion):
    if conversion['format'] == 'png-card':
        return [prepare_artwork(source)]
    if conversion['format'] not in {'charx', 'byaf'}:
        return []
    members = read_container(source)
    paths = {asset['path'] for asset in conversion['assets'] if asset['status'] == 'image'}
    return [prepare_artwork(members[path]) for path in sorted(paths)]


def artwork_references(row, conversion):
    if conversion['format'] == 'png-card':
        return {row['source_sha256']}
    return {asset['sha256'] for asset in conversion.get('assets', []) if asset['status'] == 'image'}
