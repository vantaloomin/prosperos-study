from typing import Literal

from pydantic import Field

from server.memory.source_evidence import quotation_matches
from server.models import Input
from server.scenes.models import SceneApproval

Disposition = Literal['hard-fix', 'fix', 'cut', 'overrule', 'verify', 'hold']


class Evidence(Input):
    source_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=4000)


class Resolution(Input):
    disposition: Disposition
    reason: str = Field(min_length=1, max_length=4000)
    action: str = Field(default='', max_length=4000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)


class TriageItem(Resolution):
    id: str = Field(min_length=1, max_length=100)
    finding_ids: list[str] = Field(min_length=1, max_length=100)


class TriageOutput(Input):
    summary: str = Field(min_length=1, max_length=4000)
    approach: Literal['patch', 'redraft']
    items: list[TriageItem] = Field(max_length=100)


class VerificationOutput(Input):
    summary: str = Field(min_length=1, max_length=4000)
    verdict: Literal['confirmed', 'rejected', 'undecidable']
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    smallest_fix: str = Field(default='', max_length=4000)


class TriageEdit(SceneApproval):
    item_id: str
    resolution: Resolution


class RevisionApproval(SceneApproval):
    package: Literal['A', 'B', 'C', 'custom']
    item_ids: list[str] = Field(default_factory=list, max_length=100)
    confirmed_hold_ids: list[str] = Field(default_factory=list, max_length=100)


def validate_evidence(evidence, sources):
    from server.errors import require

    text = {source['id']: source for source in sources}
    for item in evidence:
        require(item['source_id'] in text and quotation_matches(text[item['source_id']], item['quote']),
                'Evidence must quote an exact passage from the supplied sources.', 502)


def validate_resolution(item, sources):
    from server.errors import require

    validate_evidence(item['evidence'], sources)
    if item['disposition'] in {'hard-fix', 'fix', 'cut', 'hold'}:
        require(bool(item['action'].strip()), 'A proposed change needs a concrete action.', 502)
    if item['disposition'] == 'overrule':
        require(bool(item['evidence']), 'Overruling a finding needs cited evidence.', 502)


def validate_triage(result, content):
    from server.errors import require

    expected = {item['id'] for item in content['findings']}
    actual = [ref for item in result['items'] for ref in item['finding_ids']]
    require(set(actual) == expected and len(actual) == len(expected),
            'Triage must account for every supplied finding exactly once.', 502)
    require(len({item['id'] for item in result['items']}) == len(result['items']), 'Triage items need unique IDs.', 502)
    findings = {item['id']: item for item in content['findings']}
    for item in result['items']:
        validate_resolution(item, content['sources'])
        hard = any(findings[ref]['severity'] == 'hard' for ref in item['finding_ids'])
        require(not hard or item['disposition'] in {'hard-fix', 'overrule', 'verify', 'hold'},
                'A hard finding cannot silently become an optional fix.', 502)
        structural = any(findings[ref]['severity'] == 'hold' for ref in item['finding_ids'])
        require(not structural or item['disposition'] in {'hold', 'overrule', 'verify'},
                'A structural finding needs explicit approval or an evidenced overrule.', 502)


def validate_verification(result, content):
    from server.errors import require

    validate_evidence(result['evidence'], content['sources'])
    require(result['verdict'] == 'undecidable' or bool(result['evidence']),
            'A decisive verdict needs exact source evidence.', 502)
