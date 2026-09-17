from typing import Annotated, Literal

from pydantic import Field

from server.errors import require
from server.models import Input


class ProseBlock(Input):
    id: str = Field(min_length=1, max_length=100)
    kind: Literal["prose"]
    text: str = Field(min_length=1, max_length=100000)


class DialogueSlot(Input):
    id: str = Field(min_length=1, max_length=100)
    kind: Literal["dialogue"]
    speaker: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=3000)


class DraftOutput(Input):
    summary: str = Field(min_length=1, max_length=4000)
    blocks: list[Annotated[ProseBlock | DialogueSlot, Field(discriminator="kind")]] = Field(min_length=1, max_length=200)
    proposed_facts: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(default_factory=list, max_length=40)


class DialogueLine(Input):
    slot_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=100000)


class DialogueOutput(Input):
    summary: str = Field(min_length=1, max_length=4000)
    lines: list[DialogueLine] = Field(min_length=1, max_length=200)


class BeatCoverage(Input):
    beat_id: str = Field(min_length=1, max_length=100)
    status: Literal["rendered", "compressed", "missing", "moved"]
    quotes: list[Annotated[str, Field(min_length=1, max_length=4000)]] = Field(default_factory=list, max_length=5)
    explanation: str = Field(min_length=1, max_length=4000)


class CoverageIssue(Input):
    category: Literal["agency", "constraint", "sequence", "other"]
    quote: str = Field(min_length=1, max_length=4000)
    explanation: str = Field(min_length=1, max_length=4000)


class CoverageOutput(Input):
    summary: str = Field(min_length=1, max_length=4000)
    beats: list[BeatCoverage] = Field(min_length=1, max_length=24)
    issues: list[CoverageIssue] = Field(default_factory=list, max_length=30)


def assemble_draft(draft, dialogue=None):
    lines = {line["slot_id"]: line["text"] for line in (dialogue or {}).get("lines", [])}
    blocks = [{**block, "text": block.get("text", lines.get(block["id"]))} for block in draft["blocks"]]
    pending = any(block["text"] is None for block in blocks)
    return {"blocks": blocks, "complete": not pending,
            "text": None if pending else "\n\n".join(block["text"] for block in blocks),
            "proposed_facts": draft["proposed_facts"]}


def validate_draft(result, context):
    blocks = result["blocks"]
    require(len({block["id"] for block in blocks}) == len(blocks), "Draft blocks need unique IDs.", 502)
    slots = [block for block in blocks if block["kind"] == "dialogue"]
    require(bool(slots) == bool(context["dialogue_split"]), "The draft does not match the requested dialogue mode.", 502)
    require(sum(len(block.get("text", "")) + 2 for block in blocks) <= 100002,
            "The proposed scene exceeds 100,000 prose characters.", 502)


def validate_dialogue(result, context):
    draft = context["skeleton"]
    slots = [block["id"] for block in draft["blocks"] if block["kind"] == "dialogue"]
    require([line["slot_id"] for line in result["lines"]] == slots,
            "Dialogue must fill every slot exactly once, in the skeleton's order.", 502)
    require(len(assemble_draft(draft, result)["text"]) <= 100000, "The completed scene exceeds 100,000 characters.", 502)


def validate_coverage(result, context):
    expected = [beat["id"] for beat in context["proposed_beats"]["beats"]]
    require([beat["beat_id"] for beat in result["beats"]] == expected,
            "Coverage must assess every approved beat exactly once, in order.", 502)
    prose = context["draft"]["text"]
    for beat in result["beats"]:
        require(beat["status"] == "missing" or bool(beat["quotes"]), "Coverage needs evidence for each present beat.", 502)
        require(all(quote in prose for quote in beat["quotes"]), "A coverage quotation does not match the draft.", 502)
    require(all(issue["quote"] in prose for issue in result["issues"]), "A coverage issue does not quote the draft.", 502)


def coverage_passes(result):
    return bool(result) and not result["issues"] and all(beat["status"] == "rendered" for beat in result["beats"])
