import SwiftUI
import UIKit

/// 聊天页：微信式布局 + 三套气泡主题 + 自定义背景。
struct ChatView: View {
    @EnvironmentObject private var viewModel: ChatViewModel
    @ObservedObject private var appearance = AppearanceStore.shared

    @State private var draft = ""
    @State private var showSettings = false
    @State private var dismissError = false
    @State private var quoted: ChatMessage?
    @State private var previewImage: PreviewItem?
    @State private var showCallInfo = false
    @State private var callKind: CallKind = .voice

    enum CallKind { case voice, video }

    var body: some View {
        VStack(spacing: 0) {
            messageList
            if let error = viewModel.lastError, !dismissError {
                errorBanner(error)
            }
            ComposerBar(
                text: $draft,
                isSending: viewModel.isSending,
                quotedText: quoted.map { ChatViewModel.quoteSnippet($0) },
                onCancelQuote: { quoted = nil },
                onSend: { sendDraft() },
                onImage: { data in
                    draft = ""
                    viewModel.sendImage(data: data)
                },
                onVoice: { url, duration in
                    viewModel.sendVoice(fileURL: url, duration: duration)
                }
            )
        }
        .background(ChatBackgroundView(appearance: appearance))
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) { header }
            ToolbarItem(placement: .navigationBarTrailing) {
                HStack(spacing: 14) {
                    Button { callKind = .voice; showCallInfo = true } label: {
                        Image(systemName: "phone")
                            .foregroundStyle(.white.opacity(0.85))
                    }
                    Button { callKind = .video; showCallInfo = true } label: {
                        Image(systemName: "video")
                            .foregroundStyle(.white.opacity(0.85))
                    }
                    Button { showSettings = true } label: {
                        Image(systemName: "gearshape")
                            .foregroundStyle(.white.opacity(0.85))
                    }
                }
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView().environmentObject(viewModel)
        }
        .sheet(isPresented: $showCallInfo) {
            CallCapabilityView(kind: callKind == .voice ? .voice : .video)
                .presentationDetents([.medium])
        }
        .fullScreenCover(item: $previewImage) { item in
            ImagePreviewView(image: item.image)
        }
        .onChange(of: viewModel.lastError) { _, _ in dismissError = false }
    }

    // MARK: - 顶部

    private var header: some View {
        HStack(spacing: 8) {
            if let custom = appearance.characterAvatar {
                Image(uiImage: custom)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 26, height: 26)
                    .clipShape(Circle())
            } else {
                LUMIAvatar(size: 26)
            }
            VStack(alignment: .leading, spacing: 0) {
                Text("绘梨衣")
                    .font(LUMIStyle.Font.title)
                    .foregroundStyle(.white)
                Text(viewModel.isSending ? "正在输入…" : "在线")
                    .font(.system(size: 10))
                    .foregroundStyle(.white.opacity(0.5))
            }
        }
        .accessibilityIdentifier("chatHeader")
    }

    // MARK: - 消息列表

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(Array(viewModel.messages.enumerated()), id: \.element.id) { index, message in
                        let meta = grouping(at: index)
                        MessageBubble(
                            message: message,
                            theme: appearance.theme,
                            appearance: appearance,
                            showTime: meta.showTime,
                            showAvatar: meta.showAvatar,
                            onRetry: { viewModel.retry(messageID: message.id) },
                            onReply: { quoted = $0 },
                            onDelete: { viewModel.delete(messageID: $0.id) },
                            onPreviewImage: { previewImage = PreviewItem(image: $0) }
                        )
                        .id(message.id)
                        .padding(.bottom, meta.spacingBelow)
                    }
                    if viewModel.isSending {
                        TypingIndicator().id("typing")
                    }
                }
                .padding(.top, 8)
                .padding(.bottom, 6)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: viewModel.messages.count) { _, _ in scrollToBottom(proxy) }
            .onChange(of: viewModel.isSending) { _, sending in
                if sending { scrollToBottom(proxy) }
            }
            .onAppear { scrollToBottom(proxy) }
            .overlay(alignment: .center) {
                if viewModel.isRestoring && viewModel.messages.isEmpty {
                    ProgressView("恢复中…")
                        .tint(.white)
                        .foregroundStyle(.white.opacity(0.7))
                }
            }
        }
    }

    /// 连续消息合并：同一个人、间隔小于 3 分钟算一组
    private func grouping(at index: Int) -> (showTime: Bool, showAvatar: Bool, spacingBelow: CGFloat) {
        let messages = viewModel.messages
        guard messages.indices.contains(index) else { return (false, true, 4) }
        let current = messages[index]
        let previous = index > 0 ? messages[index - 1] : nil
        let next = index + 1 < messages.count ? messages[index + 1] : nil

        let sameAsPrevious = previous.map {
            $0.role == current.role && current.createdAt.timeIntervalSince($0.createdAt) < 180
        } ?? false
        let sameAsNext = next.map {
            $0.role == current.role && $0.createdAt.timeIntervalSince(current.createdAt) < 180
        } ?? false

        let showTime = !sameAsPrevious
        // 一组的最后一条才显示头像
        let showAvatar = !sameAsNext
        let spacing: CGFloat = sameAsNext ? 3 : 10
        return (showTime, showAvatar, spacing)
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.08) {
            withAnimation(.easeOut(duration: 0.2)) {
                if viewModel.isSending {
                    proxy.scrollTo("typing", anchor: .bottom)
                } else if let last = viewModel.messages.last {
                    proxy.scrollTo(last.id, anchor: .bottom)
                }
            }
        }
    }

    private func sendDraft() {
        let text = draft
        draft = ""
        let quote = quoted
        quoted = nil
        viewModel.send(text: text, quoted: quote)
    }

    // MARK: - 错误提示条

    private func errorBanner(_ error: LUMIError) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.yellow)
            VStack(alignment: .leading, spacing: 2) {
                Text(error.userMessage)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.92))
                if let hint = error.hint {
                    Text(hint)
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.55))
                }
            }
            Spacer()
            if error.isRetryable, let failed = viewModel.messages.last(where: { $0.status == .failed }) {
                Button("重试") { viewModel.retry(messageID: failed.id) }
                    .font(.caption.weight(.semibold))
            }
            Button {
                dismissError = true
            } label: {
                Image(systemName: "xmark")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.6))
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
        .background(.ultraThinMaterial)
        .overlay(alignment: .top) {
            Rectangle().fill(Color.white.opacity(0.08)).frame(height: 0.5)
        }
    }
}

