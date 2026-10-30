import SwiftUI
import UIKit

/// 聊天页：微信式布局 + 三套气泡主题 + 自定义背景。
struct ChatView: View {
    @EnvironmentObject private var viewModel: ChatViewModel
    @ObservedObject private var appearance = AppearanceStore.shared

    @State private var showSettings = false
    @State private var dismissError = false
    @State private var quoted: ChatMessage?
    @State private var previewImage: PreviewItem?
    @State private var showCallInfo = false
    @State private var callKind: CallKind = .voice
    @State private var showSearch = false
    @State private var scrollTarget: UUID?
    @StateObject private var ttsPlayer = AudioPlayer()
    /// 是否在消息底部（用于「浏览历史不被新消息拉底」）
    @State private var isAtBottom = true
    /// 未读新消息数（用户上翻时累积，回到底部清零）
    @State private var unreadCount = 0
    @State private var scrollTask: Task<Void, Never>?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// 双击放大文字的内容
    @State private var zoomedText: String?

    enum CallKind { case voice, video }

    var body: some View {
        VStack(spacing: 0) {
            messageList
            if let error = viewModel.lastError, !dismissError {
                errorBanner(error)
            }
            ChatComposerView(
                viewModel: viewModel,
                quoted: $quoted,
                accent: appearance.theme.accent
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
            NavigationStack { SettingsView().environmentObject(viewModel) }
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
            ImagePreviewView(item: item)
        }
        .sheet(isPresented: Binding(
            get: { zoomedText != nil },
            set: { if !$0 { zoomedText = nil } }
        )) {
            if let text = zoomedText {
                ZoomedTextView(text: text)
            }
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
                    ForEach(ChatRows(messages: viewModel.messages)) { meta in
                        let message = meta.message
                        MessageBubble(
                            message: message,
                            theme: appearance.theme,
                            appearance: appearance,
                            showTime: meta.showTime,
                            showAvatar: meta.showAvatar,
                            onRetry: { viewModel.retry(messageID: message.id) },
                            onReply: { quoted = $0 },
                            onDelete: { viewModel.delete(messageID: $0.id) },
                            onPreviewImage: {
                                previewImage = PreviewItem(image: $0, mediaID: message.mediaID,
                                                           localPath: message.localMediaPath)
                            },
                            onSpeak: { speak($0) },
                            onStar: { toggleStar($0) },
                            onZoomText: { zoomedText = $0 },
                            onFeedback: { type in feedback(type, message: message) }
                        )
                        .id(message.id)
                        .padding(.bottom, CGFloat(meta.spacingBelow))
                    }
                    if viewModel.isSending {
                        TypingIndicator().id("typing")
                    }
                    // 底部标记：可见=在底部；滚出屏幕=在往上翻历史。
                    Color.clear
                        .frame(height: 1)
                        .id("bottom-marker")
                        .onAppear {
                            if #unavailable(iOS 18.0) { isAtBottom = true; unreadCount = 0 }
                        }
                        .onDisappear { if #unavailable(iOS 18.0) { isAtBottom = false } }
                }
                .padding(.top, 8)
                .padding(.bottom, 6)
            }
            .modifier(ChatBottomObserver(isAtBottom: $isAtBottom))
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: isAtBottom) { _, bottom in if bottom { unreadCount = 0 } }
            .onChange(of: viewModel.messages.count) { oldCount, newCount in
                guard newCount > oldCount else { return }
                if isAtBottom {
                    scrollToBottom(proxy)
                } else {
                    // 用户在翻历史：不拉底，只累计未读提示
                    unreadCount += newCount - oldCount
                }
            }
            .onChange(of: viewModel.isSending) { _, sending in
                if sending && isAtBottom { scrollToBottom(proxy) }
            }
            .onChange(of: scrollTarget) { _, target in
                if let target {
                    withAnimation(reduceMotion ? nil : .easeOut(duration: 0.25)) {
                        proxy.scrollTo(target, anchor: .center)
                    }
                    scrollTarget = nil
                }
            }
            .onAppear { scrollToBottom(proxy) }
            .onDisappear { scrollTask?.cancel() }
            .overlay(alignment: .center) {
                if viewModel.isRestoring && viewModel.messages.isEmpty {
                    ProgressView("恢复中…")
                        .tint(.white)
                        .foregroundStyle(.white.opacity(0.7))
                }
            }
            .overlay(alignment: .bottom) {
                if unreadCount > 0 {
                    newMessageBadge(proxy)
                }
            }
        }
    }

    /// 新消息提示：点击回到底部并清零未读。
    private func newMessageBadge(_ proxy: ScrollViewProxy) -> some View {
        Button {
            scrollToBottom(proxy)
            unreadCount = 0
            isAtBottom = true
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "arrow.down")
                Text(unreadCount > 99 ? "99+ 条新消息" : "\(unreadCount) 条新消息")
            }
            .font(.caption.weight(.medium))
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(.ultraThinMaterial, in: Capsule())
            .overlay(Capsule().strokeBorder(.white.opacity(0.15), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .padding(.bottom, 10)
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        scrollTask?.cancel()
        scrollTask = Task { @MainActor in
            await Task.yield()
            guard !Task.isCancelled else { return }
            withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) {
                proxy.scrollTo("bottom-marker", anchor: .bottom)
            }
        }
    }

    /// 搜索选中后：按服务端 ID 精确定位；结果不在本地窗口时不按正文猜测，
    /// 避免滚到另一条相同文本的位置。
    private func scrollToMessage(serverID: String, content: String) {
        if let byID = viewModel.messages.first(where: { $0.serverID == serverID }) {
            scrollTarget = byID.id
            return
        }
        // 本地已加载区间没有该 ID：只在恰好唯一匹配时才按正文定位，
        // 多条重复正文时不悄悄滚到错误的那一条。
        let contentMatches = viewModel.messages.filter { $0.content == content }
        if contentMatches.count == 1 {
            scrollTarget = contentMatches[0].id
        }
    }

    // MARK: - 朗读与收藏

    /// 把绘梨衣的文字回复合成为语音播出来（TTS）。
    private func speak(_ message: ChatMessage) {
        let text = message.content
        guard !text.isEmpty else { return }
        Task {
            do {
                let data = try await viewModel.synthesizeSpeech(text)
                await MainActor.run {
                    ttsPlayer.play(id: message.id, data: data)
                }
            } catch {
                // 朗读失败静默处理：不打断聊天主流程
            }
        }
    }

    /// 收藏 / 取消收藏一条消息，并同步到服务端。
    private func toggleStar(_ message: ChatMessage) {
        let newValue = !message.starred
        viewModel.setStarred(messageID: message.id, starred: newValue)
    }

    /// 反馈纠正（需求 11）：记错了 / 太长 / 不像绘梨衣。
    private func feedback(_ type: String, message: ChatMessage) {
        Task {
            await viewModel.sendFeedback(type: type, messageID: message.serverID)
        }
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
    let item: PreviewItem
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var zoom: CGFloat = 1
    @State private var detailedImage: UIImage?
    @State private var loading = false
    @State private var loadFailed = false
    @State private var retry = 0

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            Image(uiImage: detailedImage ?? item.image)
                .resizable()
                .scaledToFit()
                .scaleEffect(zoom)
                .gesture(
                    MagnificationGesture()
                        .onChanged { zoom = max(1, min($0, 4)) }
                        .onEnded { _ in
                            withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) {
                                zoom = max(1, zoom)
                            }
                        }
                )
                .onTapGesture(count: 2) {
                    withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) {
                        zoom = zoom > 1 ? 1 : 2
                    }
                }
        }
        .overlay(alignment: .bottom) {
            if loading || loadFailed {
                HStack {
                    if loading {
                        ProgressView("加载高清图…").tint(.white)
                    } else {
                        Button("高清图加载失败，点此重试") { retry += 1 }
                    }
                }
                .font(.caption)
                .foregroundStyle(.white)
                .padding()
                .background(.ultraThinMaterial, in: Capsule())
                .padding(.bottom, 20)
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
        .task(id: retry) {
            guard item.mediaID != nil || item.localPath != nil else { return }
            loading = true
            loadFailed = false
            do {
                // A bounded detail variant is decoded only after opening this screen.
                let decoded = try await MediaStore.shared.image(id: item.mediaID,
                                                               localPath: item.localPath,
                                                               maxPixelSize: 2_560)
                try Task.checkCancellation()
                detailedImage = UIImage(cgImage: decoded.cgImage)
            } catch is CancellationError { } catch {
                if !Task.isCancelled { loadFailed = true }
            }
            if !Task.isCancelled { loading = false }
        }
    }
}

