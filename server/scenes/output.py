import json

from pydantic import ValidationError

from server.database import decode
from server.errors import DomainError, require
from server.memory.source_evidence import quotation_matches
from server.scenes.continuity_models import ContinuityOutput, validate_continuity
from server.scenes.drafts import (
    CoverageOutput,
    DialogueOutput,
    DraftOutput,
    validate_coverage,
    validate_dialogue,
    validate_draft,
)
from server.scenes.models import BeatsOutput, BriefOutput, OptionsOutput
from server.scenes.patch_models import PatchCheckOutput, PatchOutput
from server.scenes.patch_validation import validate_patch, validate_patch_check
from server.scenes.revision_models import (
    TriageOutput,
    VerificationOutput,
    validate_triage,
    validate_verification,
)

OUTPUTS = {"scene-options": OptionsOutput, "scene-beats": BeatsOutput, "scene-brief": BriefOutput,
           "scene-draft": DraftOutput, "scene-dialogue": DialogueOutput, "scene-coverage": CoverageOutput,
           "scene-triage": TriageOutput, "scene-verify": VerificationOutput,
           'scene-patch': PatchOutput, 'scene-dialogue-patch': PatchOutput, 'scene-patch-check': PatchCheckOutput,
           'scene-continuity': ContinuityOutput}
DRAFT_VALIDATORS = {"scene-draft": validate_draft, "scene-dialogue": validate_dialogue, "scene-coverage": validate_coverage,
                    "scene-triage": validate_triage, "scene-verify": validate_verification,
                    'scene-patch': validate_patch, 'scene-dialogue-patch': validate_patch, 'scene-patch-check': validate_patch_check,
                    'scene-continuity': validate_continuity}


def validate_result(key, result, content):
    parsed = OUTPUTS[key].model_validate(result).model_dump()
    if key == "scene-brief":
        sources = {source["id"]: source for source in decode(content)["sources"]}
        for fact in parsed["facts"]:
            require(fact["source_id"] in sources, "The brief cites a source outside its supplied context.", 502)
            require(quotation_matches(sources[fact["source_id"]], fact["quote"]), "A brief quotation does not match its source.", 502)
    elif key in DRAFT_VALIDATORS:
        DRAFT_VALIDATORS[key](parsed, decode(content))
    else:
        items = parsed["options"] if key == "scene-options" else parsed["beats"]
        require(len({item["id"] for item in items}) == len(items), "Each proposed option or beat needs a unique ID.", 502)
    return parsed


def parse_scene(output, snapshot):
    try:
        return validate_result(snapshot["step"], json.loads(output), snapshot["content"])
    except (ValueError, ValidationError, KeyError) as error:
        raise DomainError("The specialist did not return the required structured proposal. Its text is preserved; check the prompt or retry.", 502) from error
