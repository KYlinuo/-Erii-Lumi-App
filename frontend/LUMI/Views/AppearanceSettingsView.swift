import PhotosUI
import SwiftUI

/// 外观设置：气泡主题、聊天背景、双方头像。
struct AppearanceSettingsView: View {
    @ObservedObject private var appearance = AppearanceStore.shared
    @State private var backgroundItem: PhotosPickerItem?
    @State private var myAvatarItem: PhotosPickerItem?
    @State private var characterAvatarItem: PhotosPickerItem?

    var body: some View {
        Form {
            iconSection
            themeSection
            backgroundSection
            avatarSection
        }
        .scrollContentBackground(.hidden)
        .background(Color(red: 0.08, green: 0.08, blue: 0.14))
        .navigationTitle("外观")
        .navigationBarTitleDisplayMode(.inline)
    }

    // MARK: - App 图标

    private var iconSection: some View {
        Section {
            ForEach(AppIconChoice.allCases) { choice in
                Button {
                    appearance.iconChoice = choice
                } label: {
                    HStack(spacing: 12) {
                        Image(choice.previewImageName)
                            .resizable()
                            .scaledToFit()
                            .frame(width: 44, height: 44)
                            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(choice.title)
                                .foregroundStyle(.primary)
                            Text(choice.subtitle)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        if appearance.iconChoice == choice {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(Color(red: 0.72, green: 0.60, blue: 1.0))
                        }
                    }
                }
                .buttonStyle(.plain)
            }
        } header: {
            Text("App 图标")
        } footer: {
            Text("切换后系统会弹出确认框；图标均为 App 内置，不占用你的相册。")
        }
    }

    // MARK: - 主题

    private var themeSection: some View {
        Section("聊天气泡") {
            ForEach(BubbleTheme.allCases) { theme in
                Button {
                    appearance.theme = theme
                } label: {
                    HStack(spacing: 12) {
                        themeSwatch(theme)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(theme.title)
                                .foregroundStyle(.primary)
                            Text(theme.subtitle)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        if appearance.theme == theme {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(Color(red: 0.72, green: 0.60, blue: 1.0))
                        }
                    }
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func themeSwatch(_ theme: BubbleTheme) -> some View {
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(
                LinearGradient(colors: theme.outgoingColors, startPoint: .topLeading, endPoint: .bottomTrailing)
            )
            .frame(width: 44, height: 30)
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .strokeBorder(.white.opacity(0.2), lineWidth: 0.6)
            )
    }

    // MARK: - 背景

    private var backgroundSection: some View {
        Section("聊天背景") {
            if let image = appearance.backgroundImage {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
                    .frame(height: 120)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
            }

            // 注意：PhotosPicker 的 label 闭包在 SDK 里是 @Sendable 的，
            // 里面**不能**引用 appearance 这类 main actor 隔离属性，否则编译不过。
            // 所以这里用常量文案；当前是否已有背景，由上方预览缩略图表达。
            PhotosPicker(selection: $backgroundItem, matching: .images) {
                Label("选择背景图片", systemImage: "photo")
            }
            .onChange(of: backgroundItem) { _, item in
                guard let item else { return }
                // onChange 的闭包不是 MainActor 隔离的，直接 Task{} 会在 Swift 6 下
                // 报「main actor-isolated property referenced from a Sendable closure」。
                // 显式 @MainActor 让整个任务留在主 actor 上，拿到 data 后直接落盘。
                Task { @MainActor in
                    if let data = try? await item.loadTransferable(type: Data.self) {
                        appearance.saveBackground(data)
                    }
                    backgroundItem = nil
                }
            }

            if appearance.backgroundImage != nil {
                slider("模糊", value: $appearance.backgroundBlur, range: 0...24, unit: "px")
                slider("亮度", value: $appearance.backgroundBrightness, range: -0.4...0.4, unit: "")
                slider("暗色遮罩", value: $appearance.backgroundDim, range: 0...0.75, unit: "")

                Button("恢复默认调节") { appearance.resetBackgroundAdjustments() }
                Button("移除背景图片", role: .destructive) { appearance.clearBackground() }
            }
        }
    }

    private func slider(_ title: String, value: Binding<Double>, range: ClosedRange<Double>, unit: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(title).font(.subheadline)
                Spacer()
                Text(String(format: "%.2f", value.wrappedValue) + unit)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Slider(value: value, in: range)
        }
    }

    // MARK: - 头像

    private var avatarSection: some View {
        Section("头像") {
            avatarRow(
                title: "我的头像",
                image: appearance.myAvatar,
                item: $myAvatarItem,
                onSave: { appearance.saveMyAvatar($0) },
                onClear: { appearance.clearMyAvatar() }
            )
            avatarRow(
                title: "绘梨衣头像",
                image: appearance.characterAvatar,
                item: $characterAvatarItem,
                onSave: { appearance.saveCharacterAvatar($0) },
                onClear: { appearance.clearCharacterAvatar() }
            )
        }
    }

    private func avatarRow(
        title: String,
        image: UIImage?,
        item: Binding<PhotosPickerItem?>,
        onSave: @escaping (Data) -> Void,
        onClear: @escaping () -> Void
    ) -> some View {
        HStack(spacing: 12) {
            Group {
                if let image {
                    Image(uiImage: image).resizable().scaledToFill()
                } else {
                    Circle().fill(Color.white.opacity(0.12))
                        .overlay(Image(systemName: "person.fill").foregroundStyle(.white.opacity(0.4)))
                }
            }
            .frame(width: 44, height: 44)
            .clipShape(Circle())

            Text(title)

            Spacer()

            PhotosPicker(selection: item, matching: .images) {
                Text("选择")
            }
            .onChange(of: item.wrappedValue) { _, newValue in
                guard let newValue else { return }
                // 同背景图：闭包不在 MainActor 上，必须显式标注，
                // 否则 Binding 与 onSave 都会被判成跨 actor 捕获。
                Task { @MainActor in
                    if let data = try? await newValue.loadTransferable(type: Data.self) {
                        onSave(data)
                    }
                    item.wrappedValue = nil
                }
            }

            if image != nil {
                Button("清除", role: .destructive, action: onClear)
                    .font(.caption)
            }
        }
    }
}
