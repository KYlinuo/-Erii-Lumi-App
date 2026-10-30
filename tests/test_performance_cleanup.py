"""Protect behavior and query cost; wall-clock timing is intentionally not asserted."""
from sqlalchemy import event, select
from app import personas, proactive, services, world
from app.models import Character, Conversation, Message


def test_conversation_list_uses_one_query_without_hydrating_messages(db_session):
    for i in range(20):
        conv = Conversation(title=f'conversation {i}')
        db_session.add(conv)
        db_session.flush()
        for j in range(3):
            services.append_message(db_session, conv.id, 'user', f'{i}:{j}')
    db_session.commit()
    db_session.expunge_all()
    queries = []
    engine = db_session.get_bind()
    def count(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith('SELECT'):
            queries.append(statement)
    event.listen(engine, 'before_cursor_execute', count)
    try:
        rows = services.list_conversations(db_session)
    finally:
        event.remove(engine, 'before_cursor_execute', count)
    assert len(rows) == 20
    assert all(row['message_count'] == 3 for row in rows)
    assert len(queries) == 1
    assert not any(isinstance(obj, Message) for obj in db_session.identity_map.values())


def test_conversation_list_count_excludes_tombstones(client, stub):
    turn = client.post('/api/v1/chat', json={'message': 'test'}).json()
    client.delete('/api/v1/sync/messages/' + turn['user_message_id'])
    rows = client.get('/api/v1/conversations').json()
    assert rows[0]['message_count'] == 1


def test_character_filter_is_applied(client, stub, db_session):
    db_session.add(Character(key='archive-test', name='Archive test'))
    db_session.commit()
    characters = db_session.execute(select(Character)).scalars().all()
    keys = [c.key for c in characters]
    assert len(keys) >= 2
    for key in keys[:2]:
        assert client.post('/api/v1/chat', json={'message':'hello', 'character_key':key}).status_code == 200
    rows = client.get('/api/v1/conversations', params={'character_key':keys[0]}).json()
    assert len(rows) == 1
    assert client.get('/api/v1/conversations', params={'character_key':'missing'}).json() == []


def test_proactive_composition_with_multiple_conversations(client, stub, db_session):
    for _ in range(3):
        client.post('/api/v1/chat', json={'message':'hello'})
    character = personas.resolve_character(db_session, 'erii')
    result = proactive.compose_message(db_session, character, None)
    assert result and len(result) == 2


def test_recent_world_contents_only_queries_previous_window(db_session):
    from datetime import date, datetime, timezone
    character = personas.resolve_character(db_session, 'erii')
    world.record_event(db_session, character_id=character.id, kind='diary', title='test',
                       content='yesterday-specific', occurred_at=datetime(2026, 10, 28, tzinfo=timezone.utc))
    world.record_event(db_session, character_id=character.id, kind='diary', title='test',
                       content='today-specific', occurred_at=datetime(2026, 10, 29, tzinfo=timezone.utc))
    db_session.flush()
    contents = world._recent_contents(db_session, character.id, date(2026,10,29))
    assert 'yesterday-specific' in contents
    assert 'today-specific' not in contents
