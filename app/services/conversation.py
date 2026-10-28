from uuid import uuid4
from app.models import ConfirmedContext


class Conversation:
    def __init__(self):
        self.reset()

    def reset(self):
        self.session_id = uuid4().hex
        self.revision = 0
        self.request_serial = 0
        self.draft = None

    def changed(self):
        self.revision += 1
        if self.draft:
            self.draft.stale = True

    def ticket(self):
        self.request_serial += 1
        return self.session_id, self.revision, self.request_serial

    def accepts(self, ticket):
        return ticket == (self.session_id, self.revision, self.request_serial)

    def can_copy(self, context: ConfirmedContext):
        return bool(self.draft and context.confirmed_by_user and not self.draft.stale
                    and self.draft.context_fingerprint == context.fingerprint)
