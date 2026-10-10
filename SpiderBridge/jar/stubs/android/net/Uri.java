package android.net;

import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class Uri {
    private final String raw;
    private final URI uri;
    private Uri(String raw) {
        this.raw = raw;
        URI u = null;
        try { u = URI.create(raw.replace(" ", "%20")); } catch (Exception ignored) {}
        this.uri = u;
    }
    public static Uri parse(String s) { return new Uri(s); }
    public static Uri fromFile(java.io.File f) { return new Uri(f.toURI().toString()); }
    public static String encode(String s) { return encode(s, null); }
    public static String encode(String s, String allow) {
        if (s == null) return null;
        StringBuilder sb = new StringBuilder();
        for (char c : s.toCharArray()) {
            if ((allow != null && allow.indexOf(c) >= 0) || "-_.!~*'()".indexOf(c) >= 0 || (c < 128 && Character.isLetterOrDigit(c))) sb.append(c);
            else sb.append(URLEncoder.encode(String.valueOf(c), StandardCharsets.UTF_8).replace("+", "%20"));
        }
        return sb.toString();
    }
    public static String decode(String s) { return s == null ? null : URLDecoder.decode(s.replace("+", "%2B"), StandardCharsets.UTF_8); }
    public String getScheme() { return uri == null ? null : uri.getScheme(); }
    public String getHost() { return uri == null ? null : uri.getHost(); }
    public int getPort() { return uri == null ? -1 : uri.getPort(); }
    public String getPath() { return uri == null ? null : uri.getPath(); }
    public String getEncodedPath() { return uri == null ? null : uri.getRawPath(); }
    public String getQuery() { return uri == null ? null : uri.getQuery(); }
    public String getLastPathSegment() {
        String p = getPath();
        if (p == null) return null;
        String[] parts = p.split("/");
        return parts.length == 0 ? null : parts[parts.length - 1];
    }
    public String getQueryParameter(String key) {
        String q = uri == null ? null : uri.getRawQuery();
        if (q == null) return null;
        for (String pair : q.split("&")) {
            int i = pair.indexOf('=');
            String k = i < 0 ? pair : pair.substring(0, i);
            if (decode(k).equals(key)) return i < 0 ? "" : decode(pair.substring(i + 1));
        }
        return null;
    }
    public Builder buildUpon() { return new Builder(raw); }
    @Override public String toString() { return raw; }

    public static class Builder {
        private String scheme = "", authority = "", path = "", query = "";
        public Builder() {}
        Builder(String raw) {
            URI u = URI.create(raw);
            scheme = u.getScheme() == null ? "" : u.getScheme();
            authority = u.getRawAuthority() == null ? "" : u.getRawAuthority();
            path = u.getRawPath() == null ? "" : u.getRawPath();
            query = u.getRawQuery() == null ? "" : u.getRawQuery();
        }
        public Builder scheme(String s) { scheme = s; return this; }
        public Builder authority(String a) { authority = a; return this; }
        public Builder encodedPath(String p) { path = p; return this; }
        public Builder path(String p) { path = p; return this; }
        public Builder clearQuery() { query = ""; return this; }
        public Builder appendQueryParameter(String k, String v) {
            query += (query.isEmpty() ? "" : "&") + encode(k) + "=" + encode(v);
            return this;
        }
        public Uri build() { return new Uri(scheme + "://" + authority + path + (query.isEmpty() ? "" : "?" + query)); }
    }
}
