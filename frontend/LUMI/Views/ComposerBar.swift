import PhotosUI
import SwiftUI

/// 输入栏：文字 / 表情 / 图片 / 录音 / 发送，以及与键盘联动的引用条。
struct ComposerBar: View {
    @Binding var text: String
    var isSending: Bool
    /// 当前引用中的消息摘要（有值时显示引用条）
    var quotedText: String?
    var onCancelQuote: (() -> Void)?
    var onSend: () -> Void
    /// 选中图片后回调原始字节（由 ViewModel 负责落盘 + 上传）
    var onImage: (Data) -> Void = { _ in }
    /// 录音结束后回调临时文件与时长
    var onVoice: (URL, TimeInterval) -> Void = { _, _ in }
    /// 强调色（跟随当前主题）
    var accent: Color = Color(red: 0.72, green: 0.60, blue: 1.0)

    @FocusState private var focused: Bool
    @StateObject private var recorder = AudioRecorder()
    @State private var pickedItem: PhotosPickerItem?
    @State private var voiceError: String?
    @State private var showEmoji = false

    @ObservedObject private var emojiStore = QuickEmojiStore.shared

    private var quickEmojis: [String] { emojiStore.emojis }

    private var canSend: Bool {
        !isSending && !trimmedText.isEmpty
    }

    private var trimmedText: String {
        text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        VStack(spacing: 0) {
            if let quotedText, !quotedText.isEmpty {
                quoteBar(quotedText)
            }

            if let voiceError {
                Text(voiceError)
                    .font(.caption2)
                    .foregroundStyle(.orange)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 16)
                    .padding(.top, 4)
            }

            if showEmoji {
                emojiRow
            }

            HStack(alignment: .bottom, spacing: 8) {
                if !recorder.isRecording {
                    button("face.smiling", active: showEmoji) {
                        showEmoji.toggle()
                        if showEmoji { focused = false }
                    }
                    PhotosPicker(selection: $pickedItem, matching: .images) {
                        Image(systemName: "photo.on.rectangle")
                            .font(.system(size: 21))
                            .foregroundStyle(.white.opacity(0.65))
                            .padding(.bottom, 8)
                    }
                    .disabled(isSending)
                    .accessibilityIdentifier("photoPickerButton")
                }

                if recorder.isRecording {
                    recordingStrip
                } else {
                    TextField("给绘梨衣发消息…", text: $text, axis: .vertical)
                        .textFieldStyle(.plain)
                        .focused($focused)
                        .font(LUMIStyle.Font.bubble)
                        .foregroundStyle(.white)
                        .lineLimit(1...5)
                        .padding(.horizontal, 13)
                        .padding(.vertical, 9)
                        .background(
                            RoundedRectangle(cornerRadius: 19, style: .continuous)
                                .fill(Color.white.opacity(0.10))
                        )
                        .disabled(isSending)
                        .accessibilityIdentifier("composerTextField")
                }

                if canSend {
                    Button {
                        focused = false  // 发送后收起键盘
                        onSend()
                    } label: {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 29))
                            .foregroundStyle(accent)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("sendButton")
                } else {
                    Button {
                        Task { await toggleRecording() }
                    } label: {
                        Image(systemName: recorder.isRecording ? "stop.circle.fill" : "mic.circle.fill")
                            .font(.system(size: 29))
                            .foregroundStyle(recorder.isRecording ? .red : accent.opacity(0.7))
                    }
                    .buttonStyle(.plain)
                    .disabled(isSending)
                    .accessibilityIdentifier("micButton")
                }
            }
            .padding(.horizontal, 10)
            .padding(.top, 7)
            .padding(.bottom, 5)
        }
        .background(.ultraThinMaterial)
        .overlay(alignment: .top) {
            Rectangle().fill(Color.white.opacity(0.07)).frame(height: 0.5)
        }
        .onChange(of: pickedItem) { _, newValue in
            guard let newValue else { return }
            Task { @MainActor in
                if let data = try? await newValue.loadTransferable(type: Data.self) {
                    onImage(data)
                }
                pickedItem = nil
            }
        }
    }

    private func button(_ symbol: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 21))
                .foregroundStyle(active ? LUMIStyle.violet : .white.opacity(0.65))
                .padding(.bottom, 8)
        }
        .buttonStyle(.plain)
    }

    private func quoteBar(_ text: String) -> some View {
        HStack(spacing: 8) {
            Rectangle()
                .fill(LUMIStyle.violet)
                .frame(width: 2, height: 24)
                .clipShape(Capsule())
            Text(text)
                .font(.system(size: 12))
                .foregroundStyle(.white.opacity(0.6))
                .lineLimit(1)
            Spacer()
            Button {
                onCancelQuote?()
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 11))
                    .foregroundStyle(.white.opacity(0.5))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
        .background(Color.white.opacity(0.05))
    }

    private var emojiRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 14) {
                ForEach(quickEmojis, id: \.self) { emoji in
                    Button {
                        text += emoji
                    } label: {
                        Text(emoji).font(.system(size: 22))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
        .background(Color.white.opacity(0.04))
    }

    private var recordingStrip: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(.red)
                .frame(width: 8, height: 8)
                .scaleEffect(1 + recorder.level * 0.6)
                .animation(.easeOut(duration: 0.15), value: recorder.level)

            Text(String(format: "%.1f″", recorder.elapsed))
                .font(.system(size: 15, weight: .medium, design: .monospaced))
                .foregroundStyle(.white)

            Text("点方块结束")
                .font(.caption2)
                .foregroundStyle(.white.opacity(0.4))

            Spacer()

            Button("取消") { recorder.cancel() }
                .font(.caption)
                .foregroundStyle(.white.opacity(0.6))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 19, style: .continuous)
                .fill(Color.white.opacity(0.09))
        )
    }

    private func toggleRecording() async {
        voiceError = nil
        if recorder.isRecording {
            if let result = recorder.stop() {
                onVoice(result.url, result.duration)
            }
            return
        }
        do {
            try await recorder.start()
        } catch {
            voiceError = (error as? LocalizedError)?.errorDescription ?? "录音失败。"
        }
    }
}

#Preview("Composer") {
    VStack {
        Spacer()
        ComposerBar(text: .constant("你好"), isSending: false, onSend: { })
        ComposerBar(
            text: .constant(""),
            isSending: false,
            quotedText: "她说过的那句话",
            onCancelQuote: { },
            onSend: { }
        )
    }
    .background(Color(red: 0.07, green: 0.07, blue: 0.12))
}
