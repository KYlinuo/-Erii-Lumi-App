import Foundation
import SwiftUI

@MainActor
final class ChatViewModel: ObservableObject {
    @Published private(set) var messages: [ChatMessage] = []
    @Published private(set) var isSending = false
    @Published private(set) var isRestoring = false
    @Published var lastError: LUMIError?
    @Published var conversationID: String? {
        didSet { UserDefaults.standard.set(conversationID, forKey: Self.conversationKey) }
    }

    private static let conversationKey = "lumi.conversation.id"

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

        // 本地为空但服务端可能已有记录（换机等场景）
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

        var userMessage = ChatMessage(role: .user, content: trimmed, status: .sending)
        messages.append(userMessage)
        isSending = true
        lastError = nil

        let messageID = userMessage.id
        Task { [weak self] in
            guard let self else { return }
            await self.deliver(messageID: messageID, text: trimmed)
        }
    }

    /// 对失败的消息点「重试」。
    func retry(messageID: UUID) {
        guard let index = messages.firstIndex(where: { $0.id == messageID }) else { return }
        guard messages[index].status == .failed else { return }
        let text = messages[index].content
        messages[index].status = .sending
        messages[index].errorMessage = nil
        isSending = true
        lastError = nil

        Task { [weak self] in
            guard let self else { return }
            await self.deliver(messageID: messageID, text: text)
        }
    }

    private func deliver(messageID: UUID, text: String) async {
        defer { isSending = false }

        do {
            let response = try await api.sendMessage(text: text, conversationID: conversationID)
            conversationID = response.conversationId

            if let index = messages.firstIndex(where: { $0.id == messageID }) {
                messages[index].status = .sent
            }
            let reply = ChatMessage(
                role: .assistant,
                content: response.reply,
                model: response.model,
                serverID: response.assistantMessageId
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

    // MARK: - 本地数据

    private func persist() async throws {
        try await store.save(messages)
    }

    func clearHistory() async {
        messages = []
        conversationID = nil
        try? await store.clear()
        await insertGreeting()
    }

    /// 从服务端重新拉取当前会话（设置页「同步历史」用）。
    func syncFromServer() async throws {
        guard let conversationID else { return }
        let remote = try await api.messages(conversationID: conversationID)
        messages = remote.map { $0.toChatMessage() }
        try await persist()
    }
}