// MARK: - 图片预览

struct ImagePreviewView: View {
    let image: UIImage
    @Environment(\.dismiss) private var dismiss
    @State private var zoom: CGFloat = 1

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            Image(uiImage: image)
                .resizable()
                .scaledToFit()
                .scaleEffect(zoom)
                .gesture(
                    MagnificationGesture()
                        .onChanged { zoom = max(1, min($0, 4)) }
                        .onEnded { _ in withAnimation(.easeOut(duration: 0.2)) { zoom = max(1, zoom) } }
                )
                .onTapGesture(count: 2) {
                    withAnimation { zoom = zoom > 1 ? 1 : 2 }
                }
        }
        .overlay(alignment: .topTrailing) {
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 28))
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(.white)
                    .padding(16)
            }
        }
        .statusBarHidden()
    }
}

/// 全屏预览的载体（避免给 UIImage 扩展 Identifiable）
struct PreviewItem: Identifiable {
    let id = UUID()
    let image: UIImage
}

// MARK: - 通话能力说明

/// 语音/视频通话的真实状态说明页。
///
/// 之所以不做成"假装接通"的界面：实时通话需要后端接入 ASR/TTS（或 WebRTC 服务），
/// 当前后端没有配置，硬做一个动画界面等于欺骗用户。
struct CallCapabilityView: View {
    enum Kind { case voice, video }
    let kind: Kind
    @Environment(\.dismiss) private var dismiss
    @State private var status: SpeechStatusDTO?
    @State private var loadError: String?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Label(kind == .voice ? "实时语音通话" : "实时视频通话", systemImage: kind == .voice ? "phone.waveform" : "video")
                        .font(.headline)
                }

                Section("当前状态") {
                    if let status {
                        row("语音识别 ASR", status.asrConfigured ? "已接入" : "未接入")
                        row("语音合成 TTS", status.ttsConfigured ? "已接入" : "未接入")
                    } else if let loadError {
                        Text(loadError).font(.footnote).foregroundStyle(.secondary)
                    } else {
                        HStack { ProgressView(); Text("正在检查服务器…").font(.footnote) }
                    }
                }

                Section("为什么还不能通话") {
                    Text("实时通话需要三个条件：后端接入 ASR 把你说的话转成文本、模型生成回复、TTS 把回复念出来。当前后端在这两项上都未配置，所以不做假的通话界面。")
                        .font(.footnote)
                }

                Section {
                    Text("配置方法：在后端 .env 中设置 LUMI_ASR_MODEL 与 LUMI_TTS_MODEL 后重启服务。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("通话")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("关闭") { dismiss() }
                }
            }
            .task { await load() }
        }
    }

    private func row(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title)
            Spacer()
            Text(value)
                .foregroundStyle(value == "已接入" ? .green : .secondary)
        }
    }

    private func load() async {
        do {
            let client = LUMIAPIClient(configuration: { ConfigurationStore.load() })
            status = try await client.speechStatus()
        } catch {
            loadError = "无法连接后端，请先在电脑上启动服务。"
        }
    }
}
