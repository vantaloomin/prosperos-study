"""Validate proposals against frozen evidence; map citations to original passages."""
import json

from pydantic import ValidationError

from server.database import decode
from server.errors import DomainError, require
from server.scenes.continuity_models import ContinuityOutput, validate_continuity


def passage_citation(citation, passages):
    matches = [source for source in passages if citation['quote'] in source['text']]
    require(len(matches) == 1, 'A plan quotation must identify one supplied passage exactly. The raw suggestion is preserved.', 502)
    return {'source_id': matches[0]['id'], 'quote': citation['quote']}


def parse_plan_scan(output, snapshot):
    try:
        result = ContinuityOutput.model_validate(json.loads(output)).model_dump()
    except (ValueError, ValidationError) as error:
        raise DomainError('The continuity role did not return a valid proposal. Its output is preserved; check the prompt or retry.', 502) from error
    context = decode(snapshot['content'])
    validate_continuity(result, context)
    require(all(change['kind'] == 'plan' for change in result['changes']),
            'This review only proposes plans. Other continuity changes were not applied.', 502)
    result['changes'] = [{**change, 'evidence': [passage_citation(item, context['passages']) for item in change['evidence']]}
                         for change in result['changes']]
    return result
