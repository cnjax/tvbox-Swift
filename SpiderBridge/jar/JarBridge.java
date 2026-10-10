import android.app.Application;
import com.github.catvod.crawler.Spider;
import com.github.catvod.crawler.SpiderApi;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileDescriptor;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Runs TVBox jar spiders (dex converted to JVM bytecode) for bridge.py.
 * stdin/stdout: one JSON object per line.
 *   request:  {"id":1,"key":"site","jar":"/abs/x.jar","api":"csp_XBPQ","ext":"...","method":"home","args":[...]}
 *   response: {"id":1,"result":"..."} or {"id":1,"error":"..."}
 * Spiders print freely, so System.out is redirected to stderr and the protocol owns the real stdout.
 */
public class JarBridge {
    private static final Application CONTEXT = new Application();
    private static final Map<String, ClassLoader> LOADERS = new ConcurrentHashMap<>();
    private static final Map<String, Spider> SPIDERS = new ConcurrentHashMap<>();
    private static PrintStream out;

    public static void main(String[] args) throws Exception {
        out = new PrintStream(new FileOutputStream(FileDescriptor.out), true, StandardCharsets.UTF_8);
        System.setOut(System.err);
        ExecutorService pool = Executors.newCachedThreadPool();
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line;
        while ((line = in.readLine()) != null) {
            JSONObject req = new JSONObject(line);
            pool.execute(() -> reply(req));
        }
        System.exit(0);
    }

    private static void reply(JSONObject req) {
        JSONObject res = new JSONObject().put("id", req.getInt("id"));
        try {
            Object result = call(req);
            res.put("result", result == null ? "" : result);
        } catch (Throwable e) {
            Throwable cause = e instanceof InvocationTargetException ? e.getCause() : e;
            cause.printStackTrace();
            res.put("error", String.valueOf(cause));
        }
        synchronized (JarBridge.class) {
            out.println(res);
        }
    }

    private static Object call(JSONObject req) throws Exception {
        Spider spider = spider(req);
        JSONArray a = req.optJSONArray("args");
        if (a == null) a = new JSONArray();
        switch (req.getString("method")) {
            case "home": return spider.homeContent(a.optBoolean(0, true));
            case "homeVod": return spider.homeVideoContent();
            case "category": return spider.categoryContent(a.getString(0), a.getString(1), a.optBoolean(2, true), toMap(a.optJSONObject(3)));
            case "detail": return spider.detailContent(toList(a.getJSONArray(0)));
            case "search": return spider.searchContent(a.getString(0), a.optBoolean(1, false));
            case "play": return spider.playerContent(a.getString(0), a.getString(1), toList(a.optJSONArray(2)));
            default: throw new IllegalArgumentException("unknown method " + req.getString("method"));
        }
    }

    private static Spider spider(JSONObject req) throws Exception {
        String key = req.getString("key");
        Spider cached = SPIDERS.get(key);
        if (cached != null) return cached;
        synchronized (SPIDERS) {
            cached = SPIDERS.get(key);
            if (cached != null) return cached;
            ClassLoader loader = loader(req.getString("jar"));
            Thread.currentThread().setContextClassLoader(loader);
            String api = req.getString("api");
            String name = "com.github.catvod.spider." + (api.startsWith("csp_") ? api.substring(4) : api);
            Spider spider = (Spider) loader.loadClass(name).getDeclaredConstructor().newInstance();
            try {
                spider.initApi(new SpiderApi());
            } catch (Throwable e) {
                System.err.println("[bridge] initApi skipped: " + e);
            }
            spider.init(CONTEXT, req.optString("ext", ""));
            SPIDERS.put(key, spider);
            return spider;
        }
    }

    private static ClassLoader loader(String jar) throws Exception {
        ClassLoader cached = LOADERS.get(jar);
        if (cached != null) return cached;
        ClassLoader loader = new URLClassLoader(new URL[]{new File(jar).toURI().toURL()}, JarBridge.class.getClassLoader());
        try {
            // Android hosts call Init.init(context) once per jar before any spider.
            loader.loadClass("com.github.catvod.spider.Init").getMethod("init", android.content.Context.class).invoke(null, CONTEXT);
        } catch (Throwable e) {
            System.err.println("[bridge] Init.init skipped: " + e);
        }
        LOADERS.put(jar, loader);
        return loader;
    }

    private static List<String> toList(JSONArray a) {
        List<String> list = new ArrayList<>();
        if (a != null) for (int i = 0; i < a.length(); i++) list.add(a.optString(i));
        return list;
    }

    private static HashMap<String, String> toMap(JSONObject o) {
        HashMap<String, String> map = new HashMap<>();
        if (o != null) for (String k : o.keySet()) map.put(k, o.optString(k));
        return map;
    }
}
