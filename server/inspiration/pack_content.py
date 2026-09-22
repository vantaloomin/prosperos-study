import json
from hashlib import sha256

from pydantic import ValidationError

from server.errors import DomainError, require
from server.inspiration.models import Card, DeckContent
from server.inspiration.pack_models import Pack
from server.library_formats.import_conversion import source_bytes
from server.library_formats.markdown import read_json
from server.writing.extras import PRIVATE_KEYS, validate_extras

MAX_PACK_BYTES = 8 * 1024 * 1024


def content_hash(content):
    return sha256(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def private_fields(value, depth=0):
    require(depth <= 40, 'Inspiration packs support at most 40 nested metadata levels.')
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.rsplit('.', 1)[-1].casefold().replace('-', '_')
            if normalized in PRIVATE_KEYS:
                require(item in (None, '', '[private connection field omitted]'), 'Remove private connection fields before importing this pack.')
            private_fields(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            private_fields(item, depth + 1)


def read_pack(source_base64):
    try:
        source = source_bytes(source_base64)
        require(len(source) <= MAX_PACK_BYTES, 'Inspiration packs are limited to 8 MiB.')
        document = read_json(source.decode('utf-8-sig'))
        require(isinstance(document, dict) and type(document.get('version')) is int, 'A pack needs an integer format version.')
        private_fields(document)
        pack = Pack.model_validate(document)
        require(len({item.key for item in pack.decks}) == len(pack.decks), 'Use each pack deck key once.')
        return source, pack, [convert_item(pack, item) for item in pack.decks]
    except (ValueError, TypeError, RecursionError, UnicodeError, ValidationError) as error:
        raise DomainError(f'Invalid inspiration pack: {str(error)[:1000]}', 400) from None


def convert_item(pack, item):
    raw_cards = item.content.get('cards')
    require(isinstance(raw_cards, list) and all(isinstance(card, dict) for card in raw_cards), 'A deck needs a list of card objects.')
    cards = [{key: value for key, value in card.items() if key in Card.model_fields} for card in raw_cards]
    content = DeckContent.model_validate({'cards': cards}).model_dump()
    extras = {**item.unsupported,
              **{f'pack.{key}': value for key, value in pack.model_extra.items()},
              **{f'pack.unsupported.{key}': value for key, value in pack.unsupported.items()},
              **{f'deck.{key}': value for key, value in item.model_extra.items()},
              **{f'content.{key}': value for key, value in item.content.items() if key != 'cards'}}
    for raw, card in zip(raw_cards, content['cards'], strict=True):
        extras.update({f"card.{card['id']}.{key}": value for key, value in raw.items() if key not in Card.model_fields})
    return {'key': item.key, 'name': item.name, 'description': item.description, 'content': content,
            'unsupported': validate_extras(extras), 'content_sha256': content_hash(content)}
