import Foundation

// MARK: - 请求

struct ChatRequest: Encodable, Sendable {
    let message: String
    let conversationId: String?
    /// 幂等 ID：同一条消息重试时复用，服务端不会重复生成回复
    let requestId: String?
    /// 人格 key（缺省沿用会话已绑定的人格）
    let characterKey: String?
    /// v0.3：图片 / 语音消息的媒体 ID（先上传，再带上它发消息）
    let mediaId: String?
    /// v0.3：消息类型 text / image / audio
    let kind: String

    enum CodingKeys: String, CodingKey {
        case message
        case conversationId = "conversation_id"
        case requestId = "request_id"
        case characterKey = "character_key"
        case mediaId = "media_id"
        case kind
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
    let characterId: String?
    let convSeq: Int?
    /// true 表示服务端没有再调用模型，直接重放了上次结果
    let idempotentReplay: Bool

    enum CodingKeys: String, CodingKey {
        case conversationId = "conversation_id"
        case userMessageId = "user_message_id"
        case assistantMessageId = "assistant_message_id"
        case reply
        case model
        case latencyMs = "latency_ms"
        case characterId = "character_id"
        case convSeq = "conv_seq"
        case idempotentReplay = "idempotent_replay"
    }

    init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        conversationId = try c.decode(String.self, forKey: .conversationId)
        userMessageId = try c.decode(String.self, forKey: .userMessageId)
        assistantMessageId = try c.decode(String.self, forKey: .assistantMessageId)
        reply = try c.decode(String.self, forKey: .reply)
        model = try c.decode(String.self, forKey: .model)
        latencyMs = try c.decode(Int.self, forKey: .latencyMs)
        // v0.1 服务器可能不返回这些字段，用 decodeIfPresent 保持向后兼容
        characterId = try c.decodeIfPresent(String.self, forKey: .characterId)
        convSeq = try c.decodeIfPresent(Int.self, forKey: .convSeq)
        idempotentReplay = try c.decodeIfPresent(Bool.self, forKey: .idempotentReplay) ?? false
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
    // v0.2
    let schemaVersion: String?
    let isMock: Bool?
    let deviceCount: Int?
    let characterCount: Int?
    let proactiveEnabled: Bool?
    let timezone: String?

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
        case schemaVersion = "schema_version"
        case isMock = "is_mock"
        case deviceCount = "device_count"
        case characterCount = "character_count"
        case proactiveEnabled = "proactive_enabled"
        case timezone
    }

    init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = try c.decode(String.self, forKey: .status)
        version = try c.decode(String.self, forKey: .version)
        env = try c.decode(String.self, forKey: .env)
        database = try c.decode(String.self, forKey: .database)
        provider = try c.decode(String.self, forKey: .provider)
        providerModel = try c.decode(String.self, forKey: .providerModel)
        providerConfigured = try c.decode(Bool.self, forKey: .providerConfigured)
        apiKeyHint = try c.decode(String.self, forKey: .apiKeyHint)
        authRequired = try c.decode(Bool.self, forKey: .authRequired)
        // v0.1 服务器没有这些字段：向后兼容，缺省 nil
        schemaVersion = try c.decodeIfPresent(String.self, forKey: .schemaVersion)
        isMock = try c.decodeIfPresent(Bool.self, forKey: .isMock)
        deviceCount = try c.decodeIfPresent(Int.self, forKey: .deviceCount)
        characterCount = try c.decodeIfPresent(Int.self, forKey: .characterCount)
        proactiveEnabled = try c.decodeIfPresent(Bool.self, forKey: .proactiveEnabled)
        timezone = try c.decodeIfPresent(String.self, forKey: .timezone)
    }

    var isHealthy: Bool { status == "ok" && database == "ok" }
    /// 后端正在用 Mock Provider：回复不是真实模型输出，设置页必须提示。
    var usingMockProvider: Bool { isMock == true }
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
    let characterId: String?
    let userId: String?

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case messageCount = "message_count"
        case characterId = "character_id"
        case userId = "user_id"
    }

    /// 显式补回成员构造器：自定义 `init(from:)` 会抑制编译器合成的 memberwise init。
    init(
        id: String,
        title: String,
        createdAt: String,
        updatedAt: String,
        messageCount: Int,
        characterId: String? = nil,
        userId: String? = nil
    ) {
        self.id = id
        self.title = title
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.messageCount = messageCount
        self.characterId = characterId
        self.userId = userId
    }

    init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decode(String.self, forKey: .title)
        createdAt = try c.decode(String.self, forKey: .createdAt)
        updatedAt = try c.decode(String.self, forKey: .updatedAt)
        messageCount = try c.decode(Int.self, forKey: .messageCount)
        characterId = try c.decodeIfPresent(String.self, forKey: .characterId)
        userId = try c.decodeIfPresent(String.self, forKey: .userId)
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
