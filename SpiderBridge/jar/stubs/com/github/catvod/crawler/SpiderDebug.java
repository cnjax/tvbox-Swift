package com.github.catvod.crawler;

public class SpiderDebug {
    public static void log(String msg) { System.err.println("[spider] " + msg); }
    public static void log(Throwable e) { e.printStackTrace(); }
}
