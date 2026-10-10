package android.content;

public class Intent {
    public Intent() {}
    public Intent(String action) {}
    public Intent(String action, android.net.Uri uri) {}
    public Intent addFlags(int flags) { return this; }
    public Intent putExtra(String k, String v) { return this; }
    public Intent setClassName(String p, String c) { return this; }
    public Intent setData(android.net.Uri uri) { return this; }
    public Intent setDataAndType(android.net.Uri uri, String type) { return this; }
}
