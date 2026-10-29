import SwiftUI

/// 回复风格调节（需求 09）：长度 / 提问 / 表情 / 动作 / 称呼。
///
/// 所有调节仍受绘梨衣核心性格约束（后端叠加在人格之后，不覆盖设定）。
struct StyleSettingsView: View {
    @EnvironmentObject private var session: AppSession
    @State private var style = StyleProfileDTO()
    @State private var isLoading = true
    @State private var saved = false

    private let lengthOptions = ["short", "medium", "long"]
    private let frequencyOptions = ["low", "medium", "high"]

    var body: some View {
        Form {
            Section {
                Picker("回复长度", selection: $style.replyLength) {
                    Text("简短").tag("short")
                    Text("适中").tag("medium")
                    Text("详细").tag("long")
                }
                .onChange(of: style.replyLength) { _,_ in save() }

                Picker("提问频率", selection: $style.questionFrequency) {
                    Text("少提问").tag("low")
                    Text("适当").tag("medium")
                    Text("多关心").tag("high")
                }
                .onChange(of: style.questionFrequency) { _,_ in save() }

                Picker("表情频率", selection: $style.emojiFrequency) {
                    Text("几乎不用").tag("low")
                    Text("偶尔").tag("medium")
                    Text("多用").tag("high")
                }
                .onChange(of: style.emojiFrequency) { _,_ in save() }

                Toggle("动作描写", isOn: $style.actionDescription)
                    .onChange(of: style.actionDescription) { _,_ in save() }
            } header: {
                Text("表达方式")
            } footer: {
                Text("动作描写是类似「*她低头看本子*」的小动作。")
            }

            Section {
                TextField("称呼（留空用默认）", text: $style.address)
                    .onSubmit { save() }
            } header: {
                Text("称呼")
            } footer: {
                Text("例如「阿泽」「主人」。留空则按她习惯的称呼。")
            }

            if saved {
                Section {
                    Label("已保存", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(LUMIStyle.pageBackground)
        .navigationTitle("回复风格")
        .navigationBarTitleDisplayMode(.inline)
        .overlay {
            if isLoading { ProgressView() }
        }
        .task { await load() }
    }

    private func load() async {
        do {
            style = try await session.api.getStyle()
        } catch {
            // 读不到就用默认值，不打断页面
        }
        isLoading = false
    }

    private func save() {
        guard !isLoading else { return }
        Task {
            do {
                style = try await session.api.setStyle(style)
                withAnimation { saved = true }
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                    withAnimation { saved = false }
                }
            } catch {
                // 保存失败静默，下次进入重试
            }
        }
    }
}
