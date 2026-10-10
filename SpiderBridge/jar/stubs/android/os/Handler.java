package android.os;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class Handler {
    private static final ScheduledExecutorService EXEC = Executors.newSingleThreadScheduledExecutor(r -> { Thread t = new Thread(r, "main-looper"); t.setDaemon(true); return t; });
    public Handler() {}
    public Handler(Looper looper) {}
    public boolean post(Runnable r) { EXEC.execute(r); return true; }
    public boolean postDelayed(Runnable r, long ms) { EXEC.schedule(r, ms, TimeUnit.MILLISECONDS); return true; }
    public void removeCallbacks(Runnable r) {}
    public boolean sendEmptyMessage(int what) { return true; }
    public boolean sendMessage(Message msg) { return true; }
    public void handleMessage(Message msg) {}
}
