from fastapi import APIRouter, Request

from server.phrases.service import PhraseCheck, check

router = APIRouter(prefix='/api')


@router.post('/branches/{branch_id}/phrase-check')
def phrase_check(branch_id: str, body: PhraseCheck, request: Request):
    return check(request.app.state.database, branch_id, body)
