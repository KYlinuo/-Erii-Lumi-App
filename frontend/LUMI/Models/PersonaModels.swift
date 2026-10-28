import Foundation

// MARK: - 人格 / 角色

/// 一个 AI 角色（人格）定义。
///
/// 服务端保留多套人格且互不合并：LUMI / 林穗 / 祁鹿 / 沈昼 / 绘梨衣。
/// `source` 说明这套设定的来历：
/// - `builtin` / `erii-pet`：项目内置或沿用桌宠素材；
/// - `agent-authored`：本机未找到原始设计文档，由 AI 工程师拟定的定稿，
///   用户拿到原文后可直接覆盖——UI 会如实标注，不冒充「就是你原来的设定」。
struct CharacterInfo: Decodable, Sendable, Identifiable, Equatable {
    let id: String
    let key: String
    let name: String
    let tagline: String
    let avatarKey: String
    let greeting: String
    let summary: String
    let traits: [String]
    let interests: [String]
    let background: String
    let speakingStyle: String
    let source: String
    let isDefault: Bool
    let isActive: Bool

    enum CodingKeys: String, CodingKey {
        case id, key, name, tagline, summary, background, source
        case avatarKey = "avatar_key"
        case greeting
        case traits
        case interests
        case speakingStyle = "speaking_style"
        case isDefault = "is_default"
        case isActive = "is_active"
    }

    /// 由 AI 工程师拟定（本机没有原始设计文档），可随时被用户原文覆盖。
    var isAgentAuthored: Bool { source == "agent-authored" }

    /// 本机没有原始设定文档、需要用户补充（保留给未来真正缺失的情况）。
    var isProvisional: Bool { source == "reconstructed" }

    /// 是否为来自 Windows 桌宠的既有设定。
    var fromDesktopPet: Bool { source == "erii-pet" }
}

/// 角色待机台词（绘梨衣的来自桌宠已有素材）。
struct IdleLinesResponse: Decodable, Sendable {
    let characterKey: String
    let characterName: String
    /// 永远为 true：这些是角色设定的句子，不是任何人的真实经历。
    let fictional: Bool
    let notice: String
    let count: Int
    let lines: [String]

    enum CodingKeys: String, CodingKey {
        case characterKey = "character_key"
        case characterName = "character_name"
        case fictional
        case notice
        case count
        case lines
    }
}

// MARK: - 长期记忆

/// 一条长期记忆。
///
/// `subject` 决定归属：`user` 是真实用户信息（跨人格共享），
/// `character`/`relationship` 按人物隔离，因此不同人格不会互相污染。
struct MemoryItem: Decodable, Sendable, Identifiable, Equatable {
    let id: String
    let userId: String?
    let characterId: String?
    let scope: String
    let subject: String
    let content: String
    let sourceType: String
    let sourceMessageId: String?
    let sourceRef: String
    let confidence: Double
    let salience: Int
    let status: String
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, scope, subject, content, confidence, salience, status
        case userId = "user_id"
        case characterId = "character_id"
        case sourceType = "source_type"
        case sourceMessageId = "source_message_id"
        case sourceRef = "source_ref"
        case createdAt = "created_at"
    }

    /// 从聊天文本推断的内容：必须显式标注，不能被当成用户说过的确定事实。
    var isInferred: Bool { sourceType == "inferred" }

    /// 来自虚构世界模拟：属于角色设定，不是用户事实。
    var isSimulated: Bool { sourceType == "world_simulation" }

    /// 角色的虚构人生，与用户真实信息严格隔离。
    var isFictionalLife: Bool { scope == "fictional_life" }

    var scopeLabel: String {
        switch scope {
        case "user_fact": return "事实"
        case "user_preference": return "喜好"
        case "shared_experience": return "共同经历"
        case "important_event": return "重要事件"
        case "pending_topic": return "待续话题"
        case "fictional_life": return "她的虚构生活"
        default: return scope
        }
    }
}

struct MemorySummary: Decodable, Sendable {
    let characterKey: String?
    let characterId: String?
    let byScope: [String: Int]
    let total: Int

    enum CodingKeys: String, CodingKey {
        case characterKey = "character_key"
        case characterId = "character_id"
        case byScope = "by_scope"
        case total
    }
}

// MARK: - 虚构人生

/// 角色虚构人生中的一条事件。
///
/// `simulated` 永远为 true：这是设定里的故事，**不是**用户真实经历，
/// 界面必须显式标注，禁止冒充真实记忆。
struct WorldEventItem: Decodable, Sendable, Identifiable, Equatable {
    let id: String
    let characterId: String
    let kind: String
    let title: String
    let content: String
    let simulated: Bool
    let mood: String
    let meta: [String: String]
    let occurredAt: String?

    enum CodingKeys: String, CodingKey {
        case id, kind, title, content, simulated, mood, meta
        case characterId = "character_id"
        case occurredAt = "occurred_at"
    }

    var kindLabel: String {
        switch kind {
        case "diary": return "日记"
        case "hobby": return "爱好"
        case "reading": return "读书"
        case "relationship": return "关系"
        case "goal": return "目标"
        default: return kind
        }
    }

