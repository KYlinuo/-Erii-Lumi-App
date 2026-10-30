import SwiftUI

/// 虚构日记：角色自己的虚构生活时间线。
///
/// 顶部常驻提示：这些内容全部来自后端的虚构世界模拟（`simulated=true`），
/// **不是**用户的真实经历，也**不是** AI 的真实记忆。
struct DiaryView: View {
    @StateObject private var viewModel: DiaryViewModel

    init(viewModel: DiaryViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        ZStack {
            LUMIStyle.background
            LUMIStyle.glow

            ScrollView {
                VStack(spacing: 16) {
                    noticeCard

                    if viewModel.isLoading && viewModel.events.isEmpty {
                        ProgressView("正在读取虚构日记…").padding(.top, 40)
                    } else if viewModel.events.isEmpty {
                        LUMIEmptyState(
                            symbol: "book",
                            title: "还没有虚构日记",
                            subtitle: "后端会为每个角色按天生成虚构生活事件。"
                        )
                    } else {
                        ForEach(viewModel.grouped, id: \.key) { group in
                            VStack(alignment: .leading, spacing: 10) {
                                Text(group.key)
                                    .font(.headline)
                                    .padding(.leading, 4)

                                ForEach(group.items) { event in
                                    eventRow(event)
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 18)
            }
        }
        .navigationTitle(viewModel.characterName.isEmpty ? "虚构日记" : "\(viewModel.characterName) · 虚构日记")
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.load() }
        .refreshable { await viewModel.load() }
    }

    private var noticeCard: some View {
        LUMICard {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                VStack(alignment: .leading, spacing: 4) {
                    Text("虚构内容提示")
                        .font(.subheadline.weight(.semibold))
                    Text(viewModel.notice)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func eventRow(_ event: WorldEventItem) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                LUMIBadge(text: event.kindLabel, color: LUMIStyle.violet)
                if !event.mood.isEmpty {
                    LUMIBadge(text: event.mood, color: LUMIStyle.mint)
                }
                Spacer(minLength: 0)
                Text(timeText(event.occurredAt))
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            if !event.title.isEmpty {
                Text(event.title)
                    .font(.subheadline.weight(.semibold))
            }
            Text(event.content)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
        )
    }

    private func timeText(_ iso: String?) -> String {
        guard let iso, let date = LUMIDate.parse(iso) else {
            return ""
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: date)
    }
}
