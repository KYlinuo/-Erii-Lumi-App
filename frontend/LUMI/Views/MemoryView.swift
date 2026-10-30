import SwiftUI

/// 记忆页面：查看、新增、归档、删除长期记忆。
///
/// 分组规则与后端隔离策略一致：
/// - 「关于你」= 真实用户信息，跨人格共享；
/// - 「你们之间」= 与当前人格的共同经历；
/// - 「她的虚构生活」= 角色自己的设定，严格隔离、单独展示。
struct MemoryView: View {
    @StateObject private var viewModel: MemoryViewModel
    @State private var newContent = ""
    @State private var newScope = "user_fact"
    @State private var showComposer = false

    init(viewModel: MemoryViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    private static let scopes: [(value: String, label: String)] = [
        ("user_fact", "事实"),
        ("user_preference", "喜好"),
        ("important_event", "重要事件"),
        ("pending_topic", "待续话题"),
    ]

    var body: some View {
        ZStack {
            LUMIStyle.background
            LUMIStyle.glow

            ScrollView {
                VStack(spacing: 16) {
                    summaryBar

                    if viewModel.isLoading && viewModel.items.isEmpty {
                        ProgressView("正在读取记忆…").padding(.top, 40)
                    } else if viewModel.filtered.isEmpty {
                        LUMIEmptyState(
                            symbol: "brain",
                            title: "还没有记忆",
                            subtitle: "聊天中提到的事实与喜好会被自动记下来，也可以手动添加。"
                        )
                    } else {
                        section("关于你", items: viewModel.userMemories, symbol: "person.fill",
                               note: "这些是所有人格共享的真实信息。")
                        section("你们之间", items: viewModel.relationshipMemories,
                               symbol: "bubble.left.and.bubble.right.fill",
                               note: "只属于当前人格的共同经历。")
                        section("她的虚构生活", items: viewModel.fictionalMemories,
                               symbol: "theatermasks.fill",
                               note: "角色设定中的虚构内容，与你的真实信息隔离。")
                    }
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 18)
            }
        }
        .navigationTitle("记忆")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $viewModel.searchText, prompt: "搜索记忆")
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    showComposer = true
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showComposer) {
            composerSheet
        }
        .task { await viewModel.load() }
        .refreshable { await viewModel.load() }
    }

    // MARK: - 概览

    private var summaryBar: some View {
        LUMICard {
            HStack(spacing: 16) {
                Image(systemName: "brain.head.profile")
                    .font(.title3)
                    .foregroundStyle(LUMIStyle.violet)
                VStack(alignment: .leading, spacing: 2) {
                    Text("共 \(viewModel.items.count) 条记忆")
                        .font(.subheadline.weight(.semibold))
                    if let summary = viewModel.summary {
                        Text(scopeBreakdown(summary))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                }
                Spacer(minLength: 0)
            }
        }
    }

    // MARK: - 分组

    private func section(
        _ title: String, items: [MemoryItem], symbol: String, note: String
    ) -> some View {
        Group {
            if !items.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Label(title, systemImage: symbol)
                        .font(.headline)
                        .padding(.leading, 4)
                    Text(note)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .padding(.leading, 4)

                    ForEach(items) { item in
                        memoryRow(item)
                    }
                }
            }
        }
    }

    private func memoryRow(_ item: MemoryItem) -> some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    LUMIBadge(
                        text: item.scopeLabel,
                        color: item.isFictionalLife ? LUMIStyle.sakura : LUMIStyle.violet
                    )
                    if item.isInferred {
                        LUMIBadge(text: "推测", color: .orange)
                    } else if item.isSimulated {
                        LUMIBadge(text: "角色设定", color: LUMIStyle.sakura)
                    }
                    Text("可信度 \(Int(item.confidence * 100))%")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                Text(item.content)
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
                if item.isPinned {
                    Label("已固定", systemImage: "pin.fill")
                        .font(.caption2)
                        .foregroundStyle(LUMIStyle.sakura)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(14)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(item.isPinned ? LUMIStyle.sakura.opacity(0.4) : Color.white.opacity(0.07), lineWidth: 1)
        )
        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
            Button(role: .destructive) {
                Task { await viewModel.delete(item) }
            } label: {
                Label("删除", systemImage: "trash")
            }
            Button {
                Task { await viewModel.archive(item) }
            } label: {
                Label("归档", systemImage: "archivebox")
            }
            .tint(.orange)
        }
        .swipeActions(edge: .leading, allowsFullSwipe: true) {
            Button {
                Task { await viewModel.togglePin(item) }
            } label: {
                Label(item.isPinned ? "取消固定" : "固定", systemImage: item.isPinned ? "pin.slash" : "pin")
            }
            .tint(LUMIStyle.sakura)
        }
    }

    // MARK: - 新增

    private var composerSheet: some View {
        NavigationStack {
            Form {
                Section("内容") {
                    TextField("写一条你希望她记住的事", text: $newContent, axis: .vertical)
                        .lineLimit(3...6)
                }
                Section("类型") {
                    Picker("类型", selection: $newScope) {
                        ForEach(Self.scopes, id: \.value) { scope in
                            Text(scope.label).tag(scope.value)
                        }
                    }
                    .pickerStyle(.segmented)
                }
                Section {
                    Text("手动添加的记忆会被标记为「用户说过」，可信度最高；"
                         + "聊天中自动抽取的会标记为「推测」。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .scrollContentBackground(.hidden)
            .background(LUMIStyle.pageBackground)
            .navigationTitle("新增记忆")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { showComposer = false }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        let content = newContent
                        newContent = ""
                        showComposer = false
                        Task { await viewModel.add(scope: newScope, content: content) }
                    }
                    .disabled(newContent.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }

    /// 各类型记忆的占比摘要。
    /// 注意：Swift 的单行字符串插值里不能换行写多语句表达式，
    /// 所以这里先算好再交给 Text。
    private func scopeBreakdown(_ summary: MemorySummary) -> String {
        let parts = summary.byScope
            .sorted { $0.value > $1.value }
            .map { "\($0.key) \($0.value)" }
            .joined(separator: " · ")
        return parts.isEmpty ? "还没有分类统计" : "按类型：" + parts
    }
}
