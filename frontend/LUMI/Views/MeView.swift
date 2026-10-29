import SwiftUI

/// 「我」：个人入口，聚合 设置 / 外观 / 模型 / 关于。
///
/// 36 项需求 01「精简导航」的第三个主入口。设置类页面改为 push 进入，
/// 让原 SettingsView 的「完成」按钮在导航栈里能正确返回。
struct MeView: View {
    @EnvironmentObject private var session: AppSession
    @ObservedObject private var appearance = AppearanceStore.shared

    var body: some View {
        NavigationStack {
            List {
                profileCard
                entrySection
                aboutSection
            }
            .scrollContentBackground(.hidden)
            .background(LUMIStyle.pageBackground)
            .navigationTitle("我")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private var profileCard: some View {
        Section {
            HStack(spacing: 14) {
                Group {
                    if let avatar = appearance.myAvatar {
                        Image(uiImage: avatar).resizable().scaledToFill()
                    } else {
                        Circle().fill(LUMIStyle.violet.opacity(0.2))
                            .overlay(Image(systemName: "person.fill").foregroundStyle(LUMIStyle.violet))
                    }
                }
                .frame(width: 56, height: 56)
                .clipShape(Circle())

                VStack(alignment: .leading, spacing: 3) {
                    Text("我的绘梨衣")
                        .font(.headline)
                    Text("和她说说话，把想记的留在这。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(.vertical, 6)
        }
    }

    private var entrySection: some View {
        Section {
            NavigationLink {
                SettingsView()
            } label: {
                Label("设置", systemImage: "gearshape")
            }
            NavigationLink {
                AppearanceSettingsView()
            } label: {
                Label("外观与气泡", systemImage: "paintbrush.pointed")
            }
            NavigationLink {
                ModelStatusView()
            } label: {
                Label("AI 模型", systemImage: "sparkles")
            }
            NavigationLink {
                StyleSettingsView()
            } label: {
                Label("回复风格", systemImage: "slider.horizontal.3")
            }
        }
    }

    private var aboutSection: some View {
        Section {
            HStack {
                Text("版本")
                Spacer()
                Text("2.0.0").foregroundStyle(.secondary)
            }
            LabeledContent("角色", value: "绘梨衣")
            LabeledContent("模型", value: "deepseek-flash")
        } footer: {
            Text("她的设定、语音与模型说明集中在设置和人物资料里，这里只做入口。")
        }
    }
}
