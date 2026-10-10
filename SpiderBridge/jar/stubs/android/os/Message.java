package android.os;

public class Message {
    public int what;
    public Object obj;
    public static Message obtain() { return new Message(); }
}
