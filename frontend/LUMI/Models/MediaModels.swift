import Foundation

/// 服务端媒体资产（POST /api/v1/media 的返回体）。
struct MediaAssetDTO: Decodable, Sendable, Equatable {
    let id: String
    let kind: String
    let mime: String
    let byteSize: Int
    let durationMs: Int

    enum CodingKeys: String, CodingKey {
        case id
        case kind
        case mime
        case byteSize = "byte_size"
        case durationMs = "duration_ms"
    }
}

/// 语音转写结果。**`mock == true` 表示后端没有接入 ASR**，
/// 界面必须显示「未接入」，不能把它当成真实识别文本。
struct TranscriptDTO: Decodable, Sendable {
    let text: String
    let mock: Bool
    let language: String
    let durationMs: Int?

    enum CodingKeys: String, CodingKey {
        case text
        case mock
        case language
        case durationMs = "duration_ms"
    }
}

/// 语音能力状态（GET /api/v1/speech/status）。
struct SpeechStatusDTO: Decodable, Sendable {
    let asrConfigured: Bool
    let ttsConfigured: Bool
    let mock: Bool
    let notice: String

    enum CodingKeys: String, CodingKey {
        case asrConfigured = "asr_configured"
        case ttsConfigured = "tts_configured"
        case mock
        case notice
    }
}

/// 实时通话能力状态（GET /api/v1/call/status）。
struct CallStatusDTO: Decodable, Sendable {
    let configured: Bool
    let livekitUrl: String?
    let sttConfigured: Bool
    let ttsConfigured: Bool
    let note: String

    enum CodingKeys: String, CodingKey {
        case configured
        case livekitUrl = "livekit_url"
        case sttConfigured = "stt_configured"
        case ttsConfigured = "tts_configured"
        case note
    }
}

/// 一次通话的连接信息（POST /api/v1/call/token）。
struct CallTokenDTO: Decodable, Sendable {
    let configured: Bool
    let url: String
    let token: String
    let room: String
    let identity: String
}

/// 回复风格参数（GET/POST /api/v1/style，需求 09）。
struct StyleProfileDTO: Codable, Sendable {
    var replyLength: String = "medium"       // short / medium / long
    var questionFrequency: String = "medium" // low / medium / high
    var emojiFrequency: String = "medium"    // low / medium / high
    var actionDescription: Bool = true
    var address: String = ""

    enum CodingKeys: String, CodingKey {
        case replyLength = "reply_length"
        case questionFrequency = "question_frequency"
        case emojiFrequency = "emoji_frequency"
        case actionDescription = "action_description"
        case address
    }
}

/// 一条约定（GET/POST/PATCH /api/v1/promises，需求 20）。
struct PromiseDTO: Codable, Identifiable, Sendable {
    let id: String
    var content: String
    var dueAt: String?
    var certainty: String
    var status: String
    var note: String

    enum CodingKeys: String, CodingKey {
        case id, content, certainty, status, note
        case dueAt = "due_at"
    }
}
