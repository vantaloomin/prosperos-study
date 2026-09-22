from fastapi import APIRouter, Request

from server.text_edits.documents import autosave_document
from server.text_edits.models import (
    DocumentSave,
    DocumentWrite,
    ProposalChange,
    ProposalCreate,
    ProposalDecision,
    ProposalRebase,
    TargetCatalog,
    TargetRead,
    UndoCommand,
)
from server.text_edits.service import (
    apply_in,
    change_proposal,
    create_proposal,
    dismiss_proposal,
    list_proposals,
    proposal_view,
    read_receipt,
    rebase_proposal,
    run,
    save_text_document,
)
from server.text_edits.targets import read_target
from server.text_edits.undo import undo_receipt
from server.text_edits.versioned import target_catalog

router = APIRouter(prefix='/api')


@router.post('/text-targets/catalog')
def catalog(body: TargetCatalog, request: Request):
    with request.app.state.database.connect() as connection:
        return target_catalog(connection, body)


@router.post('/text-targets/read')
def target(body: TargetRead, request: Request):
    with request.app.state.database.connect() as connection:
        return read_target(connection, body.target)


@router.put('/text-documents')
def save_document(body: DocumentSave, request: Request):
    return save_text_document(request.app.state.database, body)


@router.put('/text-documents/autosave')
def autosave(body: DocumentWrite, request: Request):
    return autosave_document(request.app.state.database, body)


@router.post('/text-edits', status_code=201)
def create(body: ProposalCreate, request: Request):
    return create_proposal(request.app.state.database, body)


@router.get('/text-edits/{identity}')
def detail(identity: str, request: Request):
    with request.app.state.database.connect() as connection:
        return proposal_view(connection, identity)


@router.get('/stories/{story_id}/text-edits')
def history(story_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        return list_proposals(connection, story_id)


@router.patch('/text-edits/{identity}')
def change(identity: str, body: ProposalChange, request: Request):
    return change_proposal(request.app.state.database, identity, body)


@router.post('/text-edits/{identity}/apply')
def apply(identity: str, body: ProposalDecision, request: Request):
    return run(request.app.state.database, body, 'text-edit-apply', identity,
               lambda connection: apply_in(connection, identity, body.expected_revision, body.branch_name, body.acknowledge_state_reset, database=request.app.state.database))


@router.post('/text-edits/{identity}/dismiss')
def dismiss(identity: str, body: ProposalDecision, request: Request):
    return dismiss_proposal(request.app.state.database, identity, body)


@router.post('/text-edits/{identity}/rebase', status_code=201)
def rebase(identity: str, body: ProposalRebase, request: Request):
    return rebase_proposal(request.app.state.database, identity, body)


@router.get('/text-edit-receipts/{identity}')
def receipt(identity: str, request: Request):
    with request.app.state.database.connect() as connection:
        return read_receipt(connection, identity)


@router.post('/text-edit-receipts/{identity}/undo')
def undo(identity: str, body: UndoCommand, request: Request):
    return undo_receipt(request.app.state.database, identity, body)
