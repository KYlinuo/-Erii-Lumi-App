import Foundation
import SwiftUI

/// 长期记忆浏览与管理。
///
/// 展示规则：推断出来的条目必须带「推测」标记；角色虚构生活单独分组，
/// 绝不与用户真实信息混在一起。
@MainActor
final class MemoryViewModel: ObservableObject {
    @Published private(set) var items: [MemoryItem] = []
    @Published private(set) var summary: MemorySummary?
    @Published private(set) var isLoading = false
    @Published var lastError: LUMIError?
    @Published var searchText = ""

    /// 当前查看的人格 key；nil 表示只看跨人格共享的用户层记忆。
    var characterKey: String?

    private let api: LUMIAPIClient

    init(api: LUMIAPIClient, characterKey: String? = nil) {
        self.api = api
        self.characterKey = characterKey
    }

    var filtered: [MemoryItem] {
        guard !searchText.trimmingCharacters(in: .whitespaces).isEmpty else { return items }
        let needle = searchText.lowercased()
        return items.filter { $0.content.lowercased().contains(needle) }
    }

    /// 用户真实信息（跨人格共享）
    var userMemories: [MemoryItem] { filtered.filter { $0.subject == "user" } }
    /// 与当前人格相关的关系记忆
    var relationshipMemories: [MemoryItem] { filtered.filter { $0.subject == "relationship" } }
    /// 角色自己的虚构人生（严格隔离）
    var fictionalMemories: [MemoryItem] { filtered.filter { $0.subject == "character" } }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let fetched = api.memories(characterKey: characterKey, limit: 200)
            async let summaryFetch = api.memorySummary(characterKey: characterKey)
            items = try await fetched
            summary = try await summaryFetch
            lastError = nil
        } catch let error as LUMIError {
            lastError = error
        } catch {
            lastError = .cannotConnectToServer
        }
    }

    func add(scope: String, content: String) async {
        let trimmed = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        do {
            _ = try await api.createMemory(scope: scope, content: trimmed)
            await load()
        } catch let error as LUMIError {
            lastError = error
        } catch {
            lastError = .cannotConnectToServer
        }
    }

    func archive(_ item: MemoryItem) async {
        do {
            try await api.archiveMemory(id: item.id)
            await load()
        } catch let error as LUMIError {
            lastError = error
        } catch {
            lastError = .cannotConnectToServer
        }
    }

    func delete(_ item: MemoryItem) async {
        do {
            try await api.deleteMemory(id: item.id)
            await load()
        } catch let error as LUMIError {
            lastError = error
        } catch {
            lastError = .cannotConnectToServer
        }
    }
}
