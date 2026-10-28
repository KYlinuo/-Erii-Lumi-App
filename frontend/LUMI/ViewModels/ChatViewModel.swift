import Foundation
import SwiftUI

@MainActor
final class ChatViewModel: ObservableObject {
    @Published private(set) var messages: [ChatMessage] = []
    @Published private(set) var isSending = false
    @Published private(set) var isRestoring = false
    @Published private(set) var isSyncing = false
    @Published var lastError: LUMIError?
    @Published var conversationID: String? {
        didSet { UserDefaults.standard.set(conversationID, forKey: Self.conversationKey) }
    }
    /// 当前人格 key（由 AppSession 统一维护）
    @Published var characterKey: String? = "lumi"

    private static let conversationKey = "lumi.conversation.id"
    private static let cursorKey = "lumi.sync.cursor"
    private static let proactiveSeenKey = "lumi.proactive.seen"

    private let api: LUMIAPIClient
    private let store: MessageStore

    init(api: LUMIAPIClient, store: MessageStore = MessageStore(directory: MessageStore.defaultDirectory())) {
        self.api = api
        self.store = store
        self.conversationID = UserDefaults.standard.string(forKey: Self.conversationKey)
    }

    // MARK: - 历史恢复

    /// App 冷启动：先读本地快照（离线也能看），再按需从服务端补齐。
    func restoreHistory() async {
        isRestoring = true
        defer { isRestoring = false }

        do {
            let local = try await store.load()
            if !local.isEmpty {
                messages = local
            }
        } catch {
            lastError = .decodingFailure(String(describing: error))
        }

        // 本地为空但服务端可能已有记录（换机、Windows 端先聊过等场景）
        if messages.isEmpty, let conversationID {
            do {
                let remote = try await api.messages(conversationID: conversationID)
                messages = remote.map { $0.toChatMessage() }
                try await persist()
            } catch {
                // 拉取失败不阻塞使用，本地没有就展示空白
            }
        }

        if messages.isEmpty {
            await insertGreeting()
        }
    }

    private func insertGreeting() async {
        do {
            let persona = try await api.persona()
            let greeting = ChatMessage(role: .assistant, content: persona.greeting)
            messages = [greeting]
            try await persist()
        } catch {
            // 拿不到 persona 就静默：不编造任何回复
        }
    }

    // MARK: - 发送

    func send(text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isSending else { return }

        var userMessage = ChatMessage(
            role: .user,
            content: trimmed,
            status: .sending,
            requestID: ChatMessage.makeRequestID()
        )
        messages.append(userMessage)
        isSending = true
        lastError = nil

        let messageID = userMessage.id
        Task { [weak self] in
            guard let self else { return }
            await self.deliver(messageID: messageID, text: trimmed)
        }
    }

    /// 发送图片。先把字节落到本地临时文件（气泡立刻能显示），再上传换 `media_id`。
    func sendImage(data: Data, filename: String = "photo.jpg") {
        guard !isSending, !data.isEmpty else { return }
        let localPath = Self.persistLocalMedia(data: data, filename: filename)
        let message = ChatMessage(
            role: .user,
            content: "",
            status: .sending,
            requestID: ChatMessage.makeRequestID(),
            kind: .image,
            localMediaPath: localPath
        )
        messages.append(message)
        isSending = true
        lastError = nil

        Task { [weak self] in
            guard let self else { return }
            await self.uploadAndDeliver(
                messageID: message.id,
                data: data,
                filename: filename,
                mime: Self.mimeFor(filename: filename),
                kind: .image,
                durationMs: 0,
                caption: ""
            )
        }
    }

    /// 发送语音。服务端没接 ASR 时会回一段标注为「未接入」的占位文本。
    func sendVoice(fileURL: URL, duration: TimeInterval) {
        guard !isSending else { return }
        guard let data = try? Data(contentsOf: fileURL), !data.isEmpty else { return }
        let durationMs = Int(duration * 1000)
        let message = ChatMessage(
            role: .user,
            content: "",
            status: .sending,
            requestID: ChatMessage.makeRequestID(),
            kind: .audio,
            localMediaPath: fileURL.path,
            durationMs: durationMs
        )
        messages.append(message)
        isSending = true
        lastError = nil

        Task { [weak self] in
            guard let self else { return }
            await self.uploadAndDeliver(
                messageID: message.id,
                data: data,
                filename: "voice.m4a",
                mime: "audio/mp4",
                kind: .audio,
                durationMs: durationMs,
                caption: ""
            )
        }
    }

