import SwiftUI

/// 约定 / 待续话题（需求 20）：她记下的小约定，可完成/推迟/取消。
struct PromisesView: View {
    @EnvironmentObject private var session: AppSession
    @State private var promises: [PromiseDTO] = []
    @State private var newContent = ""
    @State private var isLoading = true

    var body: some View {
        List {
            Section {
                HStack {
                    TextField("记一条约定…", text: $newContent)
                        .onSubmit { add() }
                    Button("添加") { add() }
                        .disabled(newContent.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }

            Section {
                if isLoading {
                    HStack { Spacer(); ProgressView(); Spacer() }
                } else if promises.isEmpty {
                    Text("还没有约定。她记性很好，说过的她会记得。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(promises) { promise in
                        promiseRow(promise)
                    }
                }
            } header: {
                Text("待办")
            }
        }
        .scrollContentBackground(.hidden)
        .background(LUMIStyle.pageBackground)
        .task { await load() }
    }

    private func promiseRow(_ promise: PromiseDTO) -> some View {
        HStack(spacing: 12) {
            Button {
                Task { await setStatus(promise, status: promise.status == "done" ? "pending" : "done") }
            } label: {
                Image(systemName: promise.status == "done" ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(promise.status == "done" ? .green : .secondary)
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 2) {
                Text(promise.content)
                    .strikethrough(promise.status == "done")
                    .foregroundStyle(promise.status == "done" ? .secondary : .primary)
                if promise.certainty == "vague" {
                    Text("随口一说").font(.caption2).foregroundStyle(.tertiary)
                }
            }
            Spacer()

            if promise.status == "pending" {
                Button("推迟") {
                    Task { await setStatus(promise, status: "postponed") }
                }
                .font(.caption)
            }
        }
        .swipeActions(edge: .trailing) {
            Button(role: .destructive) {
                Task { await remove(promise) }
            } label: {
                Label("删除", systemImage: "trash")
            }
        }
    }

    private func load() async {
        do {
            promises = try await session.api.listPromises(status: "pending")
        } catch {
            promises = []
        }
        isLoading = false
    }

    private func add() {
        let content = newContent.trimmingCharacters(in: .whitespaces)
        guard !content.isEmpty else { return }
        newContent = ""
        Task {
            _ = try? await session.api.createPromise(content: content)
            await load()
        }
    }

    private func setStatus(_ promise: PromiseDTO, status: String) async {
        _ = try? await session.api.updatePromise(id: promise.id, status: status)
        await load()
    }

    private func remove(_ promise: PromiseDTO) async {
        try? await session.api.deletePromise(id: promise.id)
        await load()
    }
}
