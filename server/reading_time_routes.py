from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/reading-time')


@router.post('/composing')
async def composing(request: Request):
    scheduler = getattr(request.app.state.runner.provider, 'scheduler', None)
    if scheduler:
        scheduler.composing()
    return {'noted': True}


@router.get('/status')
async def status(request: Request):
    scheduler = request.app.state.preparation_runner.scheduler
    return {'preparation': request.app.state.preparation_runner.status(),
            'inference': {'active': len(scheduler.active), 'waiting': len(scheduler.waiting),
                          'blocked_resources': len(scheduler.blocked)}}
