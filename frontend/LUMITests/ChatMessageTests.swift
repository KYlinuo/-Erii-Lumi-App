import XCTest
@testable import LUMI

/// 消息模型与本地持久化（MessageStore）测试。
final class ChatMessageTests: XCTestCase {

    func testChatMessageCodableRoundtrip() throws {
        let original = ChatMessage(
            role: .assistant,
            content: "嗨，我是 LUMI。",
            model: "deepseek-chat",
            serverID: "abc123",
            errorMessage: nil
        )

        let data = try JSONEncoder().encode([original])
        let decoded = try JSONDecoder().decode([ChatMessage].self, from: data)

        XCTAssertEqual(decoded.count, 1)
        XCTAssertEqual(decoded[0], original)
    }

    func testFailedMessageKeepsErrorMessage() throws {
        let original = ChatMessage(
            role: .user,
            content: "在吗",
            status: .failed,
            errorMessage: "请求超时了，服务器没有及时响应。"
        )
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(ChatMessage.self, from: data)
        XCTAssertEqual(decoded.status, .failed)
        XCTAssertEqual(decoded.errorMessage, "请求超时了，服务器没有及时响应。")
    }

    func testMessageStoreRoundtrip() async throws {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("lumi-tests-\(UUID().uuidString)", isDirectory: true)
        let store = MessageStore(directory: dir)

        let messages = [
            ChatMessage(role: .assistant, content: "第一条"),
            ChatMessage(role: .user, content: "第二条", status: .sending),
            ChatMessage(role: .user, content: "第三条", status: .failed, errorMessage: "网络不可用"),
        ]
        try await store.save(messages)

        let reloaded = MessageStore(directory: dir)
        let loaded = try await reloaded.load()
        XCTAssertEqual(loaded, messages)

        try await reloaded.clear()
        let afterClear = try await reloaded.load()
        XCTAssertTrue(afterClear.isEmpty)
    }

    func testMessageStoreLoadFromEmptyDirectory() async throws {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("lumi-tests-\(UUID().uuidString)", isDirectory: true)
        let store = MessageStore(directory: dir)
        let loaded = try await store.load()
        XCTAssertTrue(loaded.isEmpty)
    }

    func testMessageStoreSurvivesCorruptedFile() async throws {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("lumi-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try Data("这不是JSON".utf8).write(to: dir.appendingPathComponent("messages.json"))

        let store = MessageStore(directory: dir)
        let loaded = try await store.load()
        XCTAssertTrue(loaded.isEmpty, "损坏的本地文件应被安全忽略，而不是让 App 崩溃")
    }
}
