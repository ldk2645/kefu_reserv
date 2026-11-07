import pytest

from kbs_collector.clipboard_link import copy_visible_link
from kbs_collector.policy import CollectorError


class FictionalClipboard:
    counter=1
    reads=0
    value='https://www.mi.com/fictional-video?part=2#demo'
    def sequence(self):
        return self.counter
    def read_changed_text(self,sequence):
        assert sequence == self.counter and self.counter != 1
        self.reads += 1
        return self.value
    def copy(self):
        self.counter += 1


def test_copy_failure_never_reads_prior_clipboard():
    clipboard=FictionalClipboard()
    with pytest.raises(CollectorError,match='COPY_LINK_NOT_CONFIRMED'):
        copy_visible_link(lambda:None,clipboard=clipboard,timeout=.01)
    assert clipboard.reads==0


def test_copy_preserves_exact_url_and_rejects_sensitive_query():
    clipboard=FictionalClipboard()
    assert copy_visible_link(clipboard.copy,clipboard=clipboard)==clipboard.value
    clipboard.value='https://www.mi.com/fictional-video?token=FICTIONAL'
    with pytest.raises(CollectorError,match='COPIED_LINK_UNSAFE'):
        copy_visible_link(clipboard.copy,clipboard=clipboard)
