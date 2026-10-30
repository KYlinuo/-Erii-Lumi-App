import XCTest
@testable import LUMI

/// Runs against URLProtocol, with no network or paid provider. These tests must
/// be executed on macOS/iOS because URLSession.AsyncBytes is an Apple API.
final class ChatStreamNetworkTests: XCTestCase {
    @MainActor
    private func api(_ path: String) -> LUMIAPIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StreamURLProtocol.self]
        let session = URLSession(configuration: config)
        let baseURL = URL(string: "https://stream-test.invalid/\(path)")!
        return LUMIAPIClient(session: session, configuration: {
            ServerConfiguration(baseURL: baseURL)
        })
    }

    @MainActor
    func testCallbacksAreOrderedAndAwaited() async throws {
        var events: [String] = []
        try await api("delta").sendMessageStream(
            text: "你好", conversationID: nil,
            onDelta: { text in
                // A suspended callback still must finish before done begins.
                await Task.yield()
                events.append(text)
            },
            onDone: { response in events.append(response.reply) }
        )
        XCTAssertEqual(events, ["你", "好", "你好"])
    }

    @MainActor
    func testDoneOnlyInvokesCompletion() async throws {
        var reply: String?
        try await api("done-only").sendMessageStream(
            text: "你好", conversationID: "c1",
            onDelta: { _ in XCTFail("Replay has no deltas") },
            onDone: { response in reply = response.reply }
        )
        XCTAssertEqual(reply, "你好")
    }

    @MainActor
    func testEOFWithoutDoneFails() async {
        do {
            try await api("cutoff").sendMessageStream(
                text: "你好", conversationID: nil,
                onDelta: { _ in }, onDone: { _ in XCTFail("Incomplete stream") }
            )
            XCTFail("EOF must fail")
        } catch {
            XCTAssertEqual(error as? LUMIError, .connectionLost)
        }
    }

    @MainActor
    func testHTTPErrorRetainsProviderCode() async {
        do {
            try await api("http-error").sendMessageStream(
                text: "你好", conversationID: nil, onDelta: { _ in }, onDone: { _ in }
            )
            XCTFail("503 must fail")
        } catch {
            XCTAssertEqual(error as? LUMIError, .providerNotConfigured)
        }
    }

    @MainActor
    func testViewModelReplayAndFailureCleanup() async throws {
        let oldConversation = UserDefaults.standard.string(forKey: "lumi.conversation.id")
        defer { UserDefaults.standard.set(oldConversation, forKey: "lumi.conversation.id") }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = MessageStore(directory: directory)
        let replay = ChatViewModel(api: api("done-only"), store: store)
        replay.send(text: "你好")
        for _ in 0..<200 where replay.isSending { try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(replay.isSending)
        XCTAssertEqual(replay.messages.map(\.content), ["你好", "你好"])
        XCTAssertTrue(replay.messages.allSatisfy { $0.status == .sent })
        XCTAssertEqual(replay.messages.last?.serverID, "a1")

        let cutoff = ChatViewModel(api: api("cutoff"), store: store)
        cutoff.send(text: "测试断线")
        for _ in 0..<200 where cutoff.isSending { try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(cutoff.isSending)
        XCTAssertEqual(cutoff.messages.count, 1, "Partial assistant bubble must be removed")
        XCTAssertEqual(cutoff.messages.first?.status, .failed)
        XCTAssertEqual(cutoff.lastError, .connectionLost)
    }
}

private final class StreamURLProtocol: URLProtocol, @unchecked Sendable {
    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "stream-test.invalid"
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let path = request.url?.path ?? ""
        let httpError = path.contains("http-error")
        let delta = "data: {\"type\":\"delta\",\"text\":\"你\"}\n\ndata: {\"type\":\"delta\",\"text\":\"好\"}\n\n"
        let done = """
        data: {"type":"done","conversation_id":"c1","user_message_id":"u1","assistant_message_id":"a1","reply":"你好","model":"test","latency_ms":0,"idempotent_replay":true}


        """
        let body: String
        if httpError {
            body = "{\"error\":{\"code\":\"provider_not_configured\",\"message\":\"未配置\"}}"
        } else if path.contains("cutoff") {
            body = delta
        } else if path.contains("done-only") {
            body = done
        } else {
            body = delta + done
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: httpError ? 503 : 200,
                                       httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": httpError ? "application/json" : "text/event-stream"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
