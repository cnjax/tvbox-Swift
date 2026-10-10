import Foundation

/// type=3 爬虫（py / js / jar）桥接：macOS 上启动 App 内置的 SpiderBridge/bridge.py，
/// 它把爬虫包装成本地 type=4 远程接口，SourceService 按 type=4 访问即可。
/// 依赖本机 python3；jar 源另需 JDK，js 源另需 Node.js。
actor SpiderBridge {
    static let shared = SpiderBridge()
    static let port = 9978

    #if os(macOS)
    static let isAvailable = true
    #else
    static let isAvailable = false
    #endif

    private var startTask: Task<Void, Error>?
    #if os(macOS)
    private var process: Process?
    #endif

    private init() {}

    /// 将 type=3 源转换为指向本地桥接服务的 type=4 源；其他类型原样返回。
    func remoteSource(for source: SourceBean) async throws -> SourceBean {
        guard source.type == 3, Self.isAvailable else { return source }
        try await ensureRunning()
        var components = URLComponents(string: "http://127.0.0.1:\(Self.port)/vod")!
        components.queryItems = [
            URLQueryItem(name: "key", value: source.key),
            URLQueryItem(name: "api", value: source.api),
            URLQueryItem(name: "jar", value: source.jar ?? "")
        ]
        return SourceBean(
            key: source.key, name: source.name, api: components.url!.absoluteString,
            searchable: source.searchable, filterable: source.filterable, quickSearch: source.quickSearch,
            playerType: source.playerType, type: 4, ext: source.ext, jar: source.jar
        )
    }

    private func ensureRunning() async throws {
        if let startTask { return try await startTask.value }
        let task = Task { try await self.start() }
        startTask = task
        do {
            try await task.value
        } catch {
            startTask = nil
            throw error
        }
    }

    private func isHealthy() async -> Bool {
        let url = URL(string: "http://127.0.0.1:\(Self.port)/health")!
        guard let (_, response) = try? await URLSession.shared.data(from: url) else { return false }
        return (response as? HTTPURLResponse)?.statusCode == 200
    }

    private func start() async throws {
        #if os(macOS)
        if await isHealthy() { return }
        guard let script = Bundle.main.url(forResource: "bridge", withExtension: "py", subdirectory: "SpiderBridge") else {
            throw SpiderBridgeError.missing("App 内缺少 SpiderBridge/bridge.py")
        }
        let candidates = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
        guard let python = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) else {
            throw SpiderBridgeError.missing("未找到 python3，请先安装 Python 3")
        }
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("TVBox/spider")
        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = [script.path, "--port", String(Self.port), "--data", support.path, "--watch-parent"]
        process.standardOutput = FileHandle.standardError
        process.standardError = FileHandle.standardError
        try process.run()
        self.process = process

        // 首次启动需创建 venv 并安装依赖，最多等 3 分钟
        for _ in 0..<360 {
            if await isHealthy() { return }
            if !process.isRunning { throw SpiderBridgeError.missing("爬虫桥接进程启动失败（退出码 \(process.terminationStatus)）") }
            try await Task.sleep(nanoseconds: 500_000_000)
        }
        throw SpiderBridgeError.missing("爬虫桥接启动超时")
        #else
        throw SpiderBridgeError.missing("当前平台不支持 type=3 爬虫源")
        #endif
    }
}

enum SpiderBridgeError: LocalizedError {
    case missing(String)

    var errorDescription: String? {
        switch self {
        case .missing(let message): return message
        }
    }
}
