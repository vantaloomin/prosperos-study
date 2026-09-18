"""Writing experience and character agency are independent author choices."""


def story_mode(settings):
    return 'passive' if settings.get('experience') in {'directed', 'scene'} else 'active'


def reserved_agency(settings):
    return settings.get('player_agency') != 'shared'