/// 全屏预览的载体（避免给 UIImage 扩展 Identifiable）
struct PreviewItem: Identifiable {
    let id = UUID()
    let image: UIImage
    var mediaID: String?
    var localPath: String?
}

/// 双击消息后的「放大文字」视图（需求 04）：大字、可复制、可调整字号。
struct ZoomedTextView: View {
    let text: String
    @Environment(\.dismiss) private var dismiss
    @State private var fontSize: CGFloat = 22

    var body: some View {
        NavigationStack {
            ScrollView {
                Text(text)
                    .font(.system(size: fontSize, weight: .regular))
                    .textSelection(.enabled)
                    .lineSpacing(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(20)
            }
            .background(LUMIStyle.pageBackground)
            .navigationTitle("文字")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("关闭") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    HStack(spacing: 14) {
                        Button { fontSize = max(16, fontSize - 2) } label: {
                            Image(systemName: "textformat.size.smaller")
                        }
                        Button { fontSize = min(40, fontSize + 2) } label: {
                            Image(systemName: "textformat.size.larger")
                        }
                        Button {
                            UIPasteboard.general.string = text
                        } label: {
                            Image(systemName: "doc.on.doc")
                        }
                    }
                }
            }
        }
    }
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

/// Keep keystroke state out of ChatView, so typing does not rebuild the history tree.
private struct ChatComposerView: View {
    @ObservedObject var viewModel: ChatViewModel
    @Binding var quoted: ChatMessage?
    let accent: Color
    @State private var draft = ""

    var body: some View {
        ComposerBar(
            text: $draft, isSending: viewModel.isSending,
            quotedText: quoted.map { ChatViewModel.quoteSnippet($0) },
            onCancelQuote: { quoted = nil },
            onSend: {
                let text = draft
                draft = ""
                let quote = quoted
                quoted = nil
                viewModel.send(text: text, quoted: quote)
            },
            onImage: { viewModel.sendImage(data: $0) },
            onVoice: { viewModel.sendVoice(fileURL: $0, duration: $1) },
            accent: accent
        )
    }
}

private struct ChatBottomObserver: ViewModifier {
    @Binding var isAtBottom: Bool
    func body(content: Content) -> some View {
        if #available(iOS 18.0, *) {
            content.onScrollGeometryChange(for: Bool.self) { geometry in
                geometry.contentSize.height + geometry.contentInsets.bottom
                    - geometry.contentOffset.y - geometry.containerSize.height <= 80
            } action: { _, bottom in
                isAtBottom = bottom
            }
        } else { content }
    }
}
