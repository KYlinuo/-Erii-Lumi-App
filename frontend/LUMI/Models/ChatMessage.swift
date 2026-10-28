import Foundation

/// 消息发送者角色。
enum MessageRole: String, Codable, Sendable, CaseIterable {
    case user
    case assistant
    case system
}

/// 本地消息状态。持久化后重开 App 会恢复这些状态。
enum MessageStatus: String, Codable, Sendable {
    case sending
    case sent
    case failed
}

/// 消息类型。语音/图片消息在气泡里的渲染方式完全不同，必须区分。
enum MessageKind: String, Codable, Sendable, CaseIterable {
    case text
    case image
    case audio
}

/// 一条聊天消息。本地持久化与网络传输共用这一模型。
struct ChatMessage: Identifiable, Codable, Equatable, Sendable {
    let id: UUID
    var role: MessageRole
    var content: String
    var status: MessageStatus
    var createdAt: Date
    var model: String?
    /// 服务端返回的助手消息 ID，用于对账
    var serverID: String?
    /// 失败原因（用户可读）
    var errorMessage: String?
    /// 服务端会话内单调序号（增量同步游标）
    var convSeq: Int?
    /// 客户端生成的幂等 ID：断线重发同一条不会产生第二条
    var requestID: String?
    /// 消息类型（text / image / audio）
    var kind: MessageKind = .text
    /// 服务端媒体 ID（上传成功后才有）
    var mediaID: String?
    /// 本地文件路径：上传前用于立即显示，重启后仍可离线预览
    var localMediaPath: String?
    /// 语音时长（毫秒），用于气泡上的「3″」
    var durationMs: Int?
    /// 这条回复是否来自 Mock（未接真实模型）
    var isMock: Bool = false

    init(
        id: UUID = UUID(),
        role: MessageRole,
        content: String,
        status: MessageStatus = .sent,
        createdAt: Date = Date(),
        model: String? = nil,
        serverID: String? = nil,
        errorMessage: String? = nil,
        convSeq: Int? = nil,
        requestID: String? = nil,
        kind: MessageKind = .text,
        mediaID: String? = nil,
        localMediaPath: String? = nil,
        durationMs: Int? = nil,
        isMock: Bool = false
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.status = status
        self.createdAt = createdAt
        self.model = model
        self.serverID = serverID
        self.errorMessage = errorMessage
        self.convSeq = convSeq
        self.requestID = requestID
        self.kind = kind
        self.mediaID = mediaID
        self.localMediaPath = localMediaPath
        self.durationMs = durationMs
        self.isMock = isMock
    }

    var isFromUser: Bool { role == .user }

    /// 生成一个幂等请求 ID（同一条消息重试时保持不变）。
    static func makeRequestID() -> String {
        "ios-\(UUID().uuidString.lowercased())"
    }
}

/// 服务端返回的历史消息（GET /conversations/{id}/messages）。
struct ServerMessage: Decodable, Sendable {
    let id: String
    let conversationId: String
    let role: String
    let content: String
    let status: String?
    let model: String?
    let errorCode: String?
    let latencyMs: Int?
    let createdAt: String
    let kind: String?
    let mediaId: String?

    enum CodingKeys: String, CodingKey {
        case id
        case conversationId = "conversation_id"
        case role
        case content
        case status
        case model
        case errorCode = "error_code"
        case latencyMs = "latency_ms"
        case createdAt = "created_at"
        case kind
        case mediaId = "media_id"
    }

    func toChatMessage() -> ChatMessage {
        let parsedDate = LUMIDate.parse(createdAt) ?? Date()
        return ChatMessage(
            role: MessageRole(rawValue: role) ?? .assistant,
            content: content,
            status: status == "error" ? .failed : .sent,
            createdAt: parsedDate,
            model: model,
            serverID: id,
            kind: MessageKind(rawValue: kind ?? "text") ?? .text,
            mediaID: mediaId
        )
    }
}

/// 服务端时间解析。`datetime.isoformat()` 可能带 6 位小数秒，也可能不带。
///
/// `ISO8601DateFormatter` 的 `date(from:)` / `string(from:)` 本身是线程安全的，
/// 但它是非 Sendable 类型，作为 static let 会被 Swift 6 的并发检查拦下，
/// 因此这里显式标记 `nonisolated(unsafe)` 并只暴露纯函数接口。
enum LUMIDate {
    nonisolated(unsafe) private static let fractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    nonisolated(unsafe) private static let plain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    static func parse(_ text: String) -> Date? {
        fractional.date(from: text) ?? plain.date(from: text)
    }

    static func string(from date: Date) -> String {
        fractional.string(from: date)
    }
}
