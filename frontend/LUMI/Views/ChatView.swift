import SwiftUI

struct ChatView: View {
    @EnvironmentObject private var viewModel: ChatViewModel
    @State private var draft = ""
    @State private var showSettings = false
    @State private var dismissError = false

    var body: some View {
        VStack(spacing: 0) {
            messageList
            if let error = viewModel.lastError, !dismissError {
                errorBanner(error)
            }
            ComposerBar(text: $draft, isSending: viewModel.isSending) {
                sendDraft()
            }
        }
        .background(
            LinearGradient(
                colors: [Color(red: 0.08, green: 0.08, blue: 0.15),
                         Color(red: 0.11, green: 0.10, blue: 0.20)],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
        )
        .navigationTitle("LUMI")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                HStack(spacing: 8) {
                    LUMIAvatar(size: 26)
                    Text("LUMI")
                        .font(.system(size: 16, weight: .semibold, design: .rounded))
                        .foregroundStyle(.white)
                }
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    showSettings = true
                } label: {
                    Image(systemName: "gearshape.fill")
                        .foregroundStyle(.white.opacity(0.85))
                }
                .accessibilityIdentifier("settingsButton")
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView()
                .environmentObject(viewModel)
        }
        .onChange(of: viewModel.lastError) { _, _ in dismissError = false }
    }

    // MARK: - 消息列表

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(viewModel.messages) { message in
                        MessageBubble(message: message) {
                            viewModel.retry(messageID: message.id)
                        }
                        .id(message.id)
                    }
                    if viewModel.isSending {
                        TypingIndicator()
                            .id("typing")
                    }
                }
                .padding(.top, 10)
                .padding(.bottom, 6)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: viewModel.messages.count) { _, _ in
                scrollToBottom(proxy)
            }
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
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
        .background(Color.yellow.opacity(0.14))
        .overlay(
            Rectangle().fill(Color.yellow.opacity(0.3)).frame(height: 0.5),
            alignment: .top
        )
        .accessibilityIdentifier("errorBanner")
    }

    private func sendDraft() {
        let text = draft
        draft = ""
        viewModel.send(text: text)
    }
}

#Preview("Chat") {
    NavigationStack {
        ChatView()
            .environmentObject(
                ChatViewModel(
                    api: LUMIAPIClient(configuration: {
                        ServerConfiguration(baseURL: URL(string: "http://127.0.0.1:8000")!)
                    })
                )
            )
    }
    .preferredColorScheme(.dark)
}
