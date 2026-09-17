"""Convert a card for review: python -m scripts.convert_character_card card.json new-folder."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from server.library_formats.cards import MAX_SOURCE_BYTES, convert_card


def write_package(result: dict, destination: Path):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError('Choose a new output directory; existing files are never overwritten.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.card-conversion-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'package'
        stage.mkdir()
        for name, text in result['files'].items():
            target = stage / name
            if not target.resolve().is_relative_to(stage.resolve()):
                raise ValueError('Invalid conversion output path.')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode('utf-8'))
        (stage / 'source.json').write_bytes(result['original'])
        report = {key: value for key, value in result.items() if key not in {'files', 'original'}}
        report['files'] = list(result['files'])
        (stage / 'conversion-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        stage.rename(destination)


def main():
    parser = argparse.ArgumentParser(description='Convert Character Card V1/V2/V3 JSON to Markdown for review.')
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        with args.source.open('rb') as stream:
            result = convert_card(stream.read(MAX_SOURCE_BYTES + 1))
        write_package(result, args.destination)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Conversion failed: {error}\n')
    print(f"Converted {result['card_version']} to {len(result['files'])} Markdown files in {args.destination}.")
    print('Review conversion-report.json before publishing. No library or Story was changed.')


if __name__ == '__main__':
    main()
