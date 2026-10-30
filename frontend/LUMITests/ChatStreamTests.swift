import XCTest
@testable import LUMI

final class ChatStreamTests: XCTestCase {
    func testLineWithoutNewlineDecodesImmediately() throws {
        let event = try ChatStreamEvent.decode(line: "data: {\"type\":\"delta\",\"text\":\"嗯……你好 🌸\"}")
        guard case .delta(let text) = event else { return XCTFail("Missing delta") }
        XCTAssertEqual(text, "嗯……你好 🌸")
    }

    func testDoneWithoutDeltaSupportsIdempotentReplay() throws {
        let line = """
        data: {"type":"done","conversation_id":"c1","user_message_id":"u1","assistant_message_id":"a1","reply":"在这里。","model":"test","latency_ms":0,"idempotent_replay":true}
        """
        guard case .done(let response) = try ChatStreamEvent.decode(line: line) else {
            return XCTFail("Missing done")
        }
        XCTAssertEqual(response.reply, "在这里。")
        XCTAssertTrue(response.idempotentReplay)
    }

    func testMalformedDataIsAnError() {
        XCTAssertThrowsError(try ChatStreamEvent.decode(line: "data: {bad}")) {
            XCTAssertEqual($0 as? LUMIError, .upstreamBadResponse)
        }
    }

    func testIncompleteDoneIsAnError() {
        XCTAssertThrowsError(try ChatStreamEvent.decode(line: "data: {\"type\":\"done\"}"))
    }

    func testProviderErrorIsNotAReply() {
        XCTAssertThrowsError(try ChatStreamEvent.decode(
            line: "data: {\"type\":\"error\",\"code\":\"upstream_timeout\",\"message\":\"超时\"}"
        )) { XCTAssertEqual($0 as? LUMIError, .upstreamTimeout) }
    }

    func testCommentsAndBlankLinesAreIgnored() throws {
        XCTAssertNil(try ChatStreamEvent.decode(line: ": heartbeat"))
        XCTAssertNil(try ChatStreamEvent.decode(line: ""))
        XCTAssertNil(try ChatStreamEvent.decode(line: "data:"))
        XCTAssertNil(try ChatStreamEvent.decode(line: "event: message"))
    }

    func testPinnedMemoryDecodesAndOlderServerDefaultsToUnpinned() throws {
        let base = """
        {"id":"m1","scope":"user_fact","subject":"user","content":"约定","source_type":"user_explicit","source_ref":"","confidence":1,"salience":9,"status":"active"}
        """
        let old = try JSONDecoder().decode(MemoryItem.self, from: Data(base.utf8))
        XCTAssertFalse(old.isPinned)
        let pinned = base.replacingOccurrences(of: "\"status\":", with: "\"pinned\":true,\"status\":")
        XCTAssertTrue(try JSONDecoder().decode(MemoryItem.self, from: Data(pinned.utf8)).isPinned)
    }
}
