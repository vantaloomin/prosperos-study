# Released v0.7.0 archive fixture

`v070-manuscript-archive.json.gz` contains a disposable format-33 Story archive generated using the actual `v0.7.0` tag, commit `d1c08400c0b133d63a7fde56d44bdfd43f853151`.

It contains three invented accepted passages, an unaccepted controlled-provider draft, and a manuscript chapter/scene/bookmark. It includes frozen role and mode/agency instructions. No personal data, credentials or live inference were used.

SHA-256 of the uncompressed JSON: `7c8c54e66ae1844524fba04e06539661a09a849f7da4d0915db803b6821be5d0`.

The fixture catches the archive-number collision between published v0.7.0 manuscript records and the independently developed memory/cleanup branch. Tests require preservation of manuscript references and exact writer bytes, and reject partial mixtures of the two historical shapes.
