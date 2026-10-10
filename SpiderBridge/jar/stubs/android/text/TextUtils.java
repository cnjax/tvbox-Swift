package android.text;

public class TextUtils {
    public static boolean isEmpty(CharSequence s) { return s == null || s.length() == 0; }
    public static String join(CharSequence sep, Object[] parts) { return join(sep, java.util.Arrays.asList(parts)); }
    public static String join(CharSequence sep, Iterable parts) {
        java.util.StringJoiner j = new java.util.StringJoiner(sep);
        for (Object p : parts) j.add(String.valueOf(p));
        return j.toString();
    }
    public static boolean equals(CharSequence a, CharSequence b) { return a == b || (a != null && b != null && a.toString().equals(b.toString())); }
}
