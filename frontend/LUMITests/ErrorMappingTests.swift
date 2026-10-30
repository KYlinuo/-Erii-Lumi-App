import XCTest
@testable import LUMI

/// 后端错误码 → 用户提示 的映射测试。
/// 每种失败都必须有独立且准确的文案，这是 v0.1 的硬性要求。
final class ErrorMappingTests: XCTestCase {

    func testBackendErrorCodesMapDistinctly() {
        let cases: [(String, Int, LUMIError)] = [
            ("unauthorized", 401, .unauthorized),
            ("rate_limited", 429, .rateLimited(retryAfter: 5)),
            ("upstream_timeout", 504, .upstreamTimeout),
            ("upstream_unavailable", 503, .upstreamUnavailable),
            ("upstream_unauthorized", 502, .upstreamUnauthorized),
            ("provider_not_configured", 503, .providerNotConfigured),
            ("upstream_bad_response", 502, .upstreamBadResponse),
        ]

        for (code, status, expected) in cases {
            let mapped = LUMIError.from(code: code, httpStatus: status, message: "m", retryAfter: 5)
            XCTAssertEqual(mapped, expected, "错误码 \(code) 映射不符合预期")
        }
    }

    func testEveryErrorHasUserMessage() {
        let all: [LUMIError] = [
            .invalidBaseURL("abc"), .notConnectedToInternet, .timedOut, .cannotConnectToServer,
            .connectionLost, .serverUnreachable(status: 502), .unauthorized,
            .rateLimited(retryAfter: nil), .upstreamTimeout, .upstreamUnavailable,
            .upstreamUnauthorized, .providerNotConfigured, .upstreamBadResponse,
            .serverUnknown(code: "x", httpStatus: 500, message: "未知"), .decodingFailure("d"),
            .emptyReply,
        ]
        for error in all {
            XCTAssertFalse(error.userMessage.isEmpty, "\(error) 缺少用户提示")
        }
    }

    func testRetryability() {
        XCTAssertTrue(LUMIError.timedOut.isRetryable)
        XCTAssertTrue(LUMIError.upstreamTimeout.isRetryable)
        XCTAssertTrue(LUMIError.notConnectedToInternet.isRetryable)
        XCTAssertFalse(LUMIError.unauthorized.isRetryable, "令牌错误重试没有意义")
        XCTAssertFalse(LUMIError.providerNotConfigured.isRetryable)
        XCTAssertFalse(LUMIError.upstreamUnauthorized.isRetryable)
    }

    func testRateLimitedMessageIncludesSeconds() {
        let error = LUMIError.rateLimited(retryAfter: 7)
        XCTAssertTrue(error.userMessage.contains("7"), "限流提示应包含等待秒数")
    }

    func testURLErrorMapping() {
        XCTAssertEqual(
            LUMIError.from(URLError(.notConnectedToInternet)),
            .notConnectedToInternet
        )
        XCTAssertEqual(LUMIError.from(URLError(.timedOut)), .timedOut)
        XCTAssertEqual(
            LUMIError.from(URLError(.cannotFindHost)),
            .cannotConnectToServer
        )
        XCTAssertEqual(LUMIError.from(URLError(.networkConnectionLost)), .connectionLost)
    }
}
