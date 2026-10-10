package android.content;

import java.io.File;
import java.util.HashMap;
import java.util.Map;

public class Context {
    private static final Map<String, SharedPreferences> PREFS = new HashMap<>();
    static File root() {
        File dir = new File(System.getProperty("bridge.data", System.getProperty("java.io.tmpdir")));
        dir.mkdirs();
        return dir;
    }
    public Context getApplicationContext() { return this; }
    public File getCacheDir() { File f = new File(root(), "cache"); f.mkdirs(); return f; }
    public File getFilesDir() { File f = new File(root(), "files"); f.mkdirs(); return f; }
    public File getExternalCacheDir() { return getCacheDir(); }
    public File getExternalFilesDir(String type) { return getFilesDir(); }
    public ClassLoader getClassLoader() { return Thread.currentThread().getContextClassLoader(); }
    public String getPackageName() { return "com.github.tvbox.osc"; }
    public Object getSystemService(String name) { return null; }
    public void startActivity(Intent intent) {}
    public synchronized SharedPreferences getSharedPreferences(String name, int mode) {
        return PREFS.computeIfAbsent(name, k -> new SharedPreferences.Impl());
    }
}
