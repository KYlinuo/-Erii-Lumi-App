import Foundation

/// 客户端统一错误模型。
///
/// 设计原则：**每一种失败都要有不同且准确的用户提示**，
/// 不允许笼统的「请求失败」，更不允许把失败伪装成一条 AI 回复。
enum LUMIError: LocalizedError, Sendable, Equatable {
    case invalidBaseURL(String)
    case notConnectedToInternet
    case timedOut
    case cannotConnectToServer
    case connectionLost
    case serverUnreachable(status: Int)
    case unauthorized
    case rateLimited(retryAfter: Int?)
    case upstreamTimeout
    case upstreamUnavailable
    case upstreamUnauthorized
    case providerNotConfigured
    case upstreamBadResponse
    case serverUnknown(code: String, httpStatus: Int, message: String)
    case decodingFailure(String)
    case emptyReply
    /// 同一个幂等 ID 被用在了另一个会话上（客户端逻辑错误）
    case requestIdConflict
    /// 当前设备令牌缺少某个 scope
    case forbidden
    /// 单日 token 预算已用尽
    case budgetExceeded

    /// 面向用户的中文提示（直接展示在聊天气泡或提示条上）。
    var userMessage: String {
        switch self {
        case .invalidBaseURL(let raw):
            return "服务器地址无效：\(raw)。请在设置里填写 http(s):// 开头的完整地址。"
        case .notConnectedToInternet:
            return "当前没有网络连接，请连上网络后再试。"
        case .timedOut:
            return "请求超时了，服务器没有及时响应。"
        case .cannotConnectToServer:
            return "无法连接到服务器，请确认地址正确且后端已启动。"
        case .connectionLost:
            return "网络连接中断，消息可能没有送达。"
        case .serverUnreachable(let status):
            return "服务器返回异常状态（HTTP \(status)）。"
        case .unauthorized:
            return "访问令牌无效或缺失，请在设置里重新填写。"
        case .rateLimited(let retry):
            if let retry, retry > 0 {
                return "请求太频繁了，请 \(retry) 秒后再试。"
            }
            return "请求太频繁了，请稍后再试。"
        case .upstreamTimeout:
            return "模型响应超时，请重试一次。"
        case .upstreamUnavailable:
            return "无法连接到模型服务，请检查服务器网络。"
        case .upstreamUnauthorized:
            return "服务端的模型 API Key 无效，请联系服务器管理员。"
        case .providerNotConfigured:
            return "服务端尚未配置模型 API Key，暂时无法生成回复。"
        case .upstreamBadResponse:
            return "模型返回了无法解析的内容，请重试。"
        case .serverUnknown(_, _, let message):
            return message.isEmpty ? "服务器返回了未知错误。" : message
        case .decodingFailure:
            return "服务器响应格式无法解析，可能是版本不匹配。"
        case .emptyReply:
            return "模型返回了空内容，请重试。"
        case .requestIdConflict:
            return "这条消息的编号已被用于其他会话，请重新发送。"
        case .forbidden:
            return "当前设备权限不足，请重新注册设备。"
        case .budgetExceeded:
            return "今天的额度已经用完啦，明天再来吧。"
        }
    }

    /// 次要说明（灰色小字）。
    var hint: String? {
        switch self {
        case .serverUnknown(let code, let httpStatus, _):
            return "错误码 \(code)，HTTP \(httpStatus)"
        case .rateLimited:
            return "已触发后端限流保护。"
        case .upstreamTimeout, .upstreamUnavailable, .upstreamBadResponse:
            return "后端可达，但上游模型服务异常。"
        case .providerNotConfigured:
            return "请在服务器 .env 中设置 LUMI_API_KEY 后重启后端。"
        case .decodingFailure:
            return "检查客户端与后端版本是否匹配。"
        default:
            return nil
        }
    }

    var errorDescription: String? { userMessage }
    var recoverySuggestion: String? { hint }

    /// 是否值得让用户直接点「重试」。
    var isRetryable: Bool {
        switch self {
        case .timedOut, .notConnectedToInternet, .cannotConnectToServer,
             .connectionLost, .upstreamTimeout, .upstreamUnavailable,
             .upstreamBadResponse, .emptyReply, .rateLimited:
            return true
        case .unauthorized, .providerNotConfigured, .upstreamUnauthorized,
             .invalidBaseURL, .decodingFailure, .requestIdConflict, .forbidden,
             .budgetExceeded:
            return false
        case .serverUnreachable(let status):
            return status >= 500
        case .serverUnknown(_, let httpStatus, _):
            return httpStatus >= 500
        }
    }

    // MARK: - 映射

    /// 把 URLSession 的传输层错误翻译成用户能看懂的提示。
    static func from(_ urlError: URLError) -> LUMIError {
        switch urlError.code {
        case .notConnectedToInternet, .networkConnectionLost:
            return urlError.code == .notConnectedToInternet
                ? .notConnectedToInternet
                : .connectionLost
        case .timedOut:
            return .timedOut
        case .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed:
            return .cannotConnectToServer
        case .secureConnectionFailed, .serverCertificateUntrusted,
             .serverCertificateHasBadDate, .serverCertificateNotYetValid:
            return .serverUnreachable(status: 0)
        default:
            return .cannotConnectToServer
        }
    }

    /// 把后端错误码 + HTTP 状态映射成具体语义。
    static func from(code: String, httpStatus: Int, message: String, retryAfter: Int?) -> LUMIError {
        switch code {
        case "unauthorized":
            return .unauthorized
        case "rate_limited":
            return .rateLimited(retryAfter: retryAfter)
        case "upstream_timeout":
            return .upstreamTimeout
        case "upstream_unavailable":
            return .upstreamUnavailable
        case "upstream_unauthorized":
            return .upstreamUnauthorized
        case "provider_not_configured":
            return .providerNotConfigured
        case "upstream_bad_response", "upstream_error":
            return .upstreamBadResponse
        case "request_id_conflict":
            return .requestIdConflict
        case "forbidden":
            return .forbidden
        case "budget_exceeded":
            return .budgetExceeded
        default:
            return .serverUnknown(code: code, httpStatus: httpStatus, message: message)
        }
    }
}