    var occurredDate: Date? {
        guard let occurredAt else { return nil }
        return LUMIDate.parse(occurredAt)
    }
}

struct DiaryResponse: Decodable, Sendable {
    let characterKey: String
    let characterName: String
    let notice: String
    let events: [WorldEventItem]

    enum CodingKeys: String, CodingKey {
        case characterKey = "character_key"
        case characterName = "character_name"
        case notice
        case events
    }
}

// MARK: - 设备

/// 设备注册结果：`token` 是**唯一一次**的明文令牌，必须立刻写入 Keychain。
struct DeviceRegistration: Decodable, Sendable {
    let deviceId: String
    let userId: String
    let name: String
    let platform: String
    let token: String
    let tokenHint: String
    let scopes: [String]

    enum CodingKeys: String, CodingKey {
        case name, platform, token, scopes
        case deviceId = "device_id"
        case userId = "user_id"
        case tokenHint = "token_hint"
    }
}

struct DeviceRegistrationRequest: Encodable, Sendable {
    let name: String
    let platform: String
    let appVersion: String
    let scopes: [String]?

    enum CodingKeys: String, CodingKey {
        case name, platform, scopes
        case appVersion = "app_version"
    }
}

struct DeviceInfo: Decodable, Sendable, Identifiable {
    let id: String
    let userId: String
    let name: String
    let platform: String
    let tokenHint: String
    let scopes: [String]
    let revoked: Bool
    let lastSeenAt: String?

    enum CodingKeys: String, CodingKey {
        case id, name, platform, scopes, revoked
        case userId = "user_id"
        case tokenHint = "token_hint"
        case lastSeenAt = "last_seen_at"
    }
}

struct WhoAmI: Decodable, Sendable {
    let kind: String
    let userId: String?
    let deviceId: String?
    let scopes: [String]

    enum CodingKeys: String, CodingKey {
        case kind, scopes
        case userId = "user_id"
        case deviceId = "device_id"
    }
}

// MARK: - 跨设备同步

/// 同步用的消息表示：比历史接口多了幂等 ID、会话内序号与软删除标记。
struct SyncMessage: Decodable, Sendable {
    let id: String
    let conversationId: String
    let role: String
    let content: String
    let status: String
    let model: String?
    let errorCode: String?
    let latencyMs: Int?
    let requestId: String?
    let convSeq: Int?
    let clientTs: String?
    let deletedAt: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, role, content, status, model
        case conversationId = "conversation_id"
        case errorCode = "error_code"
        case latencyMs = "latency_ms"
        case requestId = "request_id"
        case convSeq = "conv_seq"
        case clientTs = "client_ts"
        case deletedAt = "deleted_at"
        case createdAt = "created_at"
    }

    var isDeleted: Bool { deletedAt != nil }

    func toChatMessage() -> ChatMessage {
        ChatMessage(
            role: MessageRole(rawValue: role) ?? .assistant,
            content: content,
            status: status == "error" ? .failed : .sent,
            createdAt: (createdAt.flatMap { LUMIDate.parse($0) }) ?? Date(),
            model: model,
            serverID: id,
            convSeq: convSeq,
            requestID: requestId
        )
    }
}

struct SyncRequest: Encodable, Sendable {
    let since: [String: Int]
    let limit: Int
}

struct ConversationDelta: Decodable, Sendable {
    let conversationId: String
    let title: String
    let characterId: String?
    let updatedAt: String
    let cursor: Int
    let hasMore: Bool
    let messages: [SyncMessage]

    enum CodingKeys: String, CodingKey {
        case title, cursor, messages
        case conversationId = "conversation_id"
        case characterId = "character_id"
        case updatedAt = "updated_at"
        case hasMore = "has_more"
    }
}

struct SyncResponse: Decodable, Sendable {
    let conversations: [ConversationDelta]
    let globalCursor: Int
    let serverTime: String

    enum CodingKeys: String, CodingKey {
        case conversations
        case globalCursor = "global_cursor"
        case serverTime = "server_time"
    }
}

// MARK: - 主动联系

struct ProactiveMessageItem: Decodable, Sendable, Identifiable {
    let id: String
    let characterId: String
    let conversationId: String?
    let content: String
    let reason: String
    let status: String
    let scheduledAt: String?

    enum CodingKeys: String, CodingKey {
        case id, content, reason, status
        case characterId = "character_id"
        case conversationId = "conversation_id"
        case scheduledAt = "scheduled_at"
    }
}

struct ProactiveStatus: Decodable, Sendable {
    let enabled: Bool
    let allowedNow: Bool
    let reason: String
    let dailyCap: Int
    let windows: String
    let quietHours: String
    /// 明确告诉 UI：**没有**实现 APNs 远程推送，只能靠 App 自己拉取。
    let apnsRemotePush: Bool
    let note: String

    enum CodingKeys: String, CodingKey {
        case enabled, reason, windows, note
        case allowedNow = "allowed_now"
        case dailyCap = "daily_cap"
        case quietHours = "quiet_hours"
        case apnsRemotePush = "apns_remote_push"
    }
}
