import SwiftUI

/// 模型接入状态。用户必须能一眼看出"现在到底是不是真模型在说话"。
struct ModelStatusView: View {
    @State private var health: HealthResponse?
    @State private var failed = false
    @State private var loading = true

    private var isMock: Bool { health?.isMock ?? false }

    var body: some View {
        Form {
            Section {
                if loading {
                    HStack { ProgressView(); Text("正在查询后端…").font(.footnote) }
                } else if let health {
                    HStack {
                        Text("当前状态")
                        Spacer()
                        Text(isMock ? "模型尚未配置" : "已接入真实模型")
                            .foregroundStyle(isMock ? .orange : .green)
                    }
                    row("提供方", health.provider)
                    row("模型", health.providerModel)
                    row("后端版本", health.version)
                    if let schema = health.schemaVersion {
                        row("数据库版本", schema)
                    }
                } else {
                    Text("无法连接后端。请先在电脑上启动服务，再回到这里重新检查。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            } header: {
                Text("AI 模型")
            } footer: {
                Text(isMock
                     ? "当前后端还没有配置模型 API Key。请在服务器端填入 API Key 并重启服务，即可让绘梨衣用真实模型回应。"
                     : "模型密钥只保存在服务器端，手机端不接触任何密钥。")
                .font(.caption2)
            }

            Section {
                Button("重新检查") { Task { await load() } }
            }
        }
        .scrollContentBackground(.hidden)
        .background(LUMIStyle.pageBackground)
        .navigationTitle("模型")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func row(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title)
            Spacer()
            Text(value).foregroundStyle(.secondary)
        }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            let client = LUMIAPIClient(configuration: { ConfigurationStore.load() })
            health = try await client.health()
            failed = false
        } catch {
            health = nil
            failed = true
        }
    }
}
