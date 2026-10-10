package android.util;

public class Base64 {
    public static final int DEFAULT = 0, NO_PADDING = 1, NO_WRAP = 2, CRLF = 4, URL_SAFE = 8;

    public static byte[] decode(String s, int flags) { return decode(s.getBytes(), flags); }
    public static byte[] decode(byte[] b, int flags) {
        String s = new String(b).replaceAll("\\s", "");
        if ((flags & URL_SAFE) != 0 || s.indexOf('-') >= 0 || s.indexOf('_') >= 0) return java.util.Base64.getUrlDecoder().decode(s.replace('+', '-').replace('/', '_'));
        return java.util.Base64.getMimeDecoder().decode(s);
    }
    public static String encodeToString(byte[] b, int flags) { return new String(encode(b, flags)); }
    public static byte[] encode(byte[] b, int flags) {
        java.util.Base64.Encoder enc = (flags & URL_SAFE) != 0 ? java.util.Base64.getUrlEncoder() : java.util.Base64.getEncoder();
        if ((flags & NO_PADDING) != 0) enc = enc.withoutPadding();
        byte[] out = enc.encode(b);
        if ((flags & NO_WRAP) != 0) return out;
        // Android DEFAULT wraps at 76 chars and appends a newline.
        StringBuilder sb = new StringBuilder();
        String s = new String(out);
        for (int i = 0; i < s.length(); i += 76) sb.append(s, i, Math.min(s.length(), i + 76)).append('\n');
        return sb.toString().getBytes();
    }
}
