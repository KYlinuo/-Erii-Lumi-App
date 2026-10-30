import SwiftUI

/// 聊天记录搜索：按关键词检索当前会话的历史消息，点击后跳转到对应位置。
struct MessageSearchView: View {
    let conversationID: String?
    let onSelect: (String, String) -> Void

    @EnvironmentObject private var session: AppSession
    @Environment(\.dismiss) private var dismiss

    @State private var query = ""
    @State private var results: [SyncMessage] = []
    @State private var isLoading = false
    @State private var searched = false

    var body: some View {
        NavigationStack {
            List {
                if searched && results.isEmpty {
                    LUMIEmptyState(
                        symbol: "magnifyingglass",
                        title: "没有找到相关内容",
                        subtitle: "换个关键词试试，或直接问绘梨衣。"
                    )
                } else {
                    ForEach(results, id: \.id) { msg in
                        Button {
                            onSelect(msg.id, msg.content)
                            dismiss()
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 6) {
                                    Text(msg.role == "user" ? "我" : "绘梨衣")
                                        .font(.caption2.weight(.semibold))
                                        .foregroundStyle(msg.role == "user" ? LUMIStyle.violet : LUMIStyle.sakura)
                                    if let ts = msg.createdAt {
                                        Text(Self.shortTime(ts))
                                            .font(.caption2)
                                            .foregroundStyle(.tertiary)
                                    }
                                }
                                Text(msg.content)
                                    .font(.subheadline)
                                    .lineLimit(2)
                                    .foregroundStyle(.primary)
                            }
                            .padding(.vertical, 4)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .searchable(text: $query, prompt: "搜索聊天记录")
            .onSubmit(of: .search) { Task { await runSearch() } }
            .navigationTitle("搜索")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("关闭") { dismiss() }
                }
            }
        }
    }

    private func runSearch() async {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !needle.isEmpty, let conversationID else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            results = try await session.api.searchMessages(conversationID: conversationID, query: needle)
            searched = true
        } catch {
            results = []
            searched = true
        }
    }

    /// 把 ISO8601 时间戳裁剪成「MM-DD HH:mm」便于展示。
    private static func shortTime(_ iso: String) -> String {
        let cleaned = iso.replacingOccurrences(of: "T", with: " ")
        guard cleaned.count >= 16 else { return cleaned }
        let start = cleaned.index(cleaned.startIndex, offsetBy: 5)
        let end = cleaned.index(cleaned.startIndex, offsetBy: 16)
        return String(cleaned[start..<end])
    }
}
