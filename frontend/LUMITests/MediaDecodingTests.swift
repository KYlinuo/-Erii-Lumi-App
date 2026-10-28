import XCTest
@testable import LUMI

/// 媒体与语音传输模型的解码测试。
///
/// 重点验证**向后兼容**：v0.2 后端不会返回 `kind` / `media_id`，
/// 客户端必须把它们当作 text，而不是解码失败。
final class MediaDecodingTests: XCTestCase {

    private let decoder = JSONDecoder()

    func testMediaAssetDecoding() throws {
        let json = """
        {"id":"m1","user_id":null,"character_id":null,"kind":"image","mime":"image/jpeg",
         "byte_size":20480,"sha256":"abc","storage_uri":"ab/m1.jpg","width":0,"height":0,
         "duration_ms":0}
        """
        let asset = try decoder.decode(MediaAssetDTO.self, from: Data(json.utf8))
        XCTAssertEqual(asset.id, "m1")
        XCTAssertEqual(asset.kind, "image")
        XCTAssertEqual(asset.byteSize, 20480)
    }

    func testTranscriptDecodingMarksMock() throws {
        let json = """
        {"media_id":"m2","text":"（语音消息 · 3 秒；本机未接入 ASR，未做转写）",
         "language":"zh","mock":true,"duration_ms":3000}
        """
        let transcript = try decoder.decode(TranscriptDTO.self, from: Data(json.utf8))
        XCTAssertTrue(transcript.mock, "Mock 转写必须显式标记，界面不能当真")
        XCTAssertTrue(transcript.text.contains("未接入"))
    }

    func testServerMessageWithoutKindFallsBackToText() throws {
        let json = """
        {"id":"s1","conversation_id":"c1","role":"assistant","content":"晚上好",
         "status":"ok","model":"deepseek-chat","created_at":"2026-10-28T12:00:00.000000+00:00"}
        """
        let message = try decoder.decode(ServerMessage.self, from: Data(json.utf8))
        let chat = message.toChatMessage()
        XCTAssertEqual(chat.kind, .text)
        XCTAssertNil(chat.mediaID)
    }

    func testServerMessageWithMedia() throws {
        let json = """
        {"id":"s2","conversation_id":"c1","role":"user","content":"","status":"ok",
         "kind":"audio","media_id":"m9","created_at":"2026-10-28T12:00:00.000000+00:00"}
        """
        let chat = try decoder.decode(ServerMessage.self, from: Data(json.utf8)).toChatMessage()
        XCTAssertEqual(chat.kind, .audio)
        XCTAssertEqual(chat.mediaID, "m9")
    }

    func testChatRequestEncodesMediaFields() throws {
        let request = ChatRequest(
            message: "",
            conversationId: "c1",
            requestId: "r1",
            characterKey: "erii",
            mediaId: "m5",
            kind: "image"
        )
        let data = try JSONEncoder().encode(request)
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        XCTAssertEqual(object["media_id"] as? String, "m5")
        XCTAssertEqual(object["kind"] as? String, "image")
    }

    func testSpeechStatusDecoding() throws {
        let json = """
        {"asr_configured":false,"tts_configured":false,"mock":true,
         "notice":"未接入语音服务时使用 Mock，返回内容会显式标注，不会冒充真实识别结果。"}
        """
        let status = try decoder.decode(SpeechStatusDTO.self, from: Data(json.utf8))
        XCTAssertTrue(status.mock)
        XCTAssertFalse(status.asrConfigured)
    }

    func testMessageKindRoundTripsThroughStore() throws {
        let message = ChatMessage(
            role: .user,
            content: "",
            kind: .audio,
            localMediaPath: "/tmp/a.m4a",
            durationMs: 4200
        )
        let data = try JSONEncoder().encode([message])
        let restored = try JSONDecoder().decode([ChatMessage].self, from: data)
        XCTAssertEqual(restored.first?.kind, .audio)
        XCTAssertEqual(restored.first?.durationMs, 4200)
    }
}
