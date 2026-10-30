import pytest
import copy
import hashlib
from app import activities as A, proactive, services
from app.models import Conversation, Message, MemoryRecord, Character
from app.database import _build_engine, Base
from app.bootstrap import bootstrap
from sqlalchemy.orm import Session
from sqlalchemy import select


@pytest.fixture(autouse=True)
def use_stub(stub):
    return stub


def checksum(backup):
    backup['checksum'] = hashlib.sha256(A._canonical(backup['data'])).hexdigest()


def test_deleted_history_context_and_cursor(client, stub, db_session):
    turn = client.post('/api/v1/chat', json={'message':'delete-unique-content','request_id':'delete-1'}).json()
    cid = turn['conversation_id']
    seq = turn['conv_seq']
    assert client.delete('/api/v1/sync/messages/'+turn['user_message_id']).status_code == 204
    newer = client.get(f'/api/v1/sync/conversation/{cid}?after={seq}').json()
    assert any(m['id']==turn['user_message_id'] and m['deleted_at'] for m in newer)
    assert all(m['id']!=turn['user_message_id'] for m in client.get(f'/api/v1/conversations/{cid}/messages').json())
    client.post('/api/v1/chat', json={'message':'下一条','conversation_id':cid})
    assert all('delete-unique-content' not in m.content for m in stub.calls[-1] if m.role != 'system')


def test_search_literal_and_blank(client):
    turn=client.post('/api/v1/chat',json={'message':'百分之100%_进度'}).json()
    path=f"/api/v1/conversations/{turn['conversation_id']}/search"
    assert len(client.get(path,params={'query':'%_'}).json()) == 1
    assert client.get(path,params={'query':'   '}).json() == []


def test_ephemeral_backup_and_recent_activity(client, db_session):
    t=client.post('/api/v1/chat',json={'message':'私人内容','ephemeral':True}).json()
    assert all(c['id']!=t['conversation_id'] for c in client.get('/api/v1/conversations').json())
    b=client.get('/api/v1/backup/export').json()
    assert not b['data']['messages']
    assert not b['data']['conversations']
    assert not proactive.has_user_activity_recently(db_session)


def test_multiple_recent_messages_do_not_crash(client, db_session):
    t=client.post('/api/v1/chat',json={'message':'first'}).json()
    client.post('/api/v1/chat',json={'message':'second','conversation_id':t['conversation_id']})
    assert proactive.has_user_activity_recently(db_session)


def test_backup_portable_to_fresh_database(client, db_session, tmp_path):
    client.post('/api/v1/chat',json={'message':'我叫小明'})
    backup=A.build_backup(db_session)
    engine=_build_engine('sqlite:///'+str(tmp_path/'fresh.db'))
    Base.metadata.create_all(engine)
    with Session(engine) as target:
        bootstrap(target)
        assert A.preview_backup(target,backup)['valid']
        result=A.apply_backup(target,backup)
        assert result['applied']
        assert len(target.execute(select(Message)).scalars().all())==2
        charids=set(target.execute(select(Character.id)).scalars())
        assert all(c.character_id in charids for c in target.execute(select(Conversation)).scalars())
        assert A.apply_backup(target,backup)['tables']['messages']['created']==0
    engine.dispose()


def test_backup_null_overwrite_and_invalid_shape(client, db_session):
    t=client.post('/api/v1/chat',json={'message':'hello'}).json()
    b=A.build_backup(db_session)
    row=db_session.get(Message,t['assistant_message_id']);row.error_code='stale';db_session.commit()
    A.apply_backup(db_session,b,strategy='overwrite')
    assert db_session.get(Message,row.id).error_code is None
    for value in (None,{},'bad'):
        broken=copy.deepcopy(b);broken['data']['messages']=value;checksum(broken)
        assert not A.preview_backup(db_session,broken)['valid']
    bad=copy.deepcopy(b);bad['version']='garbage'
    assert not A.preview_backup(db_session,bad)['valid']


def test_restore_atomic_on_constraint_failure(client,db_session):
    client.post('/api/v1/chat',json={'message':'hello'})
    b=A.build_backup(db_session)
    b['data']['conversations'][0]['title']='must roll back'
    b['data']['messages'][0]['content']={'not':'text'};checksum(b)
    result=client.post('/api/v1/backup/apply',json={'backup':b,'strategy':'overwrite'})
    assert result.status_code==422
    db_session.expire_all()
    assert db_session.get(Conversation,b['data']['conversations'][0]['id']).title!='must roll back'


def test_sync_cursor_stops_at_page_end(client,db_session):
    t=client.post('/api/v1/chat',json={'message':'hello'}).json()
    rows,cursor,_=services.sync_messages(db_session,t['conversation_id'],limit=1)
    assert cursor==rows[-1]['conv_seq'] < t['conv_seq']
