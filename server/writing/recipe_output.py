import json

from pydantic import ValidationError

from server.database import decode
from server.errors import DomainError, require
from server.side_edits import EditOutput
from server.structured_text import json_payload
from server.workflow.runner import parse_review


def parse_recipe_output(output, snapshot):
    output = json_payload(output)
    if snapshot['task'] == 'review':
        return parse_review(output, snapshot['content'])
    try:
        result = EditOutput.model_validate(json.loads(output))
    except (ValueError, ValidationError):
        raise DomainError('The recipe writer did not return a complete text proposal. Its original output is preserved; retry is explicit.', 502) from None
    allowed = {source['id'] for source in decode(snapshot['content'])['sources']}
    require(len(result.source_ids) == len(set(result.source_ids)) and set(result.source_ids) <= allowed,
            'The recipe proposal cites a source outside this step’s frozen inputs.', 502)
    return result.model_dump()
