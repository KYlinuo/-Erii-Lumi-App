import SwiftUI

/// 「小本子」：绘梨衣的随身小本，聚合 人物资料 / 记忆 / 日记 / 约定 / 共同回忆。
///
/// 这是 36 项需求 01「精简导航」的核心容器——把原来分散在 3 个 tab 的内容
/// 收进一个入口，用分段控件切换。约定（20）与共同回忆（21）在阶段 D 落地，
/// 当前提供占位空态，不伪装成已完成。
struct NotebookView: View {
    @EnvironmentObject private var session: AppSession

    enum Section: String, CaseIterable, Identifiable {
        case profile = "人物"
        case memory = "记忆"
        case diary = "日记"
        case promises = "约定"
        case memories = "回忆"

        var id: String { rawValue }

        var icon: String {
            switch self {
            case .profile: return "person.crop.circle.fill"
            case .memory: return "brain"
            case .diary: return "book.closed.fill"
            case .promises: return "checkmark.circle"
            case .memories: return "heart.text.square"
            }
        }
    }

    @State private var selection: Section = .profile

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                sectionPicker
                content
            }
            .background(LUMIStyle.pageBackground)
            .navigationTitle("小本子")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private var sectionPicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(Section.allCases) { section in
                    Button {
                        withAnimation(.easeOut(duration: 0.2)) { selection = section }
                    } label: {
                        Label(section.rawValue, systemImage: section.icon)
                            .font(.subheadline.weight(selection == section ? .semibold : .regular))
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                            .background(
                                Capsule().fill(selection == section ? LUMIStyle.violet.opacity(0.22) : Color.clear)
                            )
                            .foregroundStyle(selection == section ? LUMIStyle.violet : .secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
    }

    @ViewBuilder
    private var content: some View {
        switch selection {
        case .profile:
            ProfileView(viewModel: session.personaViewModel)
        case .memory:
            MemoryView(viewModel: session.memoryViewModel)
        case .diary:
            DiaryView(viewModel: session.diaryViewModel)
        case .promises:
            placeholder(title: "约定", icon: "checkmark.circle",
                        text: "她记下的小约定会在这里。等她记起来的时候，会突然跟你提起。")
        case .memories:
            placeholder(title: "共同回忆", icon: "heart.text.square",
                        text: "你们一起经历的片段，会慢慢沉淀成一条时间线。")
        }
    }

    private func placeholder(title: String, icon: String, text: String) -> some View {
        VStack(spacing: 14) {
            Image(systemName: icon)
                .font(.system(size: 44))
                .foregroundStyle(LUMIStyle.violet.opacity(0.6))
            Text(title)
                .font(.headline)
            Text(text)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
