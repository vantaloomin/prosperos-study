from server.authoring.context import parse_authoring
from server.workflow.runner import ReviewRunner


class AuthoringRunner(ReviewRunner):
    prefix = 'authoring'
    label = 'Library assistant'

    def parse_result(self, output, snapshot):
        return parse_authoring(output, snapshot)
