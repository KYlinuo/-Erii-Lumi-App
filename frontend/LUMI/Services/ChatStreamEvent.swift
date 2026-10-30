import Foundation

/// The backend emits one JSON object per SSE data line. AsyncBytes.lines has
/// already removed the line terminator; never wait for another newline here.
enum ChatStreamEvent: Sendable {
    case delta(String)
    case done(ChatResponse)

    static func decode(line: String) throws -> ChatStreamEvent? {
        guard line.hasPrefix("data:") else { return nil }
        let payload = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
        guard !payload.isEmpty else { return nil }
        let data = Data(payload.utf8)
        struct Header: Decodable {
            let type: String
            let text: String?
            let code: String?
            let message: String?
        }
        do {
            let header = try JSONDecoder().decode(Header.self, from: data)
            switch header.type {
            case "delta":
                guard let text = header.text else { throw LUMIError.upstreamBadResponse }
                return .delta(text)
            case "done":
                return .done(try JSONDecoder().decode(ChatResponse.self, from: data))
            case "error":
                throw LUMIError.from(code: header.code ?? "upstream_error", httpStatus: 502,
                                     message: header.message ?? "", retryAfter: nil)
            default:
                return nil // Allow future metadata and heartbeat events.
            }
        } catch let error as LUMIError {
            throw error
        } catch {
            throw LUMIError.upstreamBadResponse
        }
    }
}
