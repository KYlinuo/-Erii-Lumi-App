import SwiftUI

/// 设置页：服务器地址、访问令牌（Keychain）、连接状态检测、本地数据管理。
struct SettingsView: View {
    @EnvironmentObject private var chatViewModel: ChatViewModel
    @StateObject private var viewModel: SettingsViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var showToken = false
    @State private var confirmClear = false
    @State private var notice: String?

    init() {
        _viewModel = StateObject(wrappedValue: SettingsViewModel(
            api: LUMIAPIClient(configuration: { ConfigurationStore.load() })
        ))
    }

    var body: some View {
        NavigationStack {
            Form {
                appearanceEntry
                modelEntry
                connectionSection
                serverSection
                securitySection
                dataSection
                aboutSection
            }
            .scrollContentBackground(.hidden)
            .background(Color(red: 0.08, green: 0.08, blue: 0.14))
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("完成") { dismiss() }
                        .foregroundStyle(Color(red: 0.75, green: 0.70, blue: 1.0))
                }
            }
            .task { await viewModel.checkConnection() }
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - 外观 / 模型入口

    private var appearanceEntry: some View {
        Section {
            NavigationLink {
                AppearanceSettingsView()
            } label: {
                Label("外观与气泡", systemImage: "paintbrush.pointed")
            }
        } footer: {
            Text("气泡主题、聊天背景、双方头像都在这里设置，只影响本机显示。")
                .font(.caption2)
        }
    }

    private var modelEntry: some View {
        Section {
            NavigationLink {
                ModelStatusView()
            } label: {
                Label("AI 模型", systemImage: "sparkles")
            }
        }
    }

    // MARK: - 连接状态

    private var connectionSection: some View {
        Section {
            HStack(spacing: 12) {
                Image(systemName: viewModel.connection.symbol)
                    .foregroundStyle(viewModel.connection.tint)
                    .font(.title3)
                VStack(alignment: .leading, spacing: 3) {
                    Text("服务器连接状态")
                        .font(.subheadline.weight(.medium))
                    Text(viewModel.connection.label)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    Task { await viewModel.checkConnection() }
                } label: {
                    if case .checking = viewModel.connection {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("重新检测")
                    }
                }
                .font(.caption)
                .disabled(isChecking)
                .accessibilityIdentifier("checkConnectionButton")
            }
            .padding(.vertical, 2)

            if case .connected(let health) = viewModel.connection {
                LabeledContent("服务版本", value: health.version)
                LabeledContent("运行环境", value: health.env)
                LabeledContent("数据库", value: health.database)
                LabeledContent("模型提供方", value: health.provider)
                LabeledContent("模型", value: health.providerModel)
                LabeledContent("模型已配置", value: health.providerConfigured ? "是" : "否")
                LabeledContent("访问认证", value: health.authRequired ? "开启" : "关闭（dev）")
                LabeledContent("密钥指纹", value: health.apiKeyHint.isEmpty ? "未配置" : health.apiKeyHint)
                    .accessibilityIdentifier("apiKeyHintRow")
            } else if case .failed(let reason) = viewModel.connection {
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        } header: {
            Text("连接")
        }
    }

    private var isChecking: Bool {
        if case .checking = viewModel.connection { return true }
        return false
    }

    // MARK: - 服务器

    private var serverSection: some View {
        Section {
            VStack(alignment: .leading, spacing: 6) {
                Text("服务器地址")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextField("http://127.0.0.1:8000", text: $viewModel.baseURLString)
                    .keyboardType(.URL)
                    .autocapitalization(.none)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .font(.system(.body, design: .monospaced))
                    .accessibilityIdentifier("baseURLField")
            }

            Stepper(value: $viewModel.timeout, in: 10...120, step: 5) {
                Text("请求超时：\(Int(viewModel.timeout)) 秒")
            }
        } header: {
            Text("服务器")
        } footer: {
            Text("手机访问本机后端请填电脑的局域网 IP，例如 http://192.168.1.20:8000")
        }
    }

    // MARK: - 认证

    private var securitySection: some View {
        Section {
            HStack {
                if showToken {
                    TextField("访问令牌", text: $viewModel.accessToken)
                        .autocapitalization(.none)
                        .autocorrectionDisabled()
                        .font(.system(.footnote, design: .monospaced))
                } else {
                    SecureField("访问令牌（LUMI_ACCESS_TOKEN）", text: $viewModel.accessToken)
                        .autocapitalization(.none)
                        .autocorrectionDisabled()
                }
                Button {
                    showToken.toggle()
                } label: {
                    Image(systemName: showToken ? "eye.slash" : "eye")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
            }
            .accessibilityIdentifier("tokenField")

            HStack {
                Image(systemName: viewModel.isTokenStoredInKeychain ? "lock.fill" : "lock.open")
                    .foregroundStyle(viewModel.isTokenStoredInKeychain ? .green : .orange)
                Text(viewModel.isTokenStoredInKeychain ? "已保存到系统钥匙串" : "尚未保存")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("清除") {
                    viewModel.clearToken()
                }
                .font(.caption)
                .foregroundStyle(.red)
            }
        } header: {
            Text("访问认证")
        } footer: {
            Text("令牌只写入 iOS 钥匙串（Keychain），不参与 iCloud 备份。模型 API Key 只保存在服务器，客户端永远不接触。")
        }
    }

    // MARK: - 数据

    private var dataSection: some View {
        Section {
            Button {
                Task {
                    do {
                        try await chatViewModel.syncFromServer()
                        notice = "已从服务器同步历史"
                    } catch let e as LUMIError {
                        notice = e.userMessage
                    } catch {
                        notice = error.localizedDescription
                    }
                }
            } label: {
                Label("从服务器同步历史", systemImage: "arrow.triangle.2.circlepath")
            }
            .disabled(chatViewModel.conversationID == nil)

            Button(role: .destructive) {
                confirmClear = true
            } label: {
                Label("清除本地聊天记录", systemImage: "trash")
            }
            .accessibilityIdentifier("clearHistoryButton")

            if let notice {
                Text(notice)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        } header: {
            Text("数据")
        } footer: {
            Text("清除本地记录不会影响服务器上的历史；服务器会话 ID 会被一并遗忘。")
        }
        .alert("确认清除？", isPresented: $confirmClear) {
            Button("取消", role: .cancel) { }
            Button("清除", role: .destructive) {
                Task { await chatViewModel.clearHistory() }
                notice = "本地记录已清除"
            }
        } message: {
            Text("本地保存的所有消息将被删除，此操作不可撤销。")
        }
    }

    // MARK: - 关于

    private var aboutSection: some View {
        Section {
            LabeledContent("客户端版本", value: appVersion)
            LabeledContent("会话 ID", value: chatViewModel.conversationID ?? "（尚未开始）")
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "checkmark.shield.fill")
                    .foregroundStyle(.green)
                Text("本客户端不含任何模型密钥，也不会在离线时伪造回复。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        } header: {
            Text("关于")
        }
    }

    private var appVersion: String {
        let v = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.1.0"
        let b = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "1"
        return "\(v) (\(b))"
    }
}

#Preview("Settings") {
    SettingsView()
        .environmentObject(
            ChatViewModel(
                api: LUMIAPIClient(configuration: {
                    ServerConfiguration(baseURL: URL(string: "http://127.0.0.1:8000")!)
                })
            )
        )
}
