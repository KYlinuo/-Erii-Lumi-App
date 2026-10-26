import Foundation

// MARK: - 请求

struct ChatRequest: Encodable, Sendable {
    let message: String
    let conversationId: String?

    enum CodingKeys: String, CodingKey {
        case message
        case conversationId = "conversation_id"
    }
}

// MARK: - 响应

struct ChatResponse: Decodable, Sendable {
    let conversationId: String
    let userMessageId: String
    let assistantMessageId: String
    let reply: String
    let model: String
    let latencyMs: Int

    enum CodingKeys: String, CodingKey {
        case conversationId = "conversation_id"
        case userMessageId = "user_message_id"
        case assistantMessageId = "assistant_message_id"
        case reply
        case model
        case latencyMs = "latency_ms"
    }
}

struct HealthResponse: Decodable, Sendable, Equatable {
    let status: String
    let version: String
    let env: String
    let database: String
    let provider: String
    let providerModel: String
    let providerConfigured: Bool
    let apiKeyHint: String
    let authRequired: Bool

    enum CodingKeys: String, CodingKey {
        case status
        case version
        case env
        case database
        case provider
        case providerModel = "provider_model"
        case providerConfigured = "provider_configured"
        case apiKeyHint = "api_key_hint"
        case authRequired = "auth_required"
    }

    var isHealthy: Bool { status == "ok" && database == "ok" }
}

struct PersonaResponse: Decodable, Sendable, Equatable {
    let name: String
    let tagline: String
    let avatar: String
    let greeting: String
}

struct ConversationSummary: Decodable, Sendable, Equatable {
    let id: String
    let title: String
    let createdAt: String
    let updatedAt: String
    let messageCount: Int

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case messageCount = "message_count"
    }
}

// MARK: - 统一错误信封

/// 后端所有 4xx/5xx 都返回 `{"error": {"code","message","hint"}}`。
struct ErrorEnvelope: Decodable, Sendable {
    struct Detail: Decodable, Sendable {
        let code: String
        let message: String
        let hint: String?
    }

    let error: Detail
}
