"""Keep questions, answers, conditions and steps together for offline retrieval."""
from .normalizer import block_text


def knowledge_chunks(capture):
    result=[]
    pending=[]
    section=''
    has_answer=False
    question=False

    def flush():
        nonlocal pending,has_answer,question
        if pending and (not question or has_answer):
            result.append((section,'\n'.join(pending)))
        pending=[]
        has_answer=False
        question=False

    for block in capture.blocks:
        if block.get('audience')=='internal':
            continue
        kind=block['kind']
        block_section=' > '.join(block.get('section',[])) or capture.title
        if kind=='heading':
            flush()
            section=block_section
            continue
        if kind in {'question','field'} or (pending and block_section!=section):
            flush()
        section=block_section
        value=block_text(block).strip()
        if not value:
            continue
        pending.append(value)
        if kind=='question':
            question=True
        elif kind not in {'label','note'}:
            has_answer=True
    flush()
    return result
