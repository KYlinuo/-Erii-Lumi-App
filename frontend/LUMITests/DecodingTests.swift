import XCTest
@testable import LUMI

/// 用后端真实响应样例验证客户端解码。
final class DecodingTests: XCTestCase {

    func testDecodeChatResponse() throws {
        let json = """
        {
          "conversation_id": "c1",
          "user_message_id": "m1",
          "assistant_message_id": "m2",
          "reply": "嗨，我是 LUMI。",
          "model": "deepseek-chat",
          "latency_ms": 812
        }
        """
        let response = try JSONDecoder().decode(ChatResponse.self, from: Data(json.utf8))
        XCTAssertEqual(response.conversationId, "c1")
        XCTAssertEqual(response.reply, "嗨，我是 LUMI。")
        XCTAssertEqual(response.model, "deepseek-chat")
        XCTAssertEqual(response.latencyMs, 812)
    }

    func testDecodeHealthResponse() throws {
        let json = """
        {
          "status": "ok", "version": "0.1.0", "env": "prod", "database": "ok",
          "provider": "deepseek", "provider_model": "deepseek-chat",
          "provider_configured": true, "api_key_hint": "sk-1...abcd",
          "auth_required": true
        }
        """
        let health = try JSONDecoder().decode(HealthResponse.self, from: Data(json.utf8))
        XCTAssertTrue(health.isHealthy)
        XCTAssertTrue(health.authRequired)
        XCTAssertEqual(health.providerModel, "deepseek-chat")
    }

    func testDecodePersonaResponse() throws {
        let json = """
        {"name":"LUMI","tagline":"会一直在你身边的 AI 少女","avatar":"lumi_avatar","greeting":"嗨，我是 LUMI。今天想聊点什么？"}
        """
        let persona = try JSONDecoder().decode(PersonaResponse.self, from: Data(json.utf8))
        XCTAssertEqual(persona.name, "LUMI")
    }

    func testDecodeErrorEnvelope() throws {
        let json = """
        {"error":{"code":"provider_not_configured","message":"后端尚未配置模型 API Key，无法生成回复。","hint":"请在 .env 中设置 LUMI_API_KEY 后重启后端。"}}
        """
        let envelope = try JSONDecoder().decode(ErrorEnvelope.self, from: Data(json.utf8))
        XCTAssertEqual(envelope.error.code, "provider_not_configured")
    }

    func testDecodeServerMessageAndConvert() throws {
        let json = """
        {
          "id": "m2", "conversation_id": "c1", "role": "assistant",
          "content": "早上好", "status": "ok", "model": "deepseek-chat",
          "latency_ms": 300,
          "created_at": "2026-10-26T15:30:00.123456+00:00"
        }
        """
        let msg = try JSONDecoder().decode(ServerMessage.self, from: Data(json.utf8))
        let chat = msg.toChatMessage()
        XCTAssertEqual(chat.role, .assistant)
        XCTAssertEqual(chat.content, "早上好")
        XCTAssertEqual(chat.status, .sent)
        XCTAssertEqual(chat.serverID, "m2")
    }

    func testChatRequestEncodesSnakeCase() throws {
        let request = ChatRequest(message: "你好", conversationId: "c9")
        let data = try JSONEncoder().encode(request)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["message"] as? String, "你好")
        XCTAssertEqual(object["conversation_id"] as? String, "c9")
        XCTAssertNil(object["conversationId"], "客户端必须使用后端的 snake_case 字段名")
    }
}
