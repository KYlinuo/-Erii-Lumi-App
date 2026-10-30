import XCTest
import UIKit
@testable import LUMI

final class ChatPerformanceTests: XCTestCase {
    func testRowsKeepIDsAndGroupingWithoutReordering() {
        let date = Date(timeIntervalSince1970: 1_000)
        let first = ChatMessage(role: .user, content: "a", createdAt: date)
        let second = ChatMessage(role: .user, content: "b", createdAt: date.addingTimeInterval(20))
        let third = ChatMessage(role: .assistant, content: "c", createdAt: date.addingTimeInterval(30))
        let rows = ChatRows(messages: [first, second, third])
        XCTAssertEqual(Array(rows).map(\.id), [first.id, second.id, third.id])
        XCTAssertTrue(rows[0].showTime)
        XCTAssertFalse(rows[0].showAvatar)
        XCTAssertFalse(rows[1].showTime)
        XCTAssertTrue(rows[1].showAvatar)
        XCTAssertTrue(rows[2].showTime)
    }

    func testOutOfOrderTimestampsDoNotGroup() {
        let now = Date()
        let rows = ChatRows(messages: [ChatMessage(role: .user, content: "a", createdAt: now),
                                      ChatMessage(role: .user, content: "b", createdAt: now.addingTimeInterval(-1))])
        XCTAssertTrue(rows[1].showTime)
    }

    func testEmptyRowsAndThreeMinuteBoundary() {
        XCTAssertTrue(ChatRows(messages: []).isEmpty)
        let now = Date()
        let rows = ChatRows(messages: [ChatMessage(role: .user, content: "a", createdAt: now),
                                      ChatMessage(role: .user, content: "b", createdAt: now.addingTimeInterval(180))])
        XCTAssertTrue(rows[1].showTime)
    }

    func testLargeHistoryGroupingPerformance() {
        let messages = (0..<10_000).map { ChatMessage(role: .user, content: "message \($0)") }
        measure {
            let rows = ChatRows(messages: messages)
            var avatars = 0
            for row in rows where row.showAvatar { avatars += 1 }
            XCTAssertGreaterThan(avatars, 0)
        }
    }

    @MainActor
    func testDecodeDownsamplesLargeImage() async throws {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let source = UIGraphicsImageRenderer(size: CGSize(width: 2400, height: 1200), format: format)
            .jpegData(withCompressionQuality: 0.8) { context in
                UIColor.blue.setFill()
                context.fill(CGRect(x: 0, y: 0, width: 2400, height: 1200))
            }
        let store = MediaStore(download: { _ in source })
        let image = try await store.image(id: "test", localPath: nil, maxPixelSize: 600)
        XCTAssertEqual(image.cgImage.width, 600)
        XCTAssertEqual(image.cgImage.height, 300)
        let cached = try await store.image(id: "test", localPath: nil, maxPixelSize: 600)
        XCTAssertTrue(image === cached)
        let detail = try await store.image(id: "test", localPath: nil, maxPixelSize: 1_200)
        XCTAssertEqual(detail.cgImage.width, 1_200)
        XCTAssertEqual(detail.cgImage.height, 600)
        XCTAssertFalse(image === detail, "A detail request must not reuse the low-resolution thumbnail")
    }

    func testInvalidImageThrowsWithoutPoisoningCache() async {
        let store = MediaStore(download: { _ in Data("not an image".utf8) })
        for _ in 0..<2 {
            do {
                _ = try await store.image(id: "bad", localPath: nil)
                XCTFail("Invalid data must fail")
            } catch { }
        }
    }

    func testConcurrentAudioRequestsShareDownload() async {
        actor Counter {
            var calls = 0
            func download() async throws -> Data {
                calls += 1
                try await Task.sleep(for: .milliseconds(30))
                return Data([1,2,3])
            }
        }
        let counter = Counter()
        let store = MediaStore(download: { _ in try await counter.download() })
        async let first = store.loadAudio("audio")
        async let second = store.loadAudio("audio")
        let (a,b) = await (first,second)
        XCTAssertEqual(a, b)
        XCTAssertEqual(a, Data([1,2,3]))
        let count = await counter.calls
        XCTAssertEqual(count, 1)
    }
}
