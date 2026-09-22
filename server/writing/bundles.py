import hashlib
import json

from pydantic import ValidationError

from server.database import encode
from server.errors import DomainError, require
from server.operations import previous, remember
from server.writing.bundle_content import supported_content
from server.writing.bundle_links import (
    dependency_slots,
    local_options,
    map_content,
    resolve_mapping,
)
from server.writing.bundle_models import MAX_BUNDLE, Bundle
from server.writing.extras import validate_extras
from server.writing.models import ResourceCreate
from server.writing.resources import create_in, validate_links


def read_bundle(document):
    try:
        require(len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode('utf-8')) <= MAX_BUNDLE,
                'Writing bundles are limited to 8 MiB.')
        bundle = Bundle.model_validate(document)
        keys = [item.key for item in [*bundle.resources, *bundle.references]]
        require(len(keys) == len(set(keys)) and not {'none', 'inherit'} & set(keys),
                'Use distinct, non-reserved resource and dependency keys.')
        require(bundle.root in {item.key for item in bundle.resources}, 'The bundle root resource is missing.')
        return bundle
    except (ValidationError, ValueError, TypeError, RecursionError) as error:
        raise DomainError(f'Invalid writing bundle: {str(error)[:1000]}', 400) from None


def bundle_items(bundle):
    result = []
    for item in bundle.resources:
        content, extras = supported_content(item)
        if item.key == bundle.root:
            extras.update({f'bundle.{key}': value for key, value in bundle.model_extra.items()})
            extras.update({f'bundle.unsupported.{key}': value for key, value in bundle.unsupported.items()})
            for reference in bundle.references:
                extras.update({f'reference.{reference.key}.{key}': value for key, value in reference.model_extra.items()})
        result.append({key: getattr(item, key) for key in ('key', 'kind', 'name', 'description', 'note')}
                      | {'content': content, 'unsupported': validate_extras(extras)})
    root = next(item for item in result if item['key'] == bundle.root)
    needed = {bundle.root}
    if root['kind'] == 'recipe':
        needed.add(root['content']['style'])
    require({item['key'] for item in result} <= needed, 'Include only the root resource and its explicit style dependency.')
    return result


def prepare_bundle(connection, body):
    bundle = read_bundle(body.document)
    items = bundle_items(bundle)
    references = {item.key: item for item in bundle.references}
    dependency_slots(items, references)
    require(set(body.mappings) <= set(references), 'Unknown dependency mapping.')
    dependencies, mapped, versions, errors = [], {}, {}, []
    for reference in bundle.references:
        status = {'key': reference.key, 'kind': reference.kind, 'name': reference.name,
                  'table_id': reference.table_id, 'mapped': reference.key in body.mappings}
        if status['mapped']:
            try:
                identity, label, selected_version = resolve_mapping(connection, reference, body.mappings[reference.key])
                mapped[reference.key] = identity
                versions[reference.key] = selected_version
                status['selected_name'] = label
            except DomainError as error:
                errors.append(f'{reference.name}: {error.message}')
        else:
            errors.append(f'Choose a local mapping for {reference.name}.')
        dependencies.append(status)
    if not errors:
        errors.extend(configuration_errors(connection, items, mapped))
    digest = hashlib.sha256(encode([body.document, body.mappings, versions]).encode('utf-8')).hexdigest()
    report = {'fingerprint': digest, 'root': bundle.root, 'resources': items,
              'dependencies': dependencies, 'options': local_options(connection), 'errors': errors,
              'unsupported': [{'resource': item['name'], 'fields': sorted(item['unsupported'])}
                              for item in items if item['unsupported']],
              'omitted_samples': bundle.omitted_samples, 'can_import': not errors,
              'activation': 'Imports create Library versions only. Story pins, model defaults, and automation stay unchanged.'}
    return report, mapped


def configuration_errors(connection, items, mapped):
    errors = []
    # Included styles are validated resources, but do not have local IDs until import.
    included = {item['key']: 'none' for item in items if item['kind'] == 'style'}
    for item in items:
        try:
            validate_links(connection, item['kind'], map_content(item, mapped, included))
        except DomainError as error:
            errors.append(f"{item['name']}: {error.message}")
    return errors


def import_bundle(database, body):
    payload = body.model_dump()
    with database.connect(write=True) as connection:
        saved = previous(connection, body.operation_id, 'writing-bundle-import', payload)
        if saved is not None:
            return saved
        report, mapped = prepare_bundle(connection, body)
        require(report['can_import'], 'Resolve bundle compatibility issues before importing.')
        require(report['fingerprint'] == body.preview_fingerprint,
                'The bundle or local dependencies changed. Preview the import again.', 409)
        identities, imported = {}, []
        for item in sorted(report['resources'], key=lambda item: item['kind'] != 'style'):
            resource = create_in(connection, ResourceCreate(operation_id=body.operation_id,
                kind=item['kind'], name=item['name'], description=item['description'], note=item['note'],
                content=map_content(item, mapped, identities), unsupported=item['unsupported']))
            identities[item['key']] = resource['id']
            imported.append(resource)
        return remember(connection, body.operation_id, 'writing-bundle-import', payload,
                        {'root_version_id': identities[report['root']], 'resources': imported,
                         'unsupported': report['unsupported'], 'activation': report['activation']})