    private func uploadAndDeliver(
        messageID: UUID,
        data: Data,
        filename: String,
        mime: String,
        kind: MessageKind,
        durationMs: Int,
        caption: String
    ) async {
        do {
            let asset = try await api.uploadMedia(
                data: data,
                filename: filename,
                mime: mime,
                kind: kind.rawValue,
                durationMs: durationMs
            )
            if let index = messages.firstIndex(where: { $0.id == messageID }) {
                messages[index].mediaID = asset.id
                if kind == .audio && messages[index].durationMs == nil {
                    messages[index].durationMs = asset.durationMs
                }
            }
            await deliver(
                messageID: messageID,
                text: caption,
                mediaID: asset.id,
                kind: kind
            )
        } catch let error as LUMIError {
            isSending = false
            markFailed(messageID: messageID, error: error)
        } catch {
            isSending = false
            markFailed(messageID: messageID, error: .cannotConnectToServer)
        }
    }

    /// 对失败的消息点「重试」——沿用同一个幂等 ID，服务端不会重复生成回复。
    func retry(messageID: UUID) {
        guard let index = messages.firstIndex(where: { $0.id == messageID }) else { return }
        guard messages[index].status == .failed else { return }
        let text = messages[index].content
        let requestID = messages[index].requestID ?? ChatMessage.makeRequestID()
        let kind = messages[index].kind
        let localPath = messages[index].localMediaPath
        let mediaID = messages[index].mediaID
        let durationMs = messages[index].durationMs ?? 0
        messages[index].status = .sending
        messages[index].errorMessage = nil
        isSending = true
        lastError = nil

        Task { [weak self] in
            guard let self else { return }
            // 语音/图片：本地文件还在就重新上传（上次可能停在半路）
            if kind != .text, mediaID == nil, let localPath,
               let data = try? Data(contentsOf: URL(fileURLWithPath: localPath)) {
                let filename = (localPath as NSString).lastPathComponent
                await self.uploadAndDeliver(
                    messageID: messageID,
                    data: data,
                    filename: filename,
                    mime: Self.mimeFor(filename: filename),
                    kind: kind,
                    durationMs: durationMs,
                    caption: text
                )
                return
            }
            await self.deliver(
                messageID: messageID,
                text: text,
                requestID: requestID,
                mediaID: mediaID,
                kind: kind
            )
        }
    }

    private func deliver(
        messageID: UUID,
        text: String,
        requestID: String? = nil,
        mediaID: String? = nil,
        kind: MessageKind = .text
    ) async {
        defer { isSending = false }

        let resolvedRequestID = requestID
            ?? messages.first(where: { $0.id == messageID })?.requestID
            ?? ChatMessage.makeRequestID()

        do {
            let response = try await api.sendMessage(
                text: text,
                conversationID: conversationID,
                requestID: resolvedRequestID,
                characterKey: characterKey,
                mediaID: mediaID,
                kind: kind.rawValue
            )
            conversationID = response.conversationId

            if let index = messages.firstIndex(where: { $0.id == messageID }) {
                messages[index].status = .sent
                messages[index].requestID = resolvedRequestID
                messages[index].convSeq = response.convSeq
                messages[index].serverID = response.userMessageId
            }

            // 幂等重放：服务端没有再调模型，直接复用上次的助手消息。
            // 注意 ChatMessage 是值类型，必须按下标改回数组，否则修改会丢失。
            if response.idempotentReplay,
               let index = messages.firstIndex(where: { $0.serverID == response.assistantMessageId }) {
                messages[index].errorMessage = nil
                messages[index].status = .sent
                try await persist()
                return
            } else if response.idempotentReplay,
                      let index = messages.firstIndex(where: { $0.role == .assistant && $0.content == response.reply }) {
                // 本地没有服务端 ID（老数据）时，按内容兜底去重
                messages[index].status = .sent
                try await persist()
                return
            }

            let reply = ChatMessage(
                role: .assistant,
                content: response.reply,
                model: response.model,
                serverID: response.assistantMessageId,
                convSeq: response.convSeq
            )
            messages.append(reply)
            try await persist()
        } catch let error as LUMIError {
            markFailed(messageID: messageID, error: error)
            lastError = error
            try? await persist()
        } catch {
            let wrapped = LUMIError.cannotConnectToServer
            markFailed(messageID: messageID, error: wrapped)
            lastError = wrapped
            try? await persist()
        }
    }

