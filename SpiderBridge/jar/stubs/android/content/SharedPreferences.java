package android.content;

import java.util.concurrent.ConcurrentHashMap;

public interface SharedPreferences {
    String getString(String key, String def);
    int getInt(String key, int def);
    long getLong(String key, long def);
    boolean getBoolean(String key, boolean def);
    float getFloat(String key, float def);
    boolean contains(String key);
    Editor edit();

    interface Editor {
        Editor putString(String key, String value);
        Editor putInt(String key, int value);
        Editor putLong(String key, long value);
        Editor putBoolean(String key, boolean value);
        Editor putFloat(String key, float value);
        Editor remove(String key);
        Editor clear();
        boolean commit();
        void apply();
    }

    // ponytail: in-memory only, prefs reset when the bridge restarts.
    class Impl implements SharedPreferences, Editor {
        private final ConcurrentHashMap<String, Object> map = new ConcurrentHashMap<>();
        private <T> T get(String key, T def) { Object v = map.get(key); return v == null ? def : (T) v; }
        public String getString(String key, String def) { return get(key, def); }
        public int getInt(String key, int def) { return get(key, def); }
        public long getLong(String key, long def) { return get(key, def); }
        public boolean getBoolean(String key, boolean def) { return get(key, def); }
        public float getFloat(String key, float def) { return get(key, def); }
        public boolean contains(String key) { return map.containsKey(key); }
        public Editor edit() { return this; }
        private Editor put(String key, Object value) { if (value == null) map.remove(key); else map.put(key, value); return this; }
        public Editor putString(String key, String value) { return put(key, value); }
        public Editor putInt(String key, int value) { return put(key, value); }
        public Editor putLong(String key, long value) { return put(key, value); }
        public Editor putBoolean(String key, boolean value) { return put(key, value); }
        public Editor putFloat(String key, float value) { return put(key, value); }
        public Editor remove(String key) { map.remove(key); return this; }
        public Editor clear() { map.clear(); return this; }
        public boolean commit() { return true; }
        public void apply() {}
    }
}
