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
