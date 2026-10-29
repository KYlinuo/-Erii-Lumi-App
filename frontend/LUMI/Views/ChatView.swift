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
    @State private var showSearch = false
    @State private var scrollTarget: UUID?

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
                    Button { showSearch = true } label: {
                        Image(systemName: "magnifyingglass")
                            .foregroundStyle(.white.opacity(0.85))
                    }
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
        .sheet(isPresented: $showSearch) {
            MessageSearchView(
                conversationID: viewModel.conversationID,
                onSelect: { serverID, content in
                    scrollToMessage(serverID: serverID, content: content)
                }
            )
            .environmentObject(viewModel)
        }
        .fullScreenCover(item: $previewImage) { item in
            ImagePreviewView(image: item.image)
        }
        .onChange(of: viewModel.lastError) { _, _ in dismissError = false }
        // 聊天页保持深色（壁纸 + 气泡是深色风格），其他页面跟随系统。
        .preferredColorScheme(.dark)
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
            .scrollDismissesKeyboard(.immediately)
            .onChange(of: viewModel.messages.count) { _, _ in scrollToBottom(proxy) }
            .onChange(of: viewModel.isSending) { _, sending in
                if sending { scrollToBottom(proxy) }
            }
            .onChange(of: scrollTarget) { _, target in
                if let target {
                    withAnimation(.easeOut(duration: 0.25)) {
                        proxy.scrollTo(target, anchor: .center)
                    }
                    scrollTarget = nil
                }
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

    /// 搜索选中后：按服务端 ID 或内容匹配本地消息，滚动到对应位置。
    private func scrollToMessage(serverID: String, content: String) {
        let match = viewModel.messages.first { $0.serverID == serverID }
            ?? viewModel.messages.first { $0.content == content }
        if let match {
            scrollTarget = match.id
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

/// 语音/视频通话的入口页：检查 LiveKit 配置状态，
/// 配置了就提供「发起通话」跳转到真正的 CallView，未配置则说明缺什么。
struct CallCapabilityView: View {
    enum Kind { case voice, video }
    let kind: Kind
    @EnvironmentObject private var session: AppSession
    @Environment(\.dismiss) private var dismiss
    @State private var status: CallStatusDTO?
    @State private var loadError: String?
    @State private var showCall = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Label(kind == .voice ? "实时语音通话" : "实时视频通话", systemImage: kind == .voice ? "phone.waveform" : "video")
                        .font(.headline)
                }

                Section("当前状态") {
                    if let status {
                        row("LiveKit 服务", status.configured ? "已配置" : "未配置")
                        row("语音识别 STT", status.sttConfigured ? "已接入" : "未接入")
                        row("语音合成 TTS", status.ttsConfigured ? "已接入" : "未接入")
                    } else if let loadError {
                        Text(loadError).font(.footnote).foregroundStyle(.secondary)
                    } else {
                        HStack { ProgressView(); Text("正在检查服务器…").font(.footnote) }
                    }
                }

                if let status, status.configured {
                    Section {
                        Button {
                            showCall = true
                        } label: {
                            Label("发起通话", systemImage: kind == .voice ? "phone.fill" : "video.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .font(.headline)
                    } footer: {
                        Text("通话中你的语音会实时转写 → 绘梨衣用 DeepSeek 思考 → 再合成语音回你。")
                    }
                } else {
                    Section("为什么还不能通话") {
                        Text("实时通话需要一个 LiveKit Server（负责音视频流）+ STT/TTS 服务。这些尚未配置，所以不假装接通。")
                            .font(.footnote)
                    }
                    Section {
                        Text("配置方法：在后端 .env 中设置 LUMI_LIVEKIT_URL / LUMI_LIVEKIT_API_KEY / LUMI_LIVEKIT_API_SECRET，以及 STT/TTS 模型后重启服务。")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
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
            .fullScreenCover(isPresented: $showCall) {
                CallView(kind: kind == .voice ? .voice : .video)
                    .environmentObject(session)
            }
        }
    }

    private func row(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title)
            Spacer()
            Text(value)
                .foregroundStyle(value == "已配置" || value == "已接入" ? .green : .secondary)
        }
    }

    private func load() async {
        do {
            status = try await session.api.callStatus()
        } catch {
            loadError = "无法连接后端，请先在电脑上启动服务。"
        }
    }
}