    private func markFailed(messageID: UUID, error: LUMIError) {
        guard let index = messages.firstIndex(where: { $0.id == messageID }) else { return }
        messages[index].status = .failed
        messages[index].errorMessage = error.userMessage
    }

    // MARK: - 跨设备同步

    /// 增量拉取：只拿 `conv_seq > 已知游标` 的消息，并按游标去重。
    func syncFromServer() async throws {
        guard let conversationID else { return }
        isSyncing = true
        defer { isSyncing = false }

        let known = Self.loadCursor()[conversationID] ?? 0
        let remote = try await api.syncConversation(conversationID: conversationID, after: known)
        guard !remote.isEmpty else { return }

        let knownIDs = Set(messages.compactMap(\.serverID))
        var added: [ChatMessage] = []
        var maxSeq = known

        for item in remote {
            if let seq = item.convSeq { maxSeq = max(maxSeq, seq) }
            if item.isDeleted {
                messages.removeAll { $0.serverID == item.id }
                continue
            }
            guard !knownIDs.contains(item.id) else { continue }
            added.append(item.toChatMessage())
        }

        if !added.isEmpty {
            messages.append(contentsOf: added)
            messages.sort { lhs, rhs in
                if lhs.createdAt == rhs.createdAt {
                    return (lhs.convSeq ?? 0) < (rhs.convSeq ?? 0)
                }
                return lhs.createdAt < rhs.createdAt
            }
        }
        Self.saveCursor(conversationID, seq: maxSeq)
        try await persist()
    }

    /// 拉取服务端排好队的主动消息（App 未打开期间产生的）。
    ///
    /// 诚实说明：这不是 APNs 远程推送，App 必须自己联网来取。
    func pullProactiveMessages() async {
        do {
            let pending = try await api.proactivePending(characterKey: characterKey)
            guard !pending.isEmpty else { return }
            var seen = Set(UserDefaults.standard.array(forKey: Self.proactiveSeenKey) as? [String] ?? [])

            var appended = false
            for item in pending where !seen.contains(item.id) {
                messages.append(
                    ChatMessage(
                        role: .assistant,
                        content: item.content,
                        model: "proactive:\(item.reason)"
                    )
                )
                seen.insert(item.id)
                appended = true
            }
            if appended {
                UserDefaults.standard.set(Array(seen), forKey: Self.proactiveSeenKey)
                try await persist()
            }
            _ = try? await api.markProactiveDelivered(ids: Array(seen))
        } catch {
            // 主动消息拉取失败不影响主流程
        }
    }

    // MARK: - 本地数据

    private static func loadCursor() -> [String: Int] {
        (UserDefaults.standard.dictionary(forKey: Self.cursorKey) as? [String: Int]) ?? [:]
    }

    private static func saveCursor(_ conversationID: String, seq: Int) {
        var map = loadCursor()
        map[conversationID] = max(map[conversationID] ?? 0, seq)
        UserDefaults.standard.set(map, forKey: Self.cursorKey)
    }

    private func persist() async throws {
        try await store.save(messages)
    }

    func clearHistory() async {
        messages = []
        conversationID = nil
        UserDefaults.standard.removeObject(forKey: Self.cursorKey)
        try? await store.clear()
        await insertGreeting()
    }

    // MARK: - 媒体辅助

    /// 把图片字节写成临时文件，气泡可以在上传完成前就显示出来。
    static func persistLocalMedia(data: Data, filename: String) -> String? {
        let dir = mediaDirectory()
        let ext = (filename as NSString).pathExtension.isEmpty ? "jpg" : (filename as NSString).pathExtension
        let url = dir.appendingPathComponent("\(UUID().uuidString).\(ext)")
        do {
            try data.write(to: url, options: .atomic)
            return url.path
        } catch {
            return nil
        }
    }

    static func mediaDirectory() -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("LUMI/media", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    static func mimeFor(filename: String) -> String {
        switch (filename as NSString).pathExtension.lowercased() {
        case "png": return "image/png"
        case "gif": return "image/gif"
        case "webp": return "image/webp"
        case "heic": return "image/heic"
        case "m4a": return "audio/mp4"
        case "wav": return "audio/wav"
        case "mp3": return "audio/mpeg"
        default: return "image/jpeg"
        }
    }
}
