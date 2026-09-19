"""Read-only configuration readiness, separate from actual draft evidence receipts."""
from fastapi import APIRouter, Query, Request

from server.database import one
from server.errors import DomainError, require
from server.memory.relationship_sources import active_annotations, source_catalog, story_policy
from server.profiles import resolve_profile

router = APIRouter(prefix='/api')


def item(key, label, state, detail, action='preferences', profile_id=None):
    return {'key': key, 'label': label, 'state': state, 'detail': detail,
            'action': action, 'profile_id': profile_id}


def writer(connection, story, override=None):
    try:
        require(not story['archived'], 'This Story is archived. Restore it in Story setup before writing.', 409)
        return resolve_profile(connection, story, 'writer', override), ''
    except DomainError as error:
        return None, error.message


def prewriting(policy, profile, character_lens):
    if character_lens:
        return item('prewriting', 'Prewriting search', 'inactive', 'Character-lens writing uses its permitted context and does not run prewriting search.')
    if policy.mode != 'long':
        return item('prewriting', 'Prewriting search', 'inactive', 'Choose Long story to use prewriting search.')
    if not policy.writer_recall:
        return item('prewriting', 'Prewriting search', 'off', 'Enable Check earlier evidence before writing to search before each draft.')
    if not profile:
        return item('prewriting', 'Prewriting search', 'unavailable', 'A configured, enabled writer is required.', 'writer')
    return item('prewriting', 'Prewriting search', 'enabled', 'One extra preparation request per draft; failure keeps the original context.')


def semantic(policy, profile, search):
    if not policy.semantic_recall:
        return item('semantic', 'Semantic search', 'off', 'Optional search by meaning; keyword recall remains available.')
    if search['state'] != 'enabled':
        return item('semantic', 'Semantic search', 'inactive', 'Requires active prewriting search for this request.')
    config = profile['config']
    if config['provider'] not in {'local', 'compatible', 'openai'}:
        return item('semantic', 'Semantic search', 'unavailable', 'This connection does not support semantic recall. Choose a Local, OpenAI or compatible writer.', 'writer', profile['profile_id'])
    model = config.get('embedding_model', '').strip()
    if not model:
        return item('semantic', 'Semantic search', 'needs setup', 'Add an embedding model to this writer profile. Keyword search will be used meanwhile.', 'writer', profile['profile_id'])
    return item('semantic', 'Semantic search', 'configured', f'{model}. Connection and cache readiness are checked during recall; warming or failure retains keyword search. Up to five embedding requests per draft.', 'writer', profile['profile_id'])


def relationships(connection, branch, policy, search):
    if not policy.relationship_recall:
        return item('relationships', 'Relationship links', 'off', 'Optional interpretations help find related original passages.')
    if search['state'] != 'enabled':
        return item('relationships', 'Relationship links', 'inactive', 'Enabled in preferences, but this request needs active prewriting search to use links.')
    sources, _ = source_catalog(connection, branch)
    count = len(active_annotations(connection, branch, sources))
    return item('relationships', 'Relationship links', 'available' if count else 'none prepared',
                f'{count} eligible annotation(s) on this path. Quotations and links do not establish narrative truth or complete coverage.', 'relationships')


def background(connection, provider, story, policy):
    if not policy.relationship_automatic:
        return item('background', 'Automatic link preparation', 'off', 'Enable automatic preparation in memory preferences, or prepare links explicitly in Story memory.')
    if policy.mode != 'long' or not policy.relationship_recall:
        return item('background', 'Automatic link preparation', 'inactive', 'Requires Long story and Use tentative relationship links.')
    profile, reason = writer(connection, story)
    if not profile:
        return item('background', 'Automatic link preparation', 'unavailable', reason, 'writer')
    try:
        capability = provider.background_capability(profile)
    except DomainError as error:
        capability = {'verified': False, 'reason': error.message}
    state = 'eligible' if capability['verified'] else 'paused'
    detail = f"Uses Story writer {profile['name']}, independently of this draft's override. "
    detail += ('Prepares newly accepted prose while idle; up to four requests per update. It yields to writing.'
               if capability['verified'] else capability['reason'])
    return item('background', 'Automatic link preparation', state, detail, 'background', profile['profile_id'])


@router.get('/branches/{branch_id}/memory-readiness')
def readiness(branch_id: str, request: Request, profile_id: str = Query(default='', max_length=100), character_lens: bool = False):
    with request.app.state.database.connect() as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
        story, policy = story_policy(connection, branch)
        profile, reason = writer(connection, story, profile_id)
        search = prewriting(policy, profile, character_lens)
        rows = [local_recall(policy, character_lens), search, semantic(policy, profile, search),
                relationships(connection, branch, policy, search),
                background(connection, request.app.state.relationship_runner.provider, story, policy)]
        return {'writer': {'profile_id': profile['profile_id'], 'name': profile['name']} if profile else None,
                'writer_reason': reason, 'items': rows}


def local_recall(policy, character_lens):
    if character_lens:
        return item('local', 'Local context', 'character scope', 'Only the selected character\'s permitted evidence is used. Inspect Context budget for this request.')
    if policy.mode == 'full':
        return item('local', 'Local recall', 'full history', 'The complete selected path must fit the context allowance; selective earlier-passage recall is off.')
    return item('local', 'Local recall', 'enabled', 'Recent prose and selected earlier excerpts share the context allowance. No extra model calls.')
