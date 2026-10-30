import SwiftUI

struct TimelineEntry: Decodable, Identifiable, Sendable {
    let id: String
    let title: String
    let content: String
    let verified: Bool
    let simulated: Bool
    let occurredAt: String?
    enum CodingKeys: String, CodingKey {
        case id, title, content, verified, simulated
        case occurredAt = "occurred_at"
    }
}

struct TimelineView: View {
    @EnvironmentObject private var session: AppSession
    @State private var entries: [TimelineEntry] = []
    @State private var includeCandidates = false
    @State private var content = ""
    @State private var busy = false
    @State private var errorText: String?

    var body: some View {
        List {
            Section {
                Toggle("显示待确认回忆", isOn: $includeCandidates)
                HStack {
                    TextField("记下今天的一件小事", text: $content, axis: .vertical)
                    Button("记下") { perform { try await session.api.addTimeline(content: content); content = "" } }
                        .disabled(content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || busy)
                }
                Button("从聊天收藏与约定整理回忆") {
                    perform { try await session.api.syncTimeline() }
                }.disabled(busy)
            } footer: {
                Text("待确认内容不会自动当作真实经历。虚构生活会单独标注。")
            }
            if busy { ProgressView("正在更新…") }
            if let errorText {
                Text(errorText).foregroundStyle(.red)
                Button("重试") { perform {} }
            }
            if entries.isEmpty && !busy && errorText == nil {
                Text("还没有回忆。可以记下一件小事，或整理已收藏的聊天。")
                    .foregroundStyle(.secondary)
            }
            ForEach(entries) { entry in
                VStack(alignment: .leading, spacing: 6) {
                    Text(entry.title).font(.headline)
                    Text(entry.content)
                    if let date = entry.occurredAt.flatMap({ LUMIDate.parse($0) }) {
                        Text(date, style: .date).font(.caption).foregroundStyle(.secondary)
                    }
                    if entry.simulated { Text("虚构生活").font(.caption).foregroundStyle(.secondary) }
                    if !entry.verified {
                        Button("确认这条回忆") { perform { try await session.api.verifyTimeline(id: entry.id) } }
                            .disabled(busy)
                    }
                }
                .swipeActions {
                    Button("删除", role: .destructive) { perform { try await session.api.deleteTimeline(id: entry.id) } }
                        .disabled(busy)
                }
            }
        }
        .scrollContentBackground(.hidden)
        .task(id: includeCandidates) { await reload() }
        .refreshable { await reload() }
    }

    @MainActor private func perform(_ action: @escaping @MainActor () async throws -> Void) {
        guard !busy else { return }
        busy = true
        Task {
            defer { busy = false }
            do {
                try await action()
                entries = try await session.api.timeline(includeCandidates: includeCandidates)
                errorText = nil
            } catch { errorText = (error as? LUMIError)?.userMessage ?? "更新失败，请重试。" }
        }
    }

    @MainActor private func reload() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            entries = try await session.api.timeline(includeCandidates: includeCandidates)
            errorText = nil
        } catch { errorText = (error as? LUMIError)?.userMessage ?? "加载失败，请重试。" }
    }
}
