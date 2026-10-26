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

    init(
        id: UUID = UUID(),
        role: MessageRole,
        content: String,
        status: MessageStatus = .sent,
        createdAt: Date = Date(),
        model: String? = nil,
        serverID: String? = nil,
        errorMessage: String? = nil
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.status = status
        self.createdAt = createdAt
        self.model = model
        self.serverID = serverID
        self.errorMessage = errorMessage
    }

    var isFromUser: Bool { role == .user }
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
    }

    func toChatMessage() -> ChatMessage {
        let parsedDate = ISO8601DateFormatter.lumiFractional.date(from: createdAt) ?? Date()
        return ChatMessage(
            role: MessageRole(rawValue: role) ?? .assistant,
            content: content,
            status: status == "error" ? .failed : .sent,
            createdAt: parsedDate,
            model: model,
            serverID: id
        )
    }
}

extension ISO8601DateFormatter {
    /// 服务端用 `datetime.isoformat()`，可能带 6 位小数秒与 +00:00，需要两种格式兜底。
    static let lumiFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
}
