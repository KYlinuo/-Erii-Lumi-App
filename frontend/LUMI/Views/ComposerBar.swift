import PhotosUI
import SwiftUI

struct ComposerBar: View {
    @Binding var text: String
    var isSending: Bool
    var onSend: () -> Void
    /// 选中图片后回调原始字节（由 ViewModel 负责落盘 + 上传）
    var onImage: (Data) -> Void = { _ in }
    /// 录音结束后回调临时文件与时长
    var onVoice: (URL, TimeInterval) -> Void = { _, _ in }

    @FocusState private var focused: Bool
    @StateObject private var recorder = AudioRecorder()
    @State private var pickedItem: PhotosPickerItem?
    @State private var voiceError: String?

    private var canSend: Bool {
        !isSending && !trimmedText.isEmpty
    }

    private var trimmedText: String {
        text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        VStack(spacing: 6) {
            if let voiceError {
                Text(voiceError)
                    .font(.caption2)
                    .foregroundStyle(.orange)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 16)
            }

            HStack(alignment: .bottom, spacing: 8) {
                if !recorder.isRecording {
                    PhotosPicker(selection: $pickedItem, matching: .images) {
                        Image(systemName: "photo.on.rectangle")
                            .font(.system(size: 22))
                            .foregroundStyle(.white.opacity(0.65))
                            .padding(.bottom, 8)
                    }
                    .disabled(isSending)
                    .accessibilityIdentifier("photoPickerButton")
                }

                if recorder.isRecording {
                    recordingStrip
                } else {
                    TextField("给 LUMI 发消息…", text: $text, axis: .vertical)
                        .textFieldStyle(.plain)
                        .focused($focused)
                        .font(.system(size: 16))
                        .foregroundStyle(.white)
                        .lineLimit(1...5)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 20, style: .continuous)
                                .fill(Color.white.opacity(0.09))
                        )
                        .disabled(isSending)
                        .accessibilityIdentifier("composerTextField")
                }

                if canSend {
                    Button(action: onSend) {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 30))
                            .foregroundStyle(Color(red: 0.72, green: 0.60, blue: 1.0))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("sendButton")
                } else {
                    Button {
                        Task { await toggleRecording() }
                    } label: {
                        Image(systemName: recorder.isRecording ? "stop.circle.fill" : "mic.circle.fill")
                            .font(.system(size: 30))
                            .foregroundStyle(recorder.isRecording ? .red : .white.opacity(0.55))
                    }
                    .buttonStyle(.plain)
                    .disabled(isSending)
                    .accessibilityIdentifier("micButton")
                }
            }
            .padding(.horizontal, 12)
            .padding(.top, 8)
            .padding(.bottom, 6)
        }
        .background(
            Color(red: 0.07, green: 0.07, blue: 0.12)
                .overlay(
                    Rectangle().fill(Color.white.opacity(0.06)).frame(height: 0.5),
                    alignment: .top
                )
        )
        .onChange(of: pickedItem) { _, newValue in
            guard let newValue else { return }
            Task {
                if let data = try? await newValue.loadTransferable(type: Data.self) {
                    await MainActor.run { onImage(data) }
                }
                await MainActor.run { pickedItem = nil }
            }
        }
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
            RoundedRectangle(cornerRadius: 20, style: .continuous)
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
        ComposerBar(text: .constant(""), isSending: true, onSend: { })
    }
    .background(Color(red: 0.07, green: 0.07, blue: 0.12))
}
