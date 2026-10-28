import PhotosUI
import SwiftUI

/// 人物主页：角色的形象、背景、性格、兴趣与虚构生活介绍。
///
/// 设计约束：
/// - 保留多套人格，彼此独立展示，不做合并；
/// - `agent-authored` 的人格会标注「AI 拟定 · 可替换」，如实说明这是工程师拟定的版本；
/// - 明确声明她是虚构 AI 角色。
struct ProfileView: View {
    @StateObject private var viewModel: PersonaViewModel
    @EnvironmentObject private var chatViewModel: ChatViewModel
    @ObservedObject private var appearance = AppearanceStore.shared
    @State private var characterAvatarItem: PhotosPickerItem?

    init(viewModel: PersonaViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        ZStack {
            LUMIStyle.background
            LUMIStyle.glow

            ScrollView {
                VStack(spacing: 18) {
                    if let character = viewModel.activeCharacter {
                        header(character)
                        identityCard(character)
                        traitsCard(character)
                        backgroundCard(character)
                        if viewModel.isSwitching {
                            ProgressView("正在切换人格…")
                                .padding()
                        }
                    } else if viewModel.isLoading {
                        ProgressView("正在读取人格…").padding(.top, 60)
                    } else {
                        LUMIEmptyState(
                            symbol: "person.crop.circle.badge.questionmark",
                            title: "还没有可用的人格",
                            subtitle: "请确认后端已启动，然后下拉刷新。"
                        )
                    }

                    avatarCard
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 20)
            }
        }
        .navigationTitle("人物")
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.load() }
        .refreshable { await viewModel.load() }
    }

    // MARK: - 头部

    private func header(_ character: CharacterInfo) -> some View {
        VStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                LUMIStyle.accent(for: character.key).opacity(0.55),
                                LUMIStyle.accent(for: character.key).opacity(0.05),
                            ],
                            center: .center, startRadius: 8, endRadius: 90
                        )
                    )
                    .frame(width: 132, height: 132)
                    .blur(radius: 6)

                LUMIAvatar(size: 108)
                    .clipShape(Circle())
                    .overlay(
                        Circle().stroke(Color.white.opacity(0.22), lineWidth: 1.2)
                    )
                    .shadow(color: LUMIStyle.accent(for: character.key).opacity(0.45), radius: 18)
            }

            VStack(spacing: 4) {
                Text(character.name)
                    .font(.title2.weight(.semibold))
                Text(character.tagline)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 8) {
                LUMIBadge(text: "虚构 AI 角色", color: LUMIStyle.violet)
                if character.fromDesktopPet {
                    LUMIBadge(text: "来自桌宠设定", color: LUMIStyle.sakura)
                }
                if character.isAgentAuthored {
                    LUMIBadge(text: "AI 拟定 · 可替换", color: LUMIStyle.mint)
                }
                if character.isProvisional {
                    LUMIBadge(text: "设定待补充", color: .orange)
                }
            }
        }
        .padding(.top, 8)
    }

    // MARK: - 名片

    private func identityCard(_ character: CharacterInfo) -> some View {
        LUMICard {
            VStack(alignment: .leading, spacing: 12) {
                Label("她是谁", systemImage: "quote.bubble")
                    .font(.headline)
                Text(character.summary)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                Divider().overlay(Color.white.opacity(0.10))

                Label("说话方式", systemImage: "waveform")
                    .font(.headline)
                Text(character.speakingStyle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func traitsCard(_ character: CharacterInfo) -> some View {
        LUMICard {
            VStack(alignment: .leading, spacing: 12) {
                Label("性格与兴趣", systemImage: "sparkles")
                    .font(.headline)
                FlowChips(items: character.traits, color: LUMIStyle.violet)
                FlowChips(items: character.interests, color: LUMIStyle.aqua)
            }
        }
    }

    private func backgroundCard(_ character: CharacterInfo) -> some View {
        LUMICard {
            VStack(alignment: .leading, spacing: 10) {
                Label("虚构背景", systemImage: "book.closed")
                    .font(.headline)
                Text(character.background)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text("以上为角色设定中的虚构内容，不代表任何真实人物的经历。")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    // MARK: - 头像自定义（单人格，不做人格切换）

    private var avatarCard: some View {
        LUMICard {
            VStack(alignment: .leading, spacing: 10) {
                Text("绘梨衣的形象")
                    .font(.headline)
                Text("可以换成你自己的图。仅保存在本机，不会上传到服务器。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                HStack(spacing: 12) {
                    PhotosPicker(selection: $characterAvatarItem, matching: .images) {
                        Label("选择图片", systemImage: "photo")
                            .font(.subheadline)
                    }
                    if appearance.characterAvatar != nil {
                        Button("恢复默认", role: .destructive) {
                            appearance.clearCharacterAvatar()
                        }
                        .font(.subheadline)
                    }
                    Spacer()
                }
                .onChange(of: characterAvatarItem) { _, item in
                    guard let item else { return }
                    Task {
                        if let data = try? await item.loadTransferable(type: Data.self) {
                            await MainActor.run { appearance.saveCharacterAvatar(data) }
                        }
                        await MainActor.run { characterAvatarItem = nil }
                    }
                }
            }
        }
    }

    private var legacyPickerSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("切换人格")
                .font(.headline)
                .padding(.leading, 4)

            if viewModel.characters.isEmpty {
                LUMICard {
                    Text("暂未读取到人格列表")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            } else {
                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 150), spacing: 12)],
                    spacing: 12
                ) {
                    ForEach(viewModel.characters) { character in
                        Button {
                            Task {
                                await viewModel.select(
                                    character, conversationID: chatViewModel.conversationID
                                )
                            }
                        } label: {
                            personaChip(character)
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isSwitching)
                    }
                }
            }
        }
    }

    private func personaChip(_ character: CharacterInfo) -> some View {
        let isActive = viewModel.activeKey == character.key
        let accent = LUMIStyle.accent(for: character.key)

        return HStack(spacing: 10) {
            LUMIAvatar(size: 38, showHalo: false)
                .clipShape(Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(character.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.primary)
                Text(character.tagline)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            Spacer(minLength: 0)
            if isActive {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(accent)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(.ultraThinMaterial)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(isActive ? accent.opacity(0.8) : Color.white.opacity(0.08), lineWidth: 1.2)
        )
    }
}

/// 简单的自适应标签流（避免引入额外依赖）。
struct FlowChips: View {
    let items: [String]
    var color: Color

    var body: some View {
        FlexibleWrap(items: items) { item in
            Text(item)
                .font(.caption)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(color.opacity(0.14), in: Capsule())
                .overlay(Capsule().stroke(color.opacity(0.30), lineWidth: 0.8))
        }
    }
}

/// 基于 Layout 协议的自动换行容器（iOS 16+）。
struct FlexibleWrap<Content: View>: View {
    let items: [String]
    @ViewBuilder var content: (String) -> Content

    var body: some View {
        WrapLayout(spacing: 8) {
            ForEach(items, id: \.self) { item in
                content(item)
            }
        }
    }
}

struct WrapLayout: Layout {
    /// 显式写出 Cache，否则 `inout ()` 不能稳定地当作协议要求来匹配。
    typealias Cache = Void

    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout Cache) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth, x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: maxWidth, height: y + rowHeight)
    }

    // 参数顺序必须与协议一致：in → proposal → subviews → cache
    func placeSubviews(
        in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout Cache
    ) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
