import XCTest
@testable import LUMI

/// 新增传输模型的解码测试：字段名必须与后端一致，否则静默丢数据。
final class PersonaDecodingTests: XCTestCase {

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(type, from: Data(json.utf8))
    }

    // MARK: - 人格

    func testCharacterDecodesAllFields() throws {
        let json = """
        {"id":"c1","key":"erii","name":"绘梨衣","tagline":"安静","avatar_key":"erii",
         "greeting":"嗯……你来了。","summary":"安静的角色","traits":["安静","含蓄"],
         "interests":["小本子"],"background":"虚构设定","speaking_style":"短句",
         "source":"erii-pet","is_default":false,"is_active":true}
        """
        let character = try decode(CharacterInfo.self, json)
        XCTAssertEqual(character.name, "绘梨衣")
        XCTAssertEqual(character.traits, ["安静", "含蓄"])
        XCTAssertTrue(character.fromDesktopPet)
        XCTAssertFalse(character.isProvisional)
    }

    func testAgentAuthoredCharacterIsFlagged() throws {
        // 本机没有原始设计文档、由 AI 工程师拟定的设定：必须如实标注，不冒充原作
        let json = """
        {"id":"c2","key":"qilu","name":"祁鹿","tagline":"","avatar_key":"qilu",
         "greeting":"","summary":"","traits":[],"interests":[],"background":"",
         "speaking_style":"","source":"agent-authored","is_default":false,"is_active":true}
        """
        let character = try decode(CharacterInfo.self, json)
        XCTAssertTrue(character.isAgentAuthored)
        XCTAssertFalse(character.isProvisional)
        XCTAssertFalse(character.fromDesktopPet)
    }

    func testMissingSourceStillFlaggedAsProvisional() throws {
        let json = """
        {"id":"c3","key":"x","name":"X","tagline":"","avatar_key":"x",
         "greeting":"","summary":"","traits":[],"interests":[],"background":"",
         "speaking_style":"","source":"reconstructed","is_default":false,"is_active":true}
        """
        XCTAssertTrue(try decode(CharacterInfo.self, json).isProvisional)
    }

    // MARK: - 记忆

    func testMemoryItemMarksInferredSource() throws {
        let json = """
        {"id":"m1","user_id":null,"character_id":null,"scope":"user_fact",
         "subject":"user","content":"用户叫小明","source_type":"inferred",
         "source_message_id":"msg1","source_ref":"","confidence":0.55,
         "salience":9,"status":"active","created_at":"2026-10-28T00:00:00+00:00"}
        """
        let memory = try decode(MemoryItem.self, json)
        XCTAssertTrue(memory.isInferred)
        XCTAssertEqual(memory.scopeLabel, "事实")
        XCTAssertFalse(memory.isFictionalLife)
    }

    func testFictionalLifeIsSeparate() throws {
        let json = """
        {"id":"m2","user_id":null,"character_id":"c1","scope":"fictional_life",
         "subject":"character","content":"她随身带小本子","source_type":"world_simulation",
         "source_message_id":null,"source_ref":"","confidence":1.0,
         "salience":6,"status":"active","created_at":null}
        """
        let memory = try decode(MemoryItem.self, json)
        XCTAssertTrue(memory.isFictionalLife)
        XCTAssertTrue(memory.isSimulated, "虚构世界内容必须标为角色设定")
        XCTAssertFalse(memory.isInferred, "虚构设定不是「对用户事实的推测」")
    }

    // MARK: - 虚构人生

    func testWorldEventDecodesSimulatedFlag() throws {
        let json = """
        {"id":"w1","character_id":"c1","kind":"reading","title":"读书进度",
         "content":"读了几页","simulated":true,"mood":"平静","meta":{},
         "occurred_at":"2026-10-28T09:00:00+00:00"}
        """
        let event = try decode(WorldEventItem.self, json)
        XCTAssertTrue(event.simulated)
        XCTAssertEqual(event.kindLabel, "读书")
        XCTAssertNotNil(event.occurredDate)
    }

    func testDiaryCarriesNotice() throws {
        let json = """
        {"character_key":"lumi","character_name":"LUMI","notice":"虚构内容","events":[]}
        """
        let diary = try decode(DiaryResponse.self, json)
        XCTAssertFalse(diary.notice.isEmpty)
    }

    // MARK: - 同步

    func testSyncMessageMapsToChatMessage() throws {
        let json = """
        {"id":"s1","conversation_id":"c1","role":"assistant","content":"你好",
         "status":"ok","model":"mock-provider-v1","error_code":null,"latency_ms":12,
         "request_id":"req-1","conv_seq":7,"client_ts":null,"deleted_at":null,
         "created_at":"2026-10-28T00:00:00+00:00"}
        """
        let message = try decode(SyncMessage.self, json)
        XCTAssertEqual(message.convSeq, 7)
        XCTAssertEqual(message.requestId, "req-1")
        XCTAssertFalse(message.isDeleted)

        let chat = message.toChatMessage()
        XCTAssertEqual(chat.serverID, "s1")
        XCTAssertEqual(chat.convSeq, 7)
        XCTAssertEqual(chat.requestID, "req-1")
        XCTAssertEqual(chat.role, .assistant)
    }

    func testDeletedMessageIsTombstone() throws {
        let json = """
        {"id":"s2","conversation_id":"c1","role":"user","content":"删掉",
         "status":"ok","model":null,"error_code":null,"latency_ms":null,
         "request_id":null,"conv_seq":9,"client_ts":null,
         "deleted_at":"2026-10-28T01:00:00+00:00","created_at":null}
        """
        let message = try decode(SyncMessage.self, json)
        XCTAssertTrue(message.isDeleted)
    }

    func testSyncResponseDecodesCursor() throws {
        let json = """
        {"conversations":[],"global_cursor":42,"server_time":"2026-10-28T00:00:00+00:00"}
        """
        let response = try decode(SyncResponse.self, json)
        XCTAssertEqual(response.globalCursor, 42)
    }

    // MARK: - 设备与主动联系

    func testDeviceRegistrationDecodesToken() throws {
        let json = """
        {"device_id":"d1","user_id":"u1","name":"iPhone 17 Pro","platform":"ios",
         "token":"abc.def","token_hint":"abc...def","scopes":["chat","sync"]}
        """
        let registration = try decode(DeviceRegistration.self, json)
        XCTAssertEqual(registration.token, "abc.def")
        XCTAssertEqual(registration.scopes, ["chat", "sync"])
    }

    func testProactiveStatusDeclaresNoAPNS() throws {
        let json = """
        {"enabled":false,"allowed_now":false,"reason":"proactive_disabled","daily_cap":3,
         "windows":"09:00-12:00","quiet_hours":"23:30-07:30","apns_remote_push":false,
         "note":"服务端排队 + 客户端拉取"}
        """
        let status = try decode(ProactiveStatus.self, json)
        XCTAssertFalse(status.apnsRemotePush)
    }

    // MARK: - 向后兼容

    func testHealthFromV01ServerStillDecodes() throws {
        // v0.1 后端没有 v0.2 字段，客户端必须能兼容
        let json = """
        {"status":"ok","version":"0.1.0","env":"dev","database":"ok","provider":"deepseek",
         "provider_model":"deepseek-chat","provider_configured":false,"api_key_hint":"",
         "auth_required":false}
        """
        let health = try decode(HealthResponse.self, json)
        XCTAssertTrue(health.isHealthy)
        XCTAssertNil(health.schemaVersion)
        XCTAssertFalse(health.usingMockProvider)
    }

    func testChatResponseFromV01ServerStillDecodes() throws {
        let json = """
        {"conversation_id":"c1","user_message_id":"u1","assistant_message_id":"a1",
         "reply":"你好","model":"deepseek-chat","latency_ms":800}
        """
        let response = try decode(ChatResponse.self, json)
        XCTAssertEqual(response.reply, "你好")
        XCTAssertFalse(response.idempotentReplay)
        XCTAssertNil(response.convSeq)
    }

    func testChatResponseV02Fields() throws {
        let json = """
        {"conversation_id":"c1","user_message_id":"u1","assistant_message_id":"a1",
         "reply":"你好","model":"deepseek-chat","latency_ms":800,"character_id":"ch1",
         "conv_seq":5,"idempotent_replay":true}
        """
        let response = try decode(ChatResponse.self, json)
        XCTAssertEqual(response.characterId, "ch1")
        XCTAssertEqual(response.convSeq, 5)
        XCTAssertTrue(response.idempotentReplay)
    }
}
